from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile

from schemas import SaveCorrectionResponse
from util.save_correction import save_correction_file


router = APIRouter()


@router.post(
    "/save-correction",
    response_model=SaveCorrectionResponse,
    response_model_exclude_none=True,
    summary="Save image correction data",
    tags=["Correction"],
)
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
