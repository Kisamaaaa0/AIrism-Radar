from flask import Flask, render_template, request, jsonify
from flask import url_for
import mimetypes
import shutil
from werkzeug.utils import secure_filename
from pathlib import Path
import os
import cv2  
from urllib.parse import urlparse


# Import from your existing modules
from app import download_media, get_media_type, predict_image, predict_video
from plagiarism_scanner import scan_text, scan_file

# 1️⃣ Create the Flask app
app = Flask(__name__)

# File upload config
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 2️⃣ Define routes
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/deepfake")
def deepfake():
    return render_template("deepfake.html")

@app.route("/plagiarism")
def plagiarism():
    return render_template("plag.html")

# --- Deepfake Detector ---
@app.route("/analyze/url")
def analyze_url():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        # 1. Download media (returns a local path)
        media_path = download_media(url)
        if not media_path:
            return jsonify({"error": "Download failed"}), 500

        # 2. Detect media type
        media_type = get_media_type(media_path)

        # 3. Copy file to static/uploads for preview
        static_preview = Path("static/uploads") / Path(media_path).name
        Path("static/uploads").mkdir(parents=True, exist_ok=True)
        shutil.copy(media_path, static_preview)

        # 4. Build preview URL (not the file itself)
        preview_url = url_for("static", filename=f"uploads/{Path(media_path).name}", _external=True)

        # 5. Run AI model
        if media_type == "image":
            label, realism, deepfake = predict_image(media_path)
        elif media_type == "video":
            label, realism, deepfake = predict_video(media_path)
        else:
            return jsonify({"error": "Unsupported media type"}), 400

        # 6. Return only safe JSON (no binary data)
        return jsonify({
            "domain": urlparse(url).netloc,
            "type": media_type,
            "label": label,
            "realism": realism,
            "deepfake": deepfake,
            "preview": preview_url
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# --- Plagiarism Checker (Text + File Upload) ---
@app.route("/analyze/plag", methods=["POST"])
def analyze_plag():
    try:
        if request.is_json:
            data = request.get_json()
            text = data.get("text", "").strip()
            if not text:
                return jsonify({"error": "No text provided"}), 400

            results, summary = scan_text(text)
            return jsonify({"summary": summary, "results": results})

        if "file" in request.files:
            file = request.files["file"]
            if file.filename == "":
                return jsonify({"error": "No file selected"}), 400

            filename = secure_filename(file.filename)
            filepath = UPLOAD_DIR / filename
            file.save(filepath)

            results, summary = scan_file(filepath)
            return jsonify({"summary": summary, "results": results})

        return jsonify({"error": "No input provided"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# 3️⃣ Run the app
if __name__ == "__main__":
    app.run(debug=True)
