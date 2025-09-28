import torch
import sys
import os
from PIL import Image
from transformers import ViTForImageClassification, ViTImageProcessor

MODEL_NAME = "prithivMLmods/Deep-Fake-Detector-v2-Model"
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print(f"[INFO] Loading DeepFake Detector v2 from {MODEL_NAME} on {device}...")
processor = ViTImageProcessor.from_pretrained(MODEL_NAME)
model = ViTForImageClassification.from_pretrained(MODEL_NAME).to(device)
model.eval()

model.config.id2label = {0: "Deepfake", 1: "Realism"}
model.config.label2id = {"Deepfake": 0, "Realism": 1}

id2label = model.config.id2label
label2id = model.config.label2id

print(f"[INFO] Model labels: {id2label}")

def predict_image(img_path):
    if not os.path.exists(img_path):
        raise FileNotFoundError(f"Image not found: {img_path}")

    image = Image.open(img_path).convert("RGB").resize((224, 224))
    inputs = processor(images=image, return_tensors="pt").to(device)

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

    results = {id2label[i]: float(probs[0, i].item()) for i in range(len(probs[0]))}

    realism_conf = results.get("Realism", 0.0)
    deepfake_conf = results.get("Deepfake", 0.0)

    THRESHOLD = 0.25
    if deepfake_conf >= THRESHOLD:
        label = "FAKE"
        print(f"[RESULT] {os.path.basename(img_path)} → {label} (Deepfake: {deepfake_conf:.4f})")
        return label, realism_conf, deepfake_conf
    else:
        label = "REAL"
        print(f"[RESULT] {os.path.basename(img_path)} → {label} (Realism: {realism_conf:.4f})")
        return label, realism_conf, deepfake_conf

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python image_model.py <image_path>")
        sys.exit(1)