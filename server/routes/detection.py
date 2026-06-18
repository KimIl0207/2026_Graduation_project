from typing import Union

from fastapi import APIRouter, File, HTTPException, UploadFile

from schemas import (
    ErrorResponse,
    ImagePredictionResponse,
    TextDetectionResponse,
    TextRequest,
    VideoPredictionResponse,
)
from service.predict import predict_image, predict_images
from state import get_text_detector, models_dict


router = APIRouter()


@router.post(
    "/predict",
    response_model=Union[ImagePredictionResponse, ErrorResponse],
    response_model_exclude_none=True,
    summary="Analyze image AI suspicious score",
    tags=["Image Detection"],
)
async def predict(file: UploadFile = File(...)):
    image_bytes = await file.read()
    result = predict_image(image_bytes, models_dict)
    if "error" not in result:
        result = {
            "filename": file.filename,
            **result,
        }
    return result


@router.post("/predict-frame")
async def predict_frame(file: UploadFile = File(...)):
    image_bytes = await file.read()
    return predict_image(image_bytes, models_dict, mode="video", include_grad_cam=False)


@router.post(
    "/predict_images",
    response_model=VideoPredictionResponse,
    response_model_exclude_none=True,
    summary="Analyze uploaded frame images",
    tags=["Video Detection"],
)
async def predict_frame_images(files: list[UploadFile] = File(...)):
    image_bytes_list = [await file.read() for file in files]
    average_suspicious_score = predict_images(image_bytes_list, models_dict)
    label = "Suspicious AI-like Video" if average_suspicious_score >= 0.5 else "Likely Real Video"

    return {
        "label": label,
        "suspicious_score": round(average_suspicious_score, 4),
        "frame_count": len(image_bytes_list),
    }


@router.post(
    "/detect",
    response_model=TextDetectionResponse,
    response_model_exclude_none=True,
    summary="Analyze text AI probability",
    tags=["Text Detection"],
)
async def detect_text(request: TextRequest):
    if not request.text or len(request.text.strip()) < 10 or len(request.text) > 2000:
        raise HTTPException(
            status_code=400,
            detail="Text must be between 10 and 2000 characters.",
        )

    try:
        detector = get_text_detector()
        return detector.detect(request.text)
    except Exception as e:
        print(f"Text detection failed: {e}")
        raise HTTPException(status_code=500, detail="Text detection failed.")
