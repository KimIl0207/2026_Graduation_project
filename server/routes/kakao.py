import os
from urllib.parse import urlparse

from fastapi import APIRouter, Request

from adapters import InMemoryUploadFile
from service.predic_video import predict_video as predict_video_file
from service.predict import predict_image
from state import get_text_detector, models_dict
from util.kakao import (
    QUICK_REPLY_RESTART,
    download_image_bytes,
    download_video_bytes,
    find_image_url,
    find_video_url,
    kakao_response,
)


router = APIRouter()


@router.post("/kakao/detect")
async def kakao_detect(req: Request):
    body = await req.json()

    utterance = body.get("userRequest", {}).get("utterance", "").strip()
    params = body.get("action", {}).get("params", {})

    video_url = find_video_url(params) or find_video_url(utterance)
    image_url = find_image_url(params) or find_image_url(utterance)

    if video_url:
        try:
            video_bytes = await download_video_bytes(video_url)
            filename = os.path.basename(urlparse(video_url).path) or "uploaded_video.mp4"
            video_file = InMemoryUploadFile(video_bytes, filename)
            result = await predict_video_file(video_file, models_dict)

            if "error" in result:
                return kakao_response(f"영상 감지 실패: {result['error']}", QUICK_REPLY_RESTART)

            label = result.get("label", "Unknown")
            prob = result.get("suspicious_score", 0)
            frame_count = result.get("frame_count", 0)

            text = (
                "영상 감지 결과\n\n"
                f"결과: {label}\n"
                f"의심 점수: {prob:.2f}\n"
                f"분석된 프레임: {frame_count}\n\n"
                "다른 텍스트, 이미지, 또는 영상을 보내주세요."
            )
            return kakao_response(text, QUICK_REPLY_RESTART)

        except Exception as e:
            print(f"Kakao video detection error: {e}")
            return kakao_response("영상 감지 실패. 다시 시도해주세요.", QUICK_REPLY_RESTART)

    if image_url:
        try:
            image_bytes = await download_image_bytes(image_url)
            result = predict_image(image_bytes, models_dict)

            label = result.get("label", "Unknown")
            prob = result.get("suspicious_score", 0)
            confidence = result.get("confidence", "")
            confidence_text = f"\nConfidence: {confidence}" if confidence else ""

            text = (
                "이미지 감지 결과\n\n"
                f"결과: {label}\n"
                f"의심 점수: {prob:.2f}"
                f"{confidence_text}\n\n"
                "다른 콘텐츠를 보내주세요."
            )
            return kakao_response(text, QUICK_REPLY_RESTART)

        except Exception as e:
            print(f"Kakao image detection error: {e}")
            return kakao_response("이미지 감지 실패. 다시 시도해주세요.", QUICK_REPLY_RESTART)

    if len(utterance) >= 10:
        try:
            detector = get_text_detector()
            result = detector.detect(utterance)

            prob = result.get("final_ai_prob", 0)
            label = "Likely AI-written" if prob > 60 else "Likely human-written"

            text = (
                "텍스트 감지 결과\n\n"
                f"결과: {label}\n"
                f"확률: {prob:.2f}%\n\n"
                "다른 콘텐츠를 보내주세요."
            )
            return kakao_response(text, QUICK_REPLY_RESTART)

        except Exception as e:
            print(f"Kakao text detection error: {e}")
            return kakao_response("텍스트 감지 실패. 다시 시도해주세요.", QUICK_REPLY_RESTART)

    return kakao_response("10자 이상의 텍스트, 이미지, 또는 영상을 보내주세요.")