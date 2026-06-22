# ADAM 서버 기술명세서

## 1. 개요

ADAM 서버는 이미지, 비디오 프레임, 텍스트 콘텐츠가 AI 생성물인지 판별하기 위한 FastAPI 기반 백엔드이다. 현재 서버의 기본 이미지 판별 방식은 단일 병합 모델이 아니라, 여러 생성 모델별 전문 판별기의 결과를 함께 사용하는 ensemble 구조이다.

서버는 다음 기능을 제공한다.

- 이미지 AI 생성 의심도 판별
- 이미지 Grad-CAM 시각화 생성
- 비디오 프레임 기반 AI 생성 의심도 판별
- 텍스트 AI 작성 의심도 판별 및 문장 단위 하이라이트 정보 제공
- 사용자 보정 데이터 저장
- 카카오 챗봇 연동용 감지 엔드포인트

## 2. 기술스택

| 구분 | 기술 |
|---|---|
| 웹 프레임워크 | FastAPI |
| ASGI 서버 | Uvicorn |
| 모델 런타임 | PyTorch, TorchVision |
| 이미지 처리 | Pillow, OpenCV headless, NumPy |
| 텍스트 모델 | Hugging Face Transformers |
| 텍스트 보조 분석 | NLTK, KoGPT2, GPT-2 |
| 범용 이미지 판별 보조 모델 | UnivFD, CLIP ViT-L/14 |
| 데이터 검증/응답 스키마 | Pydantic |
| 외부 요청 | httpx, requests |
| 환경변수 | python-dotenv |
| 업로드 처리 | python-multipart |

## 3. 서버 엔트리포인트

주 엔트리포인트는 `server/main.py`이다.

```powershell
cd server
python main.py
```

또는:

```powershell
cd server
uvicorn main:app --host 0.0.0.0 --port 8000
```

포트는 환경변수 `PORT`로 변경할 수 있다. 기본값은 `8000`이다.

## 4. 애플리케이션 구조

```text
server/
  main.py                         FastAPI 앱 생성 및 라우터 등록
  state.py                        서버 시작 시 이미지 모델 로드, 텍스트 모델 lazy load
  schemas.py                      API 응답/요청 Pydantic 스키마
  requirements.txt                Python 의존성

  routes/
    health.py                     서버 상태 확인
    detection.py                  이미지/비디오 프레임/텍스트 판별 API
    correction.py                 사용자 보정 데이터 저장 API
    kakao.py                      카카오 챗봇 연동 API

  service/
    model_loader.py               이미지 ensemble 모델 로더
    predict.py                    이미지 추론, 점수 산출, Grad-CAM 생성
    univfd.py                     UnivFD CLIP 기반 보조 판별기
    predic_video.py               카카오용 비디오 파일 처리
    ai_text_detector_engine.py    텍스트 판별 엔진

  util/
    frame_extract.py              비디오 프레임 추출
    save_correction.py            보정 이미지 저장
    logger.py                     보정 로그 기록
    kakao.py                      카카오 메시지/미디어 유틸
```

## 5. 라우터 구성

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/` | 서버 상태 확인 |
| `POST` | `/predict` | 이미지 파일 1장 판별 |
| `POST` | `/predict-frame` | 비디오에서 추출한 프레임 1장 판별 |
| `POST` | `/predict_images` | 여러 프레임 이미지를 받아 평균 비디오 점수 계산 |
| `POST` | `/detect` | 텍스트 AI 작성 의심도 판별 |
| `POST` | `/save-correction` | 사용자 보정 이미지 및 판정 메타데이터 저장 |
| `POST` | `/kakao/detect` | 카카오 챗봇용 통합 감지 |

현재 `/predict-video` API는 제거되어 있다. 웹 프론트의 비디오 판별은 브라우저에서 프레임을 추출한 뒤 `/predict` 또는 `/predict-frame` 흐름을 사용한다.

## 6. 모델 로딩 전략

이미지 모델은 `server/state.py`에서 서버 시작 시 로드된다.

```python
models_dict = load_models()
```

텍스트 모델은 무겁기 때문에 서버 시작 시 바로 로드하지 않고, `/detect` 요청이 처음 들어올 때 lazy load한다.

```python
text_detector = None
```

## 7. 이미지 판별 아키텍처

### 7.1 현재 기본 구조

현재 이미지는 ensemble 방식으로만 판별한다. 병합 모델 방식은 현재 방향성과 맞지 않아 코드와 파일이 제거되었다.

사용 모델:

| 키 | 모델 파일 | 역할 |
|---|---|---|
| `sd` | `best_efficientnet_b0_Diffusion.pth` | Stable Diffusion 계열 흔적 탐지 |
| `mj` | `best_efficientnet_b0_Midjourney_6.pth` | Midjourney 계열 흔적 탐지 |
| `bg` | `best_efficientnet_b0_BigGAN.pth` | BigGAN 계열 흔적 탐지 |
| `sd3` | `best_efficientnet_b0_SD3_finetuned.pth` | Stable Diffusion 3 계열 흔적 탐지 |
| `dalle3` | `best_efficientnet_b0_DALL_E_3_finetuned.pth` | DALL-E 3 계열 흔적 탐지 |
| `univfd` | `univfd_linear.pth` + CLIP ViT-L/14 | UnivFD 범용 fake image detector |

SDXL 모델은 과반응 문제로 현재 ensemble에서 제외되어 있다.

### 7.2 EfficientNet 계열 모델

EfficientNet 기반 판별기는 모두 같은 구조를 사용한다.

```python
torchvision.models.efficientnet_b0(weights=None)
classifier[1] = nn.Linear(1280, 1)
```

출력 logit에 sigmoid를 적용하여 0~1 사이 의심 점수로 변환한다.

### 7.3 UnivFD

UnivFD는 `server/service/univfd.py`에서 로드한다.

- CLIP backbone: `openai/clip-vit-large-patch14`
- Linear head checkpoint: `server/model/univfd_linear.pth`
- 기본 전처리:
  - `CenterCrop(224)`
  - `ToTensor`
  - CLIP mean/std normalize

환경변수로 UnivFD 경로와 CLIP 모델을 바꿀 수 있다.

```powershell
$env:ADAM_UNIVFD_CHECKPOINT="C:\path\to\univfd_linear.pth"
$env:ADAM_UNIVFD_CLIP_MODEL="openai/clip-vit-large-patch14"
```

## 8. 이미지 점수 산출 방식

현재 최종 이미지 의심 점수는 각 detector의 출력 중 가장 높은 값을 그대로 사용한다.

```python
score = max(model_probs)
```

이유:

- 각 모델은 동일 문제를 투표하는 구조가 아니다.
- 각 모델은 특정 생성 모델 계열의 흔적을 찾는 전문 탐지기이다.
- 특정 detector 하나만 높게 반응하는 것은 이상 현상이 아니라 정상적인 탐지 신호일 수 있다.

따라서 평균, 2등 점수, 모델 불일치도 기반 보정은 제거되었다.

## 9. 이미지 응답 구조

`/predict` 응답 예시:

```json
{
  "filename": "sample.png",
  "label": "Suspicious AI-like Image",
  "suspicious_score": 0.9491,
  "confidence": "ADAM 판단",
  "model_probs": {
    "sd": 0.123,
    "mj": 0.0441,
    "bg": 0.0,
    "sd3": 0.9491,
    "dalle3": 0.001,
    "univfd": 0.0641
  },
  "signals": {
    "model_fusion": 0.9491
  },
  "grad_cam": {
    "model": "sd3",
    "image_base64": "...",
    "note": "Highlighted areas contributed most to the selected AI-generator score."
  }
}
```

현재 `confidence`는 별도 통계적 신뢰도 계산값이 아니라, UI 표시용 고정 문구인 `ADAM 판단`이다.

## 10. Grad-CAM

Grad-CAM은 EfficientNet 계열 모델에 대해서만 생성한다. UnivFD는 CLIP + linear head 구조라 현재 Grad-CAM 대상으로 사용하지 않는다.

동작 방식:

1. 각 detector 점수 계산
2. Grad-CAM 생성 가능한 EfficientNet 모델만 후보로 필터링
3. 후보 중 가장 높은 점수를 낸 모델 선택
4. EfficientNet 마지막 feature block에 hook 등록
5. heatmap을 원본 이미지 위에 overlay
6. base64 PNG로 응답

## 11. 비디오 판별 구조

현재 공개 비디오 업로드 API인 `/predict-video`는 제거되어 있다.

비디오 판별 방식은 두 가지이다.

### 웹 프론트

1. 브라우저에서 비디오를 로드
2. 일정 간격으로 프레임 추출
3. 각 프레임을 이미지 판별 API로 전송
4. 프론트에서 프레임 점수를 평균내어 비디오 점수 표시

### 서버 내부/카카오

카카오 연동에서는 `service/predic_video.py`를 사용한다.

1. 비디오 파일 다운로드
2. 임시 파일 저장
3. `util/frame_extract.py`로 랜덤 프레임 추출
4. 각 프레임을 `predict_image(..., mode="video")`로 판별
5. 프레임 점수 평균을 비디오 점수로 사용

## 12. 텍스트 판별 아키텍처

텍스트 판별은 `AITextDetector`가 담당한다.

주요 구성:

| 구성 | 모델/기술 | 역할 |
|---|---|---|
| 문장/문서 분류 | `seongwoo02/ai_text_detector` 또는 fallback `xlm-roberta-base` | AI 작성 확률 산출 |
| 한국어 PPL | `skt/kogpt2-base-v2` | 한국어 문장 perplexity 보조 분석 |
| 영어 PPL | `gpt2` | 영어 문장 perplexity 보조 분석 |
| 문장 분리 | NLTK | 문장 단위 분석 |
| 언어 판별 | 정규식 기반 | 한국어/영어 PPL 모델 선택 |

텍스트 입력 제약:

- 최소 10자
- 최대 2000자

현재 문장 하이라이트는 전체 판정의 보조 정보이며, 짧은 문장 또는 전체 의심률이 낮은 경우에는 더 보수적으로 표시하는 방향으로 조정되어 있다.

## 13. 보정 데이터 저장

`/save-correction`은 사용자가 판정이 틀렸다고 판단한 이미지를 저장한다.

저장 위치:

```text
server/corrections/real/
server/corrections/fake/
server/corrections/logs.jsonl
```

저장 메타데이터:

- 파일 경로
- 사용자가 지정한 정답 라벨
- 기존 예측 라벨
- 기존 예측 점수
- Grad-CAM 선택 모델
- detector별 점수
  - `sd_prob`
  - `mj_prob`
  - `bg_prob`
  - `sd3_prob`
  - `dalle3_prob`
  - `univfd_prob`

## 14. 카카오 연동

`/kakao/detect`는 카카오 챗봇 요청을 처리한다.

처리 순서:

1. 요청 JSON에서 utterance와 action params 추출
2. 비디오 URL 우선 탐색
3. 이미지 URL 탐색
4. 텍스트 길이가 충분하면 텍스트 판별
5. 결과를 카카오 응답 포맷으로 반환

현재 카카오 응답 문자열 일부는 인코딩이 깨진 상태로 보이며, 별도 정리 대상이다.

## 15. 환경변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `PORT` | `8000` | FastAPI 서버 포트 |
| `HF_TOKEN` | 없음 | Hugging Face private model 접근 토큰 |
| `ADAM_UNIVFD_CHECKPOINT` | `server/model/univfd_linear.pth` | UnivFD linear head checkpoint 경로 |
| `ADAM_UNIVFD_CLIP_MODEL` | `openai/clip-vit-large-patch14` | UnivFD CLIP backbone |

예시:

```powershell
$env:PORT="8000"
$env:HF_TOKEN="hf_..."
python server\main.py
```

## 16. 제거된/비활성화된 요소

현재 서버 방향성과 맞지 않아 제거 또는 비활성화된 요소:

- 병합 이미지 모델
- `server/model/merged/`
- `server/tools/merge_image_models.py`
- `ADAM_IMAGE_MODEL_MODE`
- `/predict-video`
- SDXL detector
- 모델 불일치도 지표
- `sdxl_spike`

## 17. 실행 확인

서버 실행:

```powershell
python server\main.py
```

상태 확인:

```powershell
curl http://localhost:8000/
```

이미지 판별:

```powershell
curl -X POST http://localhost:8000/predict `
  -F "file=@sample.png"
```

텍스트 판별:

```powershell
curl -X POST http://localhost:8000/detect `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"분석할 텍스트를 여기에 입력합니다.\"}"
```

## 18. 운영상 주의사항

- 서버 시작 시 이미지 ensemble 모델을 모두 로드하므로 초기 로딩 시간이 있다.
- UnivFD는 첫 실행 시 Hugging Face CLIP 모델 캐시 다운로드가 발생할 수 있다.
- CPU 환경에서도 동작하지만, 모델 수가 많아 이미지 판별 응답 시간이 길어질 수 있다.
- `server/corrections/`는 사용자 보정 데이터가 쌓이는 위치이므로 배포 이미지에는 포함하지 않는 것이 좋다.
- `server/.env`에는 Hugging Face 토큰이 들어갈 수 있으므로 외부 공개 저장소에 노출되면 안 된다.
