import httpx
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
import os

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from util.save_correction import save_correction_file
from service.ai_text_detector_engine import AITextDetector
from service.model_loader import load_models
from service.predict import predict_image
from service.predic_video import predict_video as predict_video_file

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

models_dict = load_models()
text_detector = None


class TextRequest(BaseModel):
    text: str


def get_text_detector():
    global text_detector

    if text_detector is None:
        text_detector = AITextDetector()

    return text_detector

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

@app.post("/predict-video")
async def predict_video(file: UploadFile = File(...)):
    result = await predict_video_file(file, models_dict)
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


@app.post("/detect")
async def detect_text(request: TextRequest):
    if not request.text or len(request.text.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="Text must be at least 10 characters."
        )

    try:
        detector = get_text_detector()
        return detector.detect(request.text)
    except Exception as e:
        print(f"Text detection failed: {e}")
        raise HTTPException(status_code=500, detail="Text detection failed.")
    

# ── 카카오 오픈빌더 통합 스킬 ──

def kakao_response(text: str, quick_replies: list = None):
    """오픈빌더 응답 규격 JSON 생성"""
    body = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}]
        }
    }
    if quick_replies:
        body["template"]["quickReplies"] = quick_replies
    return body


QUICK_REPLY_RESTART = [
    {
        "messageText": "텍스트 분석",
        "action": "message",
        "label": "📝 텍스트 분석"
    },
    {
        "messageText": "이미지 분석",
        "action": "message",
        "label": "🖼️ 이미지 분석"
    }
]


@app.post("/kakao/detect")
async def kakao_detect(req: Request):
    body = await req.json()

    utterance = body.get("userRequest", {}).get("utterance", "").strip()
    params = body.get("action", {}).get("params", {})

    # 이미지 파라미터 확인
    secure_image = params.get("secureimage", "")

    # ── 이미지 판독 ──
    if secure_image:
        try:
            async with httpx.AsyncClient() as client:
                img_resp = await client.get(secure_image, timeout=15)
            result = predict_image(img_resp.content, models_dict)

            label = result.get("predicted_label", "알 수 없음")
            prob = result.get("predicted_probability", 0)

            # 생성 모델 정보가 있으면 추가
            generator = result.get("selected_generator_model", "")
            generator_text = f"\n생성 모델 추정: {generator}" if generator else ""

            text = (
                f"🖼️ 이미지 판독 결과\n\n"
                f"판정: {label}\n"
                f"확률: {prob:.1%}"
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
