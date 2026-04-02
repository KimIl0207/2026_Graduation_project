from fastapi import FastAPI, UploadFile, File, Form
from PIL import Image
import io
import os
from datetime import datetime
import shutil
import time

import torch
import torch.nn as nn
from torchvision import models, transforms
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
# CORS 설정
origins = [
    "http://localhost:3001",
    "http://localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 모델 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sd_model_PATH = os.path.join(BASE_DIR, "model", "best_efficientnet_b0_Diffusion.pth")
midjourney_model_path = os.path.join(BASE_DIR, "model", "best_efficientnet_b0_Midjourney.pth")
biggan_model_path = os.path.join(BASE_DIR, "model", "best_efficientnet_b0_BigGAN.pth")

sd_model = models.efficientnet_b0(weights=None)
sd_model.classifier[1] = nn.Linear(1280, 1)
sd_model.load_state_dict(torch.load(sd_model_PATH, map_location="cpu"))
sd_model.eval()

midjourney_model = models.efficientnet_b0(weights=None)
midjourney_model.classifier[1] = nn.Linear(1280, 1)
midjourney_model.load_state_dict(torch.load(midjourney_model_path, map_location="cpu"))
midjourney_model.eval()

biggan_model = models.efficientnet_b0(weights=None)
biggan_model.classifier[1] = nn.Linear(1280, 1)
biggan_model.load_state_dict(torch.load(biggan_model_path, map_location="cpu"))
biggan_model.eval()

# 틀린 데이터 저장 폴더
CORRECTION_SAVE_DIR = "./corrections"
REAL_DIR = os.path.join(CORRECTION_SAVE_DIR, "real")
FAKE_DIR = os.path.join(CORRECTION_SAVE_DIR, "fake")

os.makedirs(REAL_DIR, exist_ok=True)
os.makedirs(FAKE_DIR, exist_ok=True)


# 이미지 리사이징
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

# 파일 크기 제한
MAX_FILE_SIZE = 10 * 1024 * 1024

@app.get("/")
async def root():
    return {"message": "Server is running"}

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    # 시간 측정 시작
    start_time = time.perf_counter()
    image_bytes = await file.read()

    if len(image_bytes) > MAX_FILE_SIZE:
        return {"error": "File size exceeds the 10MB limit."}
    
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if image.width > 4096 or image.height > 4096:
        return {"error": "Image resolution must not exceed 4096x4096 pixels."}
    
    image = image.resize((224, 224))
    input_tensor = transform(image).unsqueeze(0)

    with torch.no_grad():
        sd_output = sd_model(input_tensor)
        sd_prob = torch.sigmoid(sd_output).item()

        mj_output = midjourney_model(input_tensor)
        mj_prob = torch.sigmoid(mj_output).item()

        bg_ouput = biggan_model(input_tensor)
        bg_prob = torch.sigmoid(bg_ouput).item()

    end_time = time.perf_counter()

    prob = max(sd_prob, mj_prob, bg_prob)
    scores = {
        "Diffusion": sd_prob,
        "Midjourney": mj_prob,
        "BigGAN": bg_prob
    }
    generator_model = max(scores, key=scores.get) if prob > 0.5 else "Not an ai"

    label = "AI Generated" if prob >= 0.5 else "Real Image"
    # 시간 측정 종료
    print(f"소요시간: {end_time - start_time}")
    print(f"sd:{sd_prob}\nmj:{mj_prob}\nbg:{bg_prob}")

    return {
        "filename": file.filename,
        "label": label,
        "probability": round(prob, 4),
        "generator_model": generator_model,
        "probs": {
            "sd": sd_prob,
            "mj": mj_prob,
            "bg": bg_prob
        }
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("test:app", host="0.0.0.0", port=port)