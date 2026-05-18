// 현재 탭별로 실행 중인 분석 요청을 추적하기 위한 저장소
const activeControllers = {};

// 1. 우클릭 메뉴 생성
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "analyze-text", title: "이 텍스트 AI 판별하기", contexts: ["selection"] }, () => chrome.runtime.lastError);
    chrome.contextMenus.create({ id: "analyze-image", title: "이 이미지 AI 판별하기", contexts: ["image"] }, () => chrome.runtime.lastError);
  });
});

// 2. 우클릭 메뉴 클릭 시 동작
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab || !tab.id) return;
  if (info.menuItemId === "analyze-text") {
    chrome.tabs.sendMessage(tab.id, { action: "ANALYZE_TEXT", text: info.selectionText }).catch(err => console.error(err));
  } else if (info.menuItemId === "analyze-image") {
    chrome.tabs.sendMessage(tab.id, { action: "ANALYZE_DIRECT_IMAGE", imgSrc: info.srcUrl }).catch(err => console.error(err));
  }
});

// 3. 메시지 리스너 (캡처 및 API 통신 대행)
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const tabId = sender.tab ? sender.tab.id : 'unknown';

  // [복구됨] 분석 강제 취소 요청이 들어왔을 때
  if (request.action === "CANCEL_ANALYSIS") {
    if (activeControllers[tabId]) {
      activeControllers[tabId].abort(); // 진행 중인 fetch 통신 즉시 중단!
      delete activeControllers[tabId];
      console.log(`[탭 ${tabId}] 사용자에 의해 분석이 강제 취소되었습니다.`);
    }
    return true;
  }

  // 화면 캡처 로직
  if (request.action === "CAPTURE_VISIBLE") {
    chrome.tabs.captureVisibleTab(null, { format: "png" }, (dataUrl) => {
      sendResponse(chrome.runtime.lastError ? { error: chrome.runtime.lastError.message } : { dataUrl: dataUrl });
    });
    return true;
  }

  // 텍스트 분석 요청 처리
  if (request.action === "ANALYZE_TEXT_API") {
    if (activeControllers[tabId]) activeControllers[tabId].abort();

    const controller = new AbortController();
    activeControllers[tabId] = controller;

    handleTextAnalysis(request.text, controller.signal)
      .then(data => {
        delete activeControllers[tabId];
        sendResponse({ success: true, data: data });
      })
      .catch(error => {
        delete activeControllers[tabId];
        if (error.name === 'AbortError') {
          sendResponse({ success: false, error: "사용자 취소됨", isAborted: true });
        } else {
          sendResponse({ success: false, error: error.message });
        }
      });
    return true;
  }

  // 이미지 또는 비디오 분석 요청 처리
  if (request.action === "ANALYZE_IMAGE_API" || request.action === "ANALYZE_VIDEO_API") {
    if (activeControllers[tabId]) activeControllers[tabId].abort();

    const controller = new AbortController();
    activeControllers[tabId] = controller;

    const analysisPromise = request.action === "ANALYZE_IMAGE_API"
      ? handleImageAnalysis(request.imgSrc, controller.signal)
      : handleVideoAnalysis(request.videoDataUrl, controller.signal);

    analysisPromise
      .then(data => {
        delete activeControllers[tabId];
        sendResponse({ success: true, data: data });
      })
      .catch(error => {
        delete activeControllers[tabId];
        if (error.name === 'AbortError') {
          sendResponse({ success: false, error: "사용자 취소됨", isAborted: true });
        } else {
          sendResponse({ success: false, error: error.message });
        }
      });
    return true;
  }
});

// ** 연결 완료 ** 실제 백엔드 통신 함수 (이미지용 - 드래그/우클릭 완벽 대응 버전) 
async function handleImageAnalysis(imgSrc, signal) {
  const storageData = await chrome.storage.local.get(['serverUrl']);
  const serverUrl = storageData.serverUrl;
  if (!serverUrl) throw new Error("서버 주소가 설정되지 않았습니다. 옵션에서 주소를 입력해주세요.");

  let blob;
  if (imgSrc.startsWith('data:')) {
    const byteString = atob(imgSrc.split(',')[1]);
    const mimeString = imgSrc.split(',')[0].split(':')[1].split(';')[0];
    const ab = new ArrayBuffer(byteString.length);
    const ia = new Uint8Array(ab);
    for (let i = 0; i < byteString.length; i++) {
      ia[i] = byteString.charCodeAt(i);
    }
    blob = new Blob([ab], { type: mimeString });
  } else {
    const res = await fetch(imgSrc);
    blob = await res.blob();
  }

  const formData = new FormData();
  formData.append("file", blob, "captured_image.jpg");

  const response = await fetch(`${serverUrl}/predict`, {
    method: "POST",
    headers: { "ngrok-skip-browser-warning": "true" },
    body: formData,
    signal: signal
  });

  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
}


// ** 수정됨 ** 실제 백엔드 API 서버와 통신하는 함수 (텍스트용)
async function handleTextAnalysis(text, signal) {
  const storageData = await chrome.storage.local.get(['serverUrl']);
  const serverUrl = storageData.serverUrl;
  if (!serverUrl) throw new Error("서버 주소가 설정되지 않았습니다. 옵션에서 주소를 입력해주세요.");

  // 백엔드 주소에 맞춰 /detect 로 변경
  const response = await fetch(`${serverUrl}/detect`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "ngrok-skip-browser-warning": "true"
    },
    body: JSON.stringify({ text: text }),
    signal: signal
  });

  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
}

// ** 수정됨 ** 실제 백엔드 API 서버와 통신하는 함수 (비디오용)
async function handleVideoAnalysis(videoDataUrl, signal) {
  const storageData = await chrome.storage.local.get(['serverUrl']);
  const serverUrl = storageData.serverUrl;
  if (!serverUrl) throw new Error("서버 주소가 설정되지 않았습니다. 옵션에서 주소를 입력해주세요.");

  const byteString = atob(videoDataUrl.split(',')[1]);
  const mimeString = videoDataUrl.split(',')[0].split(':')[1].split(';')[0];
  const ab = new ArrayBuffer(byteString.length);
  const ia = new Uint8Array(ab);
  for (let i = 0; i < byteString.length; i++) {
    ia[i] = byteString.charCodeAt(i);
  }
  const blob = new Blob([ab], { type: mimeString });

  const formData = new FormData();
  formData.append("file", blob, "captured_video.webm");

  // 백엔드 주소에 맞춰 /predict-video 로 변경
  const response = await fetch(`${serverUrl}/predict-video`, {
    method: "POST",
    headers: { "ngrok-skip-browser-warning": "true" },
    body: formData,
    signal: signal
  });

  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
}

// 5. ** 연결 준비중 ** 실제 백엔드 API 서버와 통신하는 함수 (비디오용)
async function handleVideoAnalysis(videoDataUrl, signal) {
  const storageData = await chrome.storage.local.get(['serverUrl']);
  const serverUrl = storageData.serverUrl;
  if (!serverUrl) throw new Error("서버 주소가 설정되지 않았습니다. 옵션에서 주소를 입력해주세요.");

  // [수정됨] 거대한 Base64 비디오 데이터를 안전하게 파일(Blob) 형태로 강제 변환
  const byteString = atob(videoDataUrl.split(',')[1]);
  const mimeString = videoDataUrl.split(',')[0].split(':')[1].split(';')[0];
  const ab = new ArrayBuffer(byteString.length);
  const ia = new Uint8Array(ab);
  for (let i = 0; i < byteString.length; i++) {
    ia[i] = byteString.charCodeAt(i);
  }
  const blob = new Blob([ab], { type: mimeString });

  const formData = new FormData();
  formData.append("file", blob, "captured_video.webm");

  const response = await fetch(`${serverUrl}/predict_video`, {
    method: "POST",
    headers: { "ngrok-skip-browser-warning": "true" },
    body: formData,
    signal: signal
  });

  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
}