from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
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
    
    
from fastapi import Request # 파일 상단 import 부분에 추가해주세요
import aiohttp # 파일 상단 import 부분에 추가해주세요

# ---------------------------------------------------------
# [추가할 부분] 카카오톡 챗봇 전용 API 엔드포인트
# ---------------------------------------------------------

# 카카오 카드 응답을 만들어주는 헬퍼 함수 (재사용 목적)
def _build_kakao_card(title: str, description: str):
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "basicCard": {
                        "title": title,
                        "description": description,
                        "buttons": [
                            {
                                "action": "message",
                                "label": "처음으로 돌아가기",
                                "messageText": "메뉴"
                            }
                        ]
                    }
                }
            ]
        }
    }

# 1. 텍스트 판별용 스킬 서버
@app.post("/kakao/detect/text")
async def kakao_detect_text(request: Request):
    kakao_data = await request.json()
    
    # 카카오에서 보낸 발화 내용(사용자가 입력한 텍스트) 추출
    user_request = kakao_data.get("userRequest", {})
    user_text = user_request.get("utterance", "")

    # 글자 수 체크 (기존 로직과 동일하게 유지)
    if not user_text or len(user_text.strip()) < 10:
        return _build_kakao_card("오류", "텍스트가 너무 짧습니다. 10자 이상 입력해주세요.")

    try:
        # 기존 AI 엔진(AITextDetector) 실행
        detector = get_text_detector()
        raw_result = detector.detect(user_text)
        
        # ⭐ 주의: raw_result가 어떤 형태(Dict)로 나오는지에 따라 아래 코드를 수정해야 합니다!
        # 예시로, raw_result가 {"ai_probability": 85.5, "label": "AI Generated"} 라고 가정했습니다.
        ai_prob = raw_result.get("ai_probability", 0) # 엔진 결과값 키에 맞춰 수정하세요!
        
        description = f"입력하신 텍스트가 AI로 작성되었을 확률은 [{ai_prob}%] 입니다.\n\n▶ 원문: {user_text[:15]}..."
        
        # 카카오 규격으로 리턴
        return _build_kakao_card("💡 텍스트 판별 결과", description)

    except Exception as e:
        print(f"Kakao Text detection failed: {e}")
        return _build_kakao_card("오류 발생", "서버 분석 중 오류가 발생했습니다.")
    
@app.post("/kakao/detect/image")
async def kakao_detect_image(request: Request):
    kakao_data = await request.json()
    
    try:
        # 1. 카카오가 보낸 데이터에서 '이미지 URL' 추출
        # 카카오는 이미지를 'secureUrls'라는 곳에 담아 보냅니다.
        action = kakao_data.get("action", {})
        detail_params = action.get("detailParams", {})
        
        # 'secureimage' 부분은 카카오 오픈빌더 파라미터 설정에 따라 다를 수 있습니다.
        # 기본적으로 이미지가 업로드되면 이 키 값에 담깁니다.
        image_param = detail_params.get("secureimage", {})
        
        # 혹시 몰라 utterance(사용자가 보낸 원문)에서도 URL을 찾아봅니다.
        user_text = kakao_data.get("userRequest", {}).get("utterance", "")
        
        image_url = None
        if "secureUrls" in image_param:
             image_url = image_param["secureUrls"]
        elif user_text.startswith("http"):
             image_url = user_text

        # 이미지가 제대로 안 들어왔을 경우
        if not image_url:
            return _build_kakao_card("오류", "이미지 URL을 찾을 수 없습니다. 정상적인 이미지 파일인지 확인해 주세요.")

        # 2. 이미지 URL에서 실제 이미지 파일 다운로드 (비동기 처리)
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                     return _build_kakao_card("다운로드 실패", "카카오 서버에서 이미지를 가져오지 못했습니다.")
                
                # 이미지를 바이트 형태로 읽어옴
                image_bytes = await resp.read()

        # 3. 기존 AI 엔진(predict_image) 실행
        # (models_dict는 기존 코드 상단에 로드되어 있다고 가정합니다)
        raw_result = predict_image(image_bytes, models_dict)
        
        # ⭐ 주의: raw_result 딕셔너리의 Key 값에 맞춰 수정하세요!
        # 기존 로직이 어떤 값을 뱉는지 몰라 임의로 get()을 사용했습니다.
        predicted_label = raw_result.get("predicted_label", "판별 불가")
        predicted_probability = raw_result.get("predicted_probability", 0)
        
        # 확률값을 퍼센트로 변환 (예: 0.85 -> 85%)
        ai_prob_percent = int(float(predicted_probability) * 100)

        description = f"💡 분석 결과: {predicted_label}\n\n해당 이미지가 AI로 생성되었을 확률은 [{ai_prob_percent}%] 입니다."
        
        # 카카오 규격으로 리턴
        return _build_kakao_card("🖼️ 이미지 판별 결과", description)

    except Exception as e:
        print(f"Kakao Image detection failed: {e}")
        return _build_kakao_card("오류 발생", f"이미지 분석 중 오류가 발생했습니다. ({e})")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
