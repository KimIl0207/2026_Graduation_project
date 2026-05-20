import os
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from util.save_correction import save_correction_file
from service.ai_text_detector_engine import AITextDetector
from service.model_loader import load_models
from service.predict import predict_image, predict_images
from service.predic_video import predict_video as predict_video_file
from util.kakao import (
    kakao_response,
    find_image_url,
    find_video_url,
    download_image_bytes,
    download_video_bytes,
    QUICK_REPLY_RESTART,
)

app = FastAPI(
    title="AI Detection API",
    description="Image and text AI detection server",
    version="1.0.0",
)
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


class TextRequest(BaseModel):
    text: str


class InMemoryUploadFile:
    def __init__(self, content: bytes, filename: str):
        self._content = content
        self.filename = filename

    async def read(self) -> bytes:
        return self._content


def get_text_detector():
    global text_detector

    if text_detector is None:
        text_detector = AITextDetector()

    return text_detector

# 파일 크기 제한

models_dict = load_models()
text_detector = None
detector = get_text_detector()
MAX_FILE_SIZE = 10 * 1024 * 1024

@app.get("/")
async def root():
    return {"message": "Server is running"}

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    image_bytes = await file.read()
    result = predict_image(image_bytes, models_dict)
    return result


@app.post("/predict-frame")
async def predict_frame(file: UploadFile = File(...)):
    image_bytes = await file.read()
    return predict_image(image_bytes, models_dict, mode="video", include_grad_cam=False)

@app.post("/predict-video")
async def predict_video(file: UploadFile = File(...)):
    result = await predict_video_file(file, models_dict)
    return result


@app.post("/predict_images")
async def predict_frame_images(files: list[UploadFile] = File(...)):
    image_bytes_list = [await file.read() for file in files]
    average_probability = predict_images(image_bytes_list, models_dict)
    label = "AI Generated Video" if average_probability >= 0.5 else "Real Video"

    return {
        "label": label,
        "probability": round(average_probability, 4),
        "frame_count": len(image_bytes_list),
    }


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


@app.post("/detect")
async def detect_text(request: TextRequest):
    if not request.text or len(request.text.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="Text must be at least 10 characters."
        )

    try:
        return detector.detect(request.text)
    except Exception as e:
        print(f"Text detection failed: {e}")
        raise HTTPException(status_code=500, detail="Text detection failed.")


@app.post("/kakao/detect")
async def kakao_detect(req: Request):
    body = await req.json()

    utterance = body.get("userRequest", {}).get("utterance", "").strip()
    params = body.get("action", {}).get("params", {})

    # 이미지 파라미터 확인
    video_url = find_video_url(params) or find_video_url(utterance)
    image_url = find_image_url(params) or find_image_url(utterance)

    # print(f"Kakao detect request - Utterance: {utterance}, Params: {params}, Image URL: {image_url}")

    # ── 이미지 판독 ──
    if video_url:
        try:
            video_bytes = await download_video_bytes(video_url)
            filename = os.path.basename(urlparse(video_url).path) or "uploaded_video.mp4"
            video_file = InMemoryUploadFile(video_bytes, filename)
            result = await predict_video_file(video_file, models_dict)

            if "error" in result:
                return kakao_response(f"Video detection failed: {result['error']}", QUICK_REPLY_RESTART)

            label = result.get("label", "Unknown")
            prob = result.get("probability", 0)
            frame_count = result.get("frame_count", 0)

            text = (
                "🎞️비디오 판독 결과\n\n"
                f"판정: {label}\n"
                f"확률: {prob:.2f}\n"
                f"분석된 프레임: {frame_count}\n\n"
                "다른 텍스트, 이미지, 또는 비디오를 보내서 분석해 보세요."
            )
            return kakao_response(text, QUICK_REPLY_RESTART)

        except Exception as e:
            print(f"Kakao video detection error: {e}")
            return kakao_response("Video detection failed. Please try again.", QUICK_REPLY_RESTART)

    if image_url:
        try:
            image_bytes = await download_image_bytes(image_url)
            # print(f"Downloaded image from {image_url} ({len(image_bytes)} bytes)")
            result = predict_image(image_bytes, models_dict)

            label = result.get("label", "알 수 없음")
            prob = result.get("probability", 0)

            # 생성 모델 정보가 있으면 추가
            generator = result.get("generator_model", "")
            generator_text = f"\n생성 모델 추정: {generator}" if generator else ""

            text = (
                f"🖼️ 이미지 판독 결과\n\n"
                f"판정: {label}\n"
                f"확률: {prob:.2f}"
                f"{generator_text}\n\n"
                f"다른 콘텐츠도 판별해 보시겠어요?"
            )
            return kakao_response(text, QUICK_REPLY_RESTART)

        except Exception as e:
            print(f"Kakao image detection error: {e}")
            return kakao_response("이미지 판독 중 오류가 발생했습니다. 다시 시도해 주세요.", QUICK_REPLY_RESTART)

    # ── 텍스트 판독 ──
    if len(utterance) >= 10:
        try:
            detector = get_text_detector()
            result = detector.detect(utterance)

            prob = result.get("final_ai_prob", 0)
            label = "AI가 작성했을 가능성이 높습니다!" if prob > 60 else "사람이 작성했을 가능성이 높습니다."

            text = (
                f"📝 텍스트 판독 결과\n\n"
                f"판정: {label}\n"
                f"확률: {prob:2f}%\n\n"
                f"다른 콘텐츠도 판별해 보시겠어요?"
            )
            return kakao_response(text, QUICK_REPLY_RESTART)

        except Exception as e:
            print(f"Kakao text detection error: {e}")
            return kakao_response("텍스트 판독 중 오류가 발생했습니다. 다시 시도해 주세요.", QUICK_REPLY_RESTART)

    # ── 안내 메시지 ──
    return kakao_response("분석할 텍스트(10자 이상) 또는 이미지를 보내주세요.")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
