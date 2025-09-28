import mimetypes
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
import yt_dlp
from playwright.sync_api import sync_playwright

from image_model import predict_image
from video_model import predict_video
from plagiarism_scanner import scan_file, scan_text

# -------------------------
# Config
# -------------------------
DATA_DIR = Path("data")
IMAGE_DIR = DATA_DIR / "images"
VIDEO_DIR = DATA_DIR / "videos"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
MERGE_OUTPUT_FORMAT = "mp4"

# -------------------------
# Platform detection
# -------------------------
def detect_platform(url: str) -> str:
    domain = urlparse(url).netloc.lower()
    if "facebook.com" in domain:
        print("[DEBUG] Detected platform by domain: Facebook")
        return "facebook"
    if "youtube.com" in domain or "youtu.be" in domain:
        print("[DEBUG] Detected platform by domain: YouTube")
        return "youtube"

    # Fallback to meta-tag sniff
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            if page.query_selector("meta[property='og:site_name'][content='Facebook']"):
                return "facebook"
            if page.query_selector("meta[itemprop='name'][content='YouTube']"):
                return "youtube"
        except Exception as e:
            print(f"[WARN] Failed meta-tag sniff: {e}")
        finally:
            browser.close()

    return None

# -------------------------
# MIME type helper
# -------------------------
def head_content_type(url: str, timeout=8) -> str | None:
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        ct = r.headers.get("Content-Type")
        if ct:
            return ct.split(";")[0].strip().lower()
    except Exception:
        return None
    return None

def get_media_type_from_url(url: str) -> str | None:
    mime = head_content_type(url)
    if mime:
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("video/"):
            return "video"
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    if ext in {".jpg", ".jpeg", ".png", ".gif"}:
        return "image"
    if ext in {".mp4", ".mov", ".mkv", ".avi"}:
        return "video"
    return None

# -------------------------
# Scraper
# -------------------------
def scrape_media_urls(url: str):
    media_links = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/115.0 Safari/537.36"
        })
        
        try:
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            
            try:
                page.wait_for_selector(
                    "img[src*='pbs.twimg.com/media'], video, "
                    "img[data-visualcompletion='media-vc-image'], "
                    "img[src*='scontent']",
                    timeout=20000
                )
            except Exception:
                print("[WARN] Media selector not found within 20s")

            # Facebook videos
            for el in page.query_selector_all("video"):
                src = el.get_attribute("src")
                if src and "fbcdn.net" in src:
                    media_links.append(src)

            # Facebook images
            for el in page.query_selector_all("img[data-visualcompletion='media-vc-image']"):
                src = el.get_attribute("src")
                if src and "fbcdn.net" in src:
                    media_links.append(src)

            for el in page.query_selector_all("img[src*='scontent']"):
                src = el.get_attribute("src")
                if src and "fbcdn.net" in src:
                    media_links.append(src)

        except Exception as e:
            print(f"[WARN] Error during scraping: {e}")
        finally:
            browser.close()

    seen = set()
    unique_links = []
    for m in media_links:
        if m not in seen:
            unique_links.append(m)
            seen.add(m)

    print(f"[DEBUG] Scraped media links: {unique_links}")
    return unique_links

# -------------------------
# Download helpers
# -------------------------
def download_with_requests(url: str, save_dir: Path) -> Path | None:
    save_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    filename = os.path.basename(parsed.path)
    if '.' not in filename:
        mime = head_content_type(url)
        if mime:
            ext = mimetypes.guess_extension(mime)
        else:
            ext = ".bin"
        filename += ext
    local_filename = save_dir / filename
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[INFO] Saved: {local_filename}")
        return local_filename
    except Exception as e:
        print(f"[ERROR] Failed to download {url}: {e}")
        return None

def download_with_ytdlp(url: str, save_dir: Path) -> Path:
    save_dir.mkdir(parents=True, exist_ok=True)

    # Get domain name for prefix
    domain = urlparse(url).netloc.lower().split('.')[-2]  # e.g., "facebook", "youtube"

    # Find next available file number
    existing_files = list(save_dir.glob(f"{domain}_*"))
    if existing_files:
        nums = []
        for f in existing_files:
            try:
                nums.append(int(f.stem.split('_')[-1]))
            except ValueError:
                continue
        next_num = max(nums) + 1 if nums else 1
    else:
        next_num = 1

    # Temporary safe name for yt-dlp download
    temp_name = f"{domain}_temp.%(ext)s"
    ydl_opts = {
        'outtmpl': str(save_dir / temp_name),
        'outtmpl': str(save_dir / f"{domain}_{next_num}.%(ext)s"),
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
        'merge_output_format': MERGE_OUTPUT_FORMAT,
        'quiet': False,
        'restrictfilenames': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        ext = info.get('ext', 'mp4')

    # Final name as domain_number.ext
    final_name = f"{domain}_{next_num}.{ext}"
    temp_path = save_dir / f"{domain}_temp.{ext}"
    final_path = save_dir / final_name

    if temp_path.exists():
        temp_path.rename(final_path)

    return final_path

def get_photo_index(url: str) -> int:
    parts = urlparse(url).path.split("/")
    if "photo" in parts:
        try:
            return int(parts[-1])  # last segment after "photo/"
        except ValueError:
            return 1
    return 1

# -------------------------
# Unified download
# -------------------------
def download_media(url: str):
    platform = detect_platform(url)
    if not platform:
        print("[ERROR] Unsupported or invalid URL.")
        return None
    
    if platform == "youtube":
        try:
            return download_with_ytdlp(url, VIDEO_DIR)
        except Exception as e:
            print(f"[WARN] yt-dlp failed for YouTube: {e}")
            print("[INFO] Skipping scraping fallback for YouTube.")
            return None

    
    if platform == "facebook":
        path_lower = urlparse(url).path.lower()

        # Handle Watch, Reels, Stories
        if any(k in path_lower for k in ("/watch", "/reel", "/videos","/stories")) or "story_fbid" in url.lower():
            try:
                return download_with_ytdlp(url, VIDEO_DIR)
            except Exception as e:
                print(f"[WARN] yt-dlp failed for Facebook: {e}")
                print("[INFO] Attempting scraping fallback…")
                media_links = scrape_media_urls(url)
                if media_links:
                    vids = [m for m in media_links if get_media_type_from_url(m) == "video"]
                    imgs = [m for m in media_links if get_media_type_from_url(m) == "image"]

                    if vids:
                        return download_with_requests(vids[0], VIDEO_DIR)
                    if imgs:
                        return download_with_requests(imgs[0], IMAGE_DIR)

                print("[ERROR] Fallback also failed or found no usable media.")
                return None

        media_links = scrape_media_urls(url)
        if media_links:
            # Separate by type
            vids = [m for m in media_links if get_media_type_from_url(m) == "video"]
            imgs = [m for m in media_links if get_media_type_from_url(m) == "image"]

            if vids:
                return download_with_requests(vids[0], VIDEO_DIR)
            if imgs:
                index = get_photo_index(url) - 1  # convert to 0-based
            if 0 <= index < len(imgs):
                return download_with_requests(imgs[index], IMAGE_DIR)
            else:
                print(f"[WARN] Requested photo index out of range, defaulting to first image.")
                return download_with_requests(imgs[0], IMAGE_DIR)

        print("[ERROR] Fallback also failed or found no usable media.")
        return None


    media_links = scrape_media_urls(url)
    if not media_links:
        print("[WARN] No media links found.")
        return None

    first_type = get_media_type_from_url(media_links[0])
    if all(get_media_type_from_url(link) == "image" for link in media_links):
        return download_with_requests(media_links[0], IMAGE_DIR)
    if all(get_media_type_from_url(link) == "video" for link in media_links):
        return download_with_requests(media_links[0], VIDEO_DIR)

    target_dir = IMAGE_DIR if first_type == "image" else VIDEO_DIR
    return download_with_requests(media_links[0], target_dir)

def get_media_type(file_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type:
        if mime_type.startswith("image"):
            return "image"
        elif mime_type.startswith("video"):
            return "video"
        elif mime_type in [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain"
        ]:
            return "document"
    return "unknown"

# -------------------------
# File routing + inference
# -------------------------
def save_to_correct_folder(file_path):
    media_type = get_media_type(file_path)
    dest_dir = IMAGE_DIR if media_type == "image" else VIDEO_DIR
    dest_path = dest_dir / os.path.basename(file_path)
    os.replace(file_path, dest_path)
    return dest_path

def run_inference(file_path: Path):
    media_type = get_media_type(file_path)

    if media_type == "image":
        label, realism_conf, deepfake_conf = predict_image(file_path)
        result = {
            "type": "image",
            "label": label,
            "realism": realism_conf,
            "deepfake": deepfake_conf,
            "file": file_path.name
        }
        print(f"[RESULT] {file_path.name} → {label} "
              f"(realism: {realism_conf:.4f}, deepfake: {deepfake_conf:.4f})")
        return result

    elif media_type == "video":
        label, avg_real, avg_fake = predict_video(file_path)
        result = {
            "type": "video",
            "label": label,
            "realism": avg_real,
            "deepfake": avg_fake,
            "file": file_path.name
        }
        print(f"[RESULT] {file_path.name} → {label} "
              f"(avg_realism: {avg_real:.4f}, avg_deepfake: {avg_fake:.4f})")
        return result

    elif media_type == "document":
        results, summary = scan_file(file_path)
        result = {
            "type": "document",
            "summary": summary,
            "paragraphs": results,
            "file": file_path.name
        }
        print(f"[RESULT] Document scanned → {summary}")
        return result

    else:
        print(f"[ERROR] Unsupported media type for: {file_path}")
        return None


# -------------------------
# CLI
# -------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: python app.py <url_or_file_path>")
        print("  python app.py --text \"Your pasted text here\"")
        sys.exit(1)

    target = sys.argv[1].strip()

    if target == "--text":
        if len(sys.argv) < 3:
            print("[ERROR] No text provided after --text")
            sys.exit(1)
        pasted_text = " ".join(sys.argv[2:])
        results, summary = scan_text(pasted_text)
        
        for idx, res in enumerate(results, 1):
            print(f"[RESULT] Paragraph {idx}: {res['label']} "
                  f"{'→ ' + res['web_source'] if res['web_source'] else ''}")

        print("\n--- Summary ---")
        print(f"Checked {summary['total']} paragraphs")
        print(f"Plagiarized: {summary['plagiarized']} "
              f"(Exact: {summary['exact']}, Paraphrase: {summary['paraphrase']})")
        print(f"Original: {summary['original']}")

        print("\n--- Percentages ---")
        print(f"Plagiarized: {summary['plag_percent']:.4f}% "
              f"(Exact: {summary['exact_percent']:.4f}%, "
              f"Paraphrase: {summary['paraphrase_percent']:.4f}%)")
        print(f"Original: {summary['original_percent']:.4f}%")
        sys.exit(0)
        
    # Handle local files for plag scan
    if os.path.isfile(target):
        media_type = get_media_type(target)
        if media_type == "document":
            results, summary = scan_file(target)
            for idx, res in enumerate(results, 1):
                print(f"[RESULT] Paragraph {idx}: {res['label']} "
                      f"{'→ ' + res['web_source'] if res['web_source'] else ''}")
            sys.exit(0)
        elif media_type in ("image", "video"):
            run_inference(Path(target))
            sys.exit(0)
        else:
            print(f"[ERROR] Unsupported local file type: {target}")
            sys.exit(1)

    # --- Existing URL flow ---
    media_path = download_media(target)
    if not media_path:
        sys.exit(1)
    final_path = save_to_correct_folder(media_path)
    run_inference(final_path)

if __name__ == "__main__":
    main()