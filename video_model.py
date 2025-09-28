import cv2
import sys
import os
import statistics
import torch
from PIL import Image
from transformers import ViTForImageClassification, ViTImageProcessor
import mediapipe as mp

MODEL_NAME = "prithivMLmods/Deep-Fake-Detector-v2-Model"
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print(f"[INFO] Loading Video DeepFake Detector v2 from {MODEL_NAME} on {device}...")
processor = ViTImageProcessor.from_pretrained(MODEL_NAME)
model = ViTForImageClassification.from_pretrained(MODEL_NAME).to(device)
model.eval()

# Explicit label mapping
model.config.id2label = {0: "Deepfake", 1: "Realism"}
model.config.label2id = {"Deepfake": 0, "Realism": 1}

# Init MediaPipe face detector
mp_face_detection = mp.solutions.face_detection
face_detector = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)


def extract_faces(frame):
    """Detect and crop faces from a frame using MediaPipe"""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_detector.process(rgb)

    faces = []
    if results.detections:
        h, w, _ = frame.shape
        for detection in results.detections:
            bboxC = detection.location_data.relative_bounding_box
            x, y, bw, bh = (
                int(bboxC.xmin * w),
                int(bboxC.ymin * h),
                int(bboxC.width * w),
                int(bboxC.height * h),
            )
            # Ensure valid cropping region
            x, y = max(0, x), max(0, y)
            bw, bh = max(1, bw), max(1, bh)
            crop = frame[y:y+bh, x:x+bw]
            if crop.size > 0:
                faces.append(crop)
    return faces


def predict_video(video_path, num_samples=25):
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames == 0:
        print("[ERROR] No frames found in video.")
        return None

    # Dynamic sampling: pick evenly spaced frames
    step = max(1, total_frames // num_samples)

    realism_scores, deepfake_scores = [], []
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % step == 0:
            faces = extract_faces(frame)

            if not faces:  # fallback: use full frame
                faces = [frame]

            for face in faces:
                image = Image.fromarray(cv2.cvtColor(face, cv2.COLOR_BGR2RGB)).resize((224, 224))
                inputs = processor(images=image, return_tensors="pt").to(device)

                with torch.no_grad():
                    outputs = model(**inputs)
                    probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

                realism_scores.append(probs[0, model.config.label2id["Realism"]].item())
                deepfake_scores.append(probs[0, model.config.label2id["Deepfake"]].item())

        frame_count += 1

    cap.release()

    # Aggregate results with median for robustness
    Real = float(statistics.median(realism_scores)) if realism_scores else 0.0
    Deepfake = float(statistics.median(deepfake_scores)) if deepfake_scores else 0.0

    THRESHOLD = 0.2149
    if Deepfake >= THRESHOLD:
        label = "FAKE"
        print(f"[RESULT] {os.path.basename(video_path)} → {label} (Deepfake: {Deepfake:.4f})")
        return label, None, Deepfake
    else:
        label = "REAL"
        print(f"[RESULT] {os.path.basename(video_path)} → {label} (Realism: {Real:.4f})")
        return label, Real, None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python video_model.py <video_path>")
        sys.exit(1)

    video_path = sys.argv[1]
    predict_video(video_path)