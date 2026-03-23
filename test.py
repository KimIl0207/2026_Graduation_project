from fastapi import FastAPI, UploadFile, File, Form
from PIL import Image
import io
import os
from datetime import datetime
import shutil

import torch
import torch.nn as nn
from torchvision import models, transforms
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = ["http://localhost:3001"]
CNN_MODEL_PATH = "./model/best_efficientnet_b0_v2.pth"

# 틀린 데이터 저장 폴더
CORRECTION_SAVE_DIR = "./corrections"
REAL_DIR = os.path.join(CORRECTION_SAVE_DIR, "real")
FAKE_DIR = os.path.join(CORRECTION_SAVE_DIR, "fake")

os.makedirs(REAL_DIR, exist_ok=True)
os.makedirs(FAKE_DIR, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cnn_model = models.efficientnet_b0(weights="DEFAULT")
cnn_model.classifier[1] = nn.Linear(1280, 1)
cnn_model.load_state_dict(torch.load(CNN_MODEL_PATH, map_location="cpu"))
cnn_model.eval()

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])


@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    image_bytes = await file.read()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    input_tensor = transform(image).unsqueeze(0)

    with torch.no_grad():
        output = cnn_model(input_tensor)
        prob = torch.sigmoid(output).item()

    label = "AI Generated" if prob >= 0.5 else "Real Image"

    return {
        "filename": file.filename,
        "label": label,
        "probability": round(prob, 4)
    }


@app.post("/save-correction")
async def save_correction(
    file: UploadFile = File(...),
    correct_label: str = Form(...)
):
    if correct_label not in ["real", "fake"]:
        return {"success": False, "message": "correct_label must be 'real' or 'fake'"}

    save_dir = REAL_DIR if correct_label == "real" else FAKE_DIR    

    original_name = file.filename or "uploaded_image"
    base_name, ext = os.path.splitext(original_name)

    if not ext:
        ext = ".jpg"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    save_name = f"{base_name}_{timestamp}{ext}"
    save_path = os.path.join(save_dir, save_name)

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "success": True,
        "message": f"Saved to {correct_label} folder",
        "saved_path": save_path
    }