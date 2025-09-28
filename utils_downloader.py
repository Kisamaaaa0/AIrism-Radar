import os
from pathlib import Path
from urllib.parse import urlparse
import mimetypes
import yt_dlp

DATA_DIR = Path("data")
IMAGE_DIR = DATA_DIR / "images"
VIDEO_DIR = DATA_DIR / "videos"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

def detect_platform(url: str) -> str:
    domain = urlparse(url).netloc.lower()
    if "facebook.com" in domain:
        return "facebook"
    if "twitter.com" in domain or "x.com" in domain:
        return "twitter"
    if "youtube.com" in domain or "youtu.be" in domain:
        return "youtube"
    return "unknown"

def download_with_ytdlp(url: str, save_dir: Path) -> Path | None:
    ydl_opts = {
        "outtmpl": str(save_dir / "%(title).50s.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
        "merge_output_format": "mp4",
        "quiet": True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return Path(filename)

def download_media(url: str) -> Path | None:
    platform = detect_platform(url)
    if platform in ("youtube", "facebook", "twitter"):
        try:
            return download_with_ytdlp(url, VIDEO_DIR)
        except Exception as e:
            print(f"[ERROR] yt-dlp failed: {e}")
            return None
    return None

def get_media_type(file_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(file_path))
    if mime:
        if mime.startswith("image"):
            return "image"
        if mime.startswith("video"):
            return "video"
    return "unknown"
