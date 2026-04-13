from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form
import os

from fastapi.middleware.cors import CORSMiddleware

from server.util.save_correction import save_correction_file
from server.service.model_loader import load_models
from server.service.predict import predict_image

app = FastAPI()
# CORS 설정
origins = [
    "http://localhost:3001",
    "http://localhost:3000",
    "https://6913-210-206-150-26.ngrok-free.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

models_dict = load_models()

# 파일 크기 제한
MAX_FILE_SIZE = 10 * 1024 * 1024

@app.get("/")
async def root():
    return {"message": "Server is running"}

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    image_bytes = await file.read()
    result = predict_image(image_bytes, models_dict)
    return result


@app.post("/save-correction")
async def save_correction(
    file: UploadFile = File(...),
    correct_label: str = Form(...),
    predicted_label: Optional[str] = Form(None),
    predicted_probability: Optional[float] = Form(None),
    selected_generator_model: Optional[str] = Form(None),
    sd_prob: Optional[float] = Form(None),
    mj_prob: Optional[float] = Form(None),
    bg_prob: Optional[float] = Form(None),
):
    prediction = {
        "predicted_label": predicted_label,
        "predicted_probability": predicted_probability,
        "selected_generator_model": selected_generator_model,
        "sd_prob": sd_prob,
        "mj_prob": mj_prob,
        "bg_prob": bg_prob,
        "source": "save-correction",
    }
    return save_correction_file(file, correct_label, prediction)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server.main:app", host="0.0.0.0", port=port)
