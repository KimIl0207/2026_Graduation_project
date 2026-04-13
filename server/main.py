from fastapi import FastAPI, UploadFile, File, Form
import os
import time

from torchvision import transforms
from fastapi.middleware.cors import CORSMiddleware

from server.util.logger import save_log
from server.util.save_correction import save_correction_file
from service.model_loader import load_models
from service.predict import predict_image

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
    correct_label: str = Form(...)
):
    return save_correction_file(file, correct_label)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("test:app", host="0.0.0.0", port=port)
