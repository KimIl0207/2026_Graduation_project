# 🧠 AI Image Detector

AI가 생성한 이미지와 실제 이미지를 구분하는 딥러닝 기반 분류 시스템입니다.
EfficientNet 모델을 활용하여 높은 정확도로 **AI vs Real 이미지 판별**을 수행합니다.

---

## 🚀 Features

* 🔍 이미지 업로드 후 AI 여부 실시간 판별
* 🧠 EfficientNet 기반 이미지 분류 모델
* 📊 확률 기반 결과 제공 (confidence score)

---

## ⚙️ Tech Stack

* 🐍 Python / PyTorch
* ⚡ FastAPI
* ⚛️ React (create-react-app)
* 🧠 EfficientNet (Image Classification)

---

## 📦 Installation

### Backend

```bash
pip install fastapi uvicorn torch torchvision pillow
```

```bash
uvicorn test:app --reload
```

---

### Frontend

```bash
npm install
npm start
```

---

## 📸 Usage

1. 이미지를 업로드합니다.
2. AI 여부 및 확률이 표시됩니다.
3. 결과가 틀렸다면:

   * "실제 사진" 또는 "AI 이미지" 버튼 클릭
   * 자동으로 데이터셋에 저장됩니다.

---

## 🔁 Training Pipeline

```text
1. 데이터 수집 (real / fake)
2. EfficientNet 학습
3. 모델 배포
4. 사용자 피드백 수집 (corrections)
5. 데이터셋 확장
6. 재학습
```

---

## 📊 Dataset

* Real Images:

  * COCO Dataset
  * 실제 촬영 이미지
* Fake Images:

  * DiffusionDB (부분 샘플)

---

## 🧪 Model

* Architecture: EfficientNet-B0
* Input Size: 224x224
* Loss: BCEWithLogitsLoss
* Output:

  * 0 → Real Image
  * 1 → AI Generated

---

## 📈 Future Improvements

* 🔍 더 다양한 생성 모델 대응 (Midjourney, DALL·E 등)
* 📊 Grad-CAM 시각화 추가
* ⚡ 모델 경량화 (모바일, 크롬 확장프로그램, 응용프로그램 지원)
* 🌐 배포 (AWS / Docker)

---

## 🧑‍💻 Author

* AI / Software Engineering Project

---

## ⭐️ License

MIT License
