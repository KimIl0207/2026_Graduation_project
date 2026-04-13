from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ai_text_detector_engine import AITextDetector
import uvicorn
import time

# [1] 서버 시작 시 모델을 메모리에 딱 한 번만 로드합니다.
# 이 과정은 모델 용량에 따라 수 초에서 수십 초가 소요될 수 있습니다.
print("🚀 [시스템] AI 탐지 모델을 메모리에 로드 중입니다... (최초 1회)")
start_time = time.time()
detector = AITextDetector()
end_time = time.time()
print(f"✅ [시스템] 모델 로드 완료! (소요 시간: {end_time - start_time:.2f}초)")

app = FastAPI(
    title="AI Text Detector API",
    description="XLM-RoBERTa + PPL Hybrid Engine",
    version="1.0.0"
)

# 클라이언트로부터 받을 데이터 구조 정의
class TextRequest(BaseModel):
    text: str

@app.get("/")
async def health_check():
    return {"status": "online", "message": "AI Text Detector API is ready."}

@app.post("/detect")
async def detect_text(request: TextRequest):
    """
    텍스트를 분석하여 AI 작성 확률 및 통계 데이터를 반환합니다.
    """
    if not request.text or len(request.text.strip()) < 10:
        raise HTTPException(
            status_code=400, 
            detail="텍스트가 너무 짧습니다. 최소 10자 이상 입력해주세요."
        )
    
    try:
        # 이미 메모리에 로드된 detector를 사용하여 즉시 결과 반환
        result = detector.detect(request.text)
        return result
    except Exception as e:
        print(f"❌ [오류] 분석 중 에러 발생: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 연산 중 오류가 발생했습니다.")

if __name__ == "__main__":
    # 서버 실행 (포트 8000번)
    # 실제 배포 시에는 host="0.0.0.0"으로 설정하여 외부 접속을 허용합니다.
    uvicorn.run(app, host="0.0.0.0", port=8000)
