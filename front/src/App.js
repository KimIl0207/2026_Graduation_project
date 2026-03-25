import { useState } from 'react';
import './App.css';

const BASE_URL = "https://two026-graduation-project.onrender.com:8000";
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const MAX_RESOLUTION = 4096; // 4096x4096 pixels

// 파일 업로드 및 예측 결과 가져오기
async function fetchPrediction(file) {
  const imageData = new FormData();
  imageData.append('file', file);

  if (file.size > MAX_FILE_SIZE || file.width > MAX_RESOLUTION || file.height > MAX_RESOLUTION) {
    return { error: "File size exceeds 10MB or resolution exceeds 4096x4096 pixels." };
  }

  try {
    const response = await fetch(`${BASE_URL}/predict`, {
      method: 'POST',
      body: imageData,
    });

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error uploading file:', error);
    return null;
  }
}

// 정답 폴더에 저장
async function saveCorrection(file, correctLabel) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('correct_label', correctLabel);

  try {
    const response = await fetch(`${BASE_URL}/save-correction`, {
      method: 'POST',
      body: formData,
    });

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error saving correction:', error);
    return null;
  }
}

function App() {
  const [result, setResult] = useState(null);
  const [imageUrl, setImageUrl] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [saveMessage, setSaveMessage] = useState("");

  // 파일 업로드 및 예측 결과 가져오기
  const handleUpload = async () => {
    const file = document.getElementById('fileInput').files[0];
    if (!file) return;

    setSelectedFile(file);
    setImageUrl(URL.createObjectURL(file));
    setSaveMessage("");

    const data = await fetchPrediction(file);
    setResult(data);
  };

  // 정답 폴더에 저장
  const handleSaveCorrection = async (label) => {
    if (!selectedFile) return;

    const data = await saveCorrection(selectedFile, label);

    if (data?.success) {
      setSaveMessage(`${label} 폴더에 저장 완료`);
    } else {
      setSaveMessage("저장 실패");
    }
  };

  return (
    <div className="App">
      <input type="file" id="fileInput" accept="image/*" />
      <button onClick={handleUpload}>upload</button>
      <p></p>

      {imageUrl && <img src={imageUrl} alt="Uploaded" width="200" />}

      {result && (
        <div>
          <p>Label: {result.label}</p>
          <p>Probability: {result.probability}</p>
          <p>{result.error && `Error: ${result.error}`}</p>

          <hr />

          <p>예측이 틀렸다면 정답 폴더에 저장:</p>
          <button onClick={() => handleSaveCorrection("real")}>
            실제 사진으로 저장
          </button>
          <button onClick={() => handleSaveCorrection("fake")} style={{ marginLeft: "10px" }}>
            AI 이미지로 저장
          </button>

          {saveMessage && <p>{saveMessage}</p>}
        </div>
      )}
    </div>
  );
}

export default App;