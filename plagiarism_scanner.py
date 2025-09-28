import os
import re
import requests
from bs4 import BeautifulSoup
from docx import Document
from dotenv import load_dotenv
import nltk

# Ensure punkt is available
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt")

# ---------------------------
# Config
# ---------------------------
load_dotenv()

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

# ---------------------------
# File extractor
# ---------------------------
def extract_docx(file_path):
    doc = Document(file_path)
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])

# ---------------------------
# Helpers
# ---------------------------
def normalize(s: str) -> str:
    return re.sub(r"\W+", " ", s).lower().strip()

def token_overlap_ratio(a: str, b: str) -> float:
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if not a_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens)

def split_paragraphs(text: str):
    raw_paragraphs = text.split("\n")
    paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]
    return paragraphs


# ---------------------------
# Brave Search
# ---------------------------
def make_queries(paragraph):
    queries = []
    para_clean = " ".join(paragraph.split())
    words = para_clean.split()

    queries.append(para_clean)
    queries.append(para_clean[:200])
    queries.append(" ".join(words[:20]))
    queries.append(" ".join(words[-20:]))
    if len(words) > 40:
        mid = len(words) // 2
        queries.append(" ".join(words[mid:mid+20]))

    return list(set(q for q in queries if q.strip()))

def web_verify(paragraph, max_results=10):
    queries = make_queries(paragraph)

    for q in queries:
        headers = {"X-Subscription-Token": BRAVE_API_KEY}
        params = {"q": q, "count": max_results}

        try:
            resp = requests.get(BRAVE_URL, headers=headers, params=params, timeout=10).json()
            if "web" not in resp or "results" not in resp["web"]:
                continue

            for item in resp["web"]["results"][:max_results]:
                link = item.get("url")
                if not link:
                    continue

                try:
                    page = requests.get(link, timeout=10).text
                    soup = BeautifulSoup(page, "html.parser")
                    text = normalize(soup.get_text(separator=" ", strip=True))

                    words_q = set(q.split())
                    if len(words_q) < 15:
                        return "ORIGINAL", None

                    if token_overlap_ratio(normalize(q), text) >= 0.9:
                        return "PLAGIARISM (exact)", link
                    elif token_overlap_ratio(normalize(q), text) >= 0.7:
                        return "PLAGIARISM (paraphrase)", link

                except Exception:
                    continue
        except Exception as e:
            print("[ERROR] Brave search failed:", e)

    return "ORIGINAL", None

# ---------------------------
# Core scan logic
# ---------------------------
def _scan_paragraphs(paragraphs):
    results = []
    plagiarized = exact = paraphrase = 0

    for idx, para in enumerate(paragraphs, 1):
        label, source = web_verify(para)
        results.append({"paragraph": para, "label": label, "web_source": source})

        if label.startswith("PLAGIARISM"):
            plagiarized += 1
            if "exact" in label:
                exact += 1
            elif "paraphrase" in label:
                paraphrase += 1

    total = len(results)
    original = total - plagiarized

    summary = {
    "total": total,
    "plagiarized": plagiarized,
    "exact": exact,
    "paraphrase": paraphrase,
    "original": original,
    "plag_percent": int(round((plagiarized / total * 100))) if total > 0 else 0,
    "exact_percent": int(round((exact / total * 100))) if total > 0 else 0,
    "paraphrase_percent": int(round((paraphrase / total * 100))) if total > 0 else 0,
    "original_percent": int(round((original / total * 100))) if total > 0 else 0,
}

    return results, summary

def scan_file(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    text = extract_docx(file_path)
    paragraphs = split_paragraphs(text)
    return _scan_paragraphs(paragraphs)

def scan_text(text: str):
    paragraphs = split_paragraphs(text)
    return _scan_paragraphs(paragraphs)

# ---------------------------
# CLI
# ---------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Brave Search Plagiarism Checker")
    parser.add_argument("file", type=str, nargs="?", help="Path to the DOCX file")
    parser.add_argument("--text", type=str, help="Raw text to scan instead of file")
    args = parser.parse_args()

    if args.text:
        results, summary = scan_text(args.text)
    elif args.file:
        results, summary = scan_file(args.file)
    else:
        print("Usage: python plagiarism_scanner.py <file.docx> OR --text 'your text here'")
        sys.exit(1)