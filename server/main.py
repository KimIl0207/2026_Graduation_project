import os
from typing import List, Optional, Union
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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


class ErrorResponse(BaseModel):
    error: str = Field(..., description="요청 처리 중 발생한 오류 메시지")


class RootResponse(BaseModel):
    message: str = Field(..., description="서버 상태 메시지")


class ModelProbs(BaseModel):
    sd: float = Field(..., description="Stable Diffusion detector의 sigmoid 확률값")
    mj: float = Field(..., description="Midjourney detector의 sigmoid 확률값")
    bg: float = Field(..., description="BigGAN detector의 sigmoid 확률값")


class PredictionSignals(BaseModel):
    model_fusion: float = Field(..., description="3개 모델 확률을 합성한 최종 suspicious_score")
    model_disagreement: float = Field(..., description="모델 간 불일치도. max(prob) - min(prob)")


class GradCamResponse(BaseModel):
    model: str = Field(..., description="Grad-CAM 설명에 사용된 모델 키")
    image_base64: str = Field(..., description="PNG Grad-CAM overlay 이미지의 base64 문자열")
    note: str = Field(..., description="Grad-CAM 해석 안내 문구")


class ImagePredictionResponse(BaseModel):
    filename: str = Field(..., description="업로드된 원본 파일명")
    label: str = Field(..., description="최종 판정 라벨")
    suspicious_score: float = Field(..., description="AI-like 의심 점수. 0에 가까울수록 실제 이미지, 1에 가까울수록 AI 의심")
    confidence: str = Field(..., description="판정 신뢰도. high, medium, low 중 하나")
    model_probs: ModelProbs = Field(..., description="생성기별 detector 원본 확률값")
    signals: PredictionSignals = Field(..., description="최종 판단에 사용한 보조 신호")
    grad_cam: Optional[GradCamResponse] = Field(None, description="선택 모델 기준 Grad-CAM 설명 이미지")


class VideoPredictionResponse(BaseModel):
    label: str = Field(..., description="동영상 최종 판정 라벨")
    suspicious_score: float = Field(..., description="분석 프레임 suspicious_score의 평균값")
    frame_count: int = Field(..., description="분석에 사용된 프레임 수")
    frame_predictions: Optional[List[float]] = Field(None, description="프레임별 suspicious_score 목록")


class TextDetectionResponse(BaseModel):
    language: Optional[str] = Field(None, description="주요 감지 언어. ko 또는 en")
    roberta_ai_prob: Optional[float] = Field(None, description="XLM-RoBERTa 기반 AI 확률. 0~100")
    final_ai_prob: Optional[float] = Field(None, description="최종 AI 작성 확률. 0~100")
    decision: Optional[str] = Field(None, description="최종 판정. AI, Human, Uncertain 중 하나")
    burstiness: Optional[float] = Field(None, description="문장 길이 변동성 지표")
    perplexity: Optional[float] = Field(None, description="언어 모델 perplexity 평균값")
    burst_score: Optional[float] = Field(None, description="burstiness를 정규화한 AI 점수")
    ppl_score: Optional[float] = Field(None, description="perplexity를 정규화한 AI 점수")


class SaveCorrectionResponse(BaseModel):
    success: bool = Field(..., description="보정 데이터 저장 성공 여부")
    message: str = Field(..., description="저장 처리 결과 메시지")
    saved_path: Optional[str] = Field(None, description="저장된 파일 경로")


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

models_dict = load_models()
text_detector = None
detector = get_text_detector()
# 파일 크기 제한
MAX_FILE_SIZE = 10 * 1024 * 1024

@app.get(
    "/",
    response_model=RootResponse,
    summary="서버 상태 확인",
    tags=["Health"],
)
async def root():
    return {"message": "Server is running"}

@app.post(
    "/predict",
    response_model=Union[ImagePredictionResponse, ErrorResponse],
    response_model_exclude_none=True,
    summary="이미지 AI 의심 점수 분석",
    description=(
        "업로드한 이미지 1장을 Stable Diffusion, Midjourney, BigGAN detector로 분석한 뒤 "
        "3개 모델의 sigmoid 확률을 합성해 최종 suspicious_score를 반환합니다. "
        "model_probs는 개별 모델 출력값이고, signals는 모델 합성 점수와 모델 간 불일치도입니다."
    ),
    tags=["Image Detection"],
    responses={
        200: {
            "description": "이미지 분석 성공 또는 검증 오류",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "분석 성공",
                            "value": {
                                "filename": "sample.jpg",
                                "label": "Suspicious AI-like Image",
                                "suspicious_score": 0.684,
                                "confidence": "medium",
                                "model_probs": {
                                    "sd": 0.71,
                                    "mj": 0.32,
                                    "bg": 0.18,
                                },
                                "signals": {
                                    "model_fusion": 0.684,
                                    "model_disagreement": 0.53,
                                },
                                "grad_cam": {
                                    "model": "sd",
                                    "image_base64": "iVBORw0KGgo...",
                                    "note": "Highlighted areas contributed most to the selected AI-generator score.",
                                },
                            },
                        },
                        "too_small": {
                            "summary": "이미지가 너무 작은 경우",
                            "value": {
                                "error": "Image is too small. Minimum size is 224x224 pixels."
                            },
                        },
                    }
                }
            },
        }
    },
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

@app.post(
    "/predict-video",
    response_model=Union[VideoPredictionResponse, ErrorResponse],
    response_model_exclude_none=True,
    summary="동영상 AI 의심 점수 분석",
    description=(
        "업로드한 동영상에서 프레임을 추출하고 각 프레임의 suspicious_score를 계산한 뒤 "
        "평균 점수로 동영상 전체의 AI-like 의심 점수를 반환합니다."
    ),
    tags=["Video Detection"],
    responses={
        200: {
            "description": "동영상 분석 결과",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "분석 성공",
                            "value": {
                                "label": "Suspicious AI-like Video",
                                "suspicious_score": 0.6123,
                                "frame_count": 5,
                                "frame_predictions": [0.58, 0.64, 0.61, 0.69, 0.54],
                            },
                        },
                        "no_frames": {
                            "summary": "프레임 추출 실패",
                            "value": {
                                "error": "No frames extracted from the video."
                            },
                        },
                    }
                }
            },
        }
    },
)
async def predict_video(file: UploadFile = File(...)):
    result = await predict_video_file(file, models_dict)
    return result


@app.post(
    "/predict_images",
    response_model=VideoPredictionResponse,
    response_model_exclude_none=True,
    summary="여러 이미지 프레임 평균 분석",
    description=(
        "여러 이미지 파일을 프레임처럼 받아 각 이미지의 suspicious_score를 계산하고 "
        "평균값으로 영상성 콘텐츠의 의심 점수를 반환합니다."
    ),
    tags=["Video Detection"],
    responses={
        200: {
            "description": "프레임 이미지 평균 분석 결과",
            "content": {
                "application/json": {
                    "example": {
                        "label": "Likely Real Video",
                        "suspicious_score": 0.2415,
                        "frame_count": 4,
                    }
                }
            },
        }
    },
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


@app.post(
    "/save-correction",
    response_model=SaveCorrectionResponse,
    response_model_exclude_none=True,
    summary="이미지 예측 정답 보정 저장",
    description=(
        "이미지 분석 결과가 틀렸을 때 사용자가 지정한 정답 라벨(real 또는 fake)과 "
        "예측 당시의 점수 정보를 함께 저장합니다. 저장된 데이터는 추후 모델 개선용으로 사용할 수 있습니다."
    ),
    tags=["Correction"],
    responses={
        200: {
            "description": "보정 데이터 저장 결과",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "저장 성공",
                            "value": {
                                "success": True,
                                "message": "Saved to real folder",
                                "saved_path": "C:/project/server/corrections/real/sample_20260523_123456.jpg",
                            },
                        },
                        "invalid_label": {
                            "summary": "잘못된 correct_label",
                            "value": {
                                "success": False,
                                "message": "correct_label must be 'real' or 'fake'",
                            },
                        },
                    }
                }
            },
        }
    },
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


@app.post(
    "/detect",
    response_model=TextDetectionResponse,
    response_model_exclude_none=True,
    summary="텍스트 AI 작성 확률 분석",
    description=(
        "입력 텍스트를 XLM-RoBERTa 기반 분류 점수와 문장 변동성, perplexity 신호를 함께 사용해 분석합니다. "
        "final_ai_prob는 최종 AI 작성 확률(0~100)이며, decision은 AI/Human/Uncertain 중 하나입니다."
    ),
    tags=["Text Detection"],
    responses={
        200: {
            "description": "텍스트 분석 결과",
            "content": {
                "application/json": {
                    "examples": {
                        "full_result": {
                            "summary": "일반 분석 결과",
                            "value": {
                                "language": "ko",
                                "roberta_ai_prob": 82.41,
                                "final_ai_prob": 76.23,
                                "decision": "AI",
                                "burstiness": 4.12,
                                "perplexity": 31.8,
                                "burst_score": 87.73,
                                "ppl_score": 70.66,
                            },
                        },
                        "shortcut_result": {
                            "summary": "RoBERTa 점수가 극단적인 경우",
                            "value": {
                                "language": "en",
                                "roberta_ai_prob": 99.8,
                                "final_ai_prob": 99.8,
                                "decision": "AI",
                            },
                        },
                    }
                }
            },
        },
        400: {
            "description": "텍스트 길이가 너무 짧은 경우",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Text must be at least 10 characters."
                    }
                }
            },
        },
        500: {
            "description": "텍스트 분석 서버 내부 오류",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Text detection failed."
                    }
                }
            },
        },
    },
)
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
            prob = result.get("suspicious_score", 0)
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
            prob = result.get("suspicious_score", 0)

            # 새 suspicious score 구조에서는 생성기 추정보다 confidence를 안내한다.
            confidence = result.get("confidence", "")
            confidence_text = f"\nConfidence: {confidence}" if confidence else ""

            text = (
                f"🖼️ 이미지 판독 결과\n\n"
                f"판정: {label}\n"
                f"확률: {prob:.2f}"
                f"{confidence_text}\n\n"
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
