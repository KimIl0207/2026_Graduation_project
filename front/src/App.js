import { useState } from 'react';
import './App.css';

const BASE_URL = "http://localhost:8000";

async function fetchPrediction(file) {
  const imageData = new FormData();
  imageData.append('file', file);

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

  const handleUpload = async () => {
    const file = document.getElementById('fileInput').files[0];
    if (!file) return;

    setSelectedFile(file);
    setImageUrl(URL.createObjectURL(file));
    setSaveMessage("");

    const data = await fetchPrediction(file);
    setResult(data);
  };

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