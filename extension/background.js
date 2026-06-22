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

  if (request.action === "CANCEL_ANALYSIS") {
    if (activeControllers[tabId]) {
      activeControllers[tabId].abort();
      delete activeControllers[tabId];
      console.log(`[탭 ${tabId}] 사용자에 의해 분석이 강제 취소되었습니다.`);
    }
    return true;
  }

  if (request.action === "CAPTURE_VISIBLE") {
    chrome.tabs.captureVisibleTab(null, { format: "png" }, (dataUrl) => {
      sendResponse(chrome.runtime.lastError ? { error: chrome.runtime.lastError.message } : { dataUrl: dataUrl });
    });
    return true;
  }

  if (request.action === "ANALYZE_TEXT_API") {
    if (activeControllers[tabId]) activeControllers[tabId].abort();
    const controller = new AbortController();
    activeControllers[tabId] = controller;

    handleTextAnalysis(request.text, controller.signal)
      .then(data => { delete activeControllers[tabId]; sendResponse({ success: true, data: data }); })
      .catch(error => { delete activeControllers[tabId]; sendResponse({ success: false, error: error.message }); });
    return true;
  }

  if (request.action === "ANALYZE_IMAGE_API") {
    if (activeControllers[tabId]) activeControllers[tabId].abort();
    const controller = new AbortController();
    activeControllers[tabId] = controller;

    handleSingleImageAnalysis(request.imgSrc, controller.signal)
      .then(data => { delete activeControllers[tabId]; sendResponse({ success: true, data: data }); })
      .catch(error => { delete activeControllers[tabId]; sendResponse({ success: false, error: error.message }); });
    return true;
  }

  // 🎥 [신규 비디오 전용 분기] 여러 장의 프레임 이미지 리스트를 서버로 대행 전송
  if (request.action === "ANALYZE_VIDEO_LIST_API") {
    if (activeControllers[tabId]) activeControllers[tabId].abort();
    const controller = new AbortController();
    activeControllers[tabId] = controller;

    handleVideoListAnalysis(request.imgSrcList, controller.signal)
      .then(data => { delete activeControllers[tabId]; sendResponse({ success: true, data: data }); })
      .catch(error => { delete activeControllers[tabId]; sendResponse({ success: false, error: error.message }); });
    return true;
  }
});

// 단일 이미지 분석 (/predict)
async function handleSingleImageAnalysis(imgSrc, signal) {
  const storageData = await chrome.storage.local.get(['serverUrl']);
  const serverUrl = storageData.serverUrl;
  if (!serverUrl) throw new Error("서버 주소가 설정되지 않았습니다.");

  let blob;
  if (imgSrc.startsWith('data:')) {
    const byteString = atob(imgSrc.split(',')[1]);
    const mimeString = imgSrc.split(',')[0].split(':')[1].split(';')[0];
    const ab = new ArrayBuffer(byteString.length);
    const ia = new Uint8Array(ab);
    for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
    blob = new Blob([ab], { type: mimeString });
  } else {
    const res = await fetch(imgSrc);
    blob = await res.blob();
  }

  const formData = new FormData();
  formData.append("file", blob, "image.jpg");

  const response = await fetch(`${serverUrl}/predict`, { method: "POST", headers: { "ngrok-skip-browser-warning": "true" }, body: formData, signal: signal });
  return await response.json();
}

// 🎥 [비디오 프레임 리스트 전송 함수] FastAPI의 /predict_images 규격 완벽 연동
async function handleVideoListAnalysis(imgSrcList, signal) {
  const storageData = await chrome.storage.local.get(['serverUrl']);
  const serverUrl = storageData.serverUrl;
  if (!serverUrl) throw new Error("서버 주소가 설정되지 않았습니다.");

  const formData = new FormData();

  // 리스트 내의 모든 Base64 데이터를 순회하며 Blob 변환 후 하나의 'files' 키에 다중 추가(List화)
  for (let i = 0; i < imgSrcList.length; i++) {
    const imgSrc = imgSrcList[i];
    const byteString = atob(imgSrc.split(',')[1]);
    const mimeString = imgSrc.split(',')[0].split(':')[1].split(';')[0];
    const ab = new ArrayBuffer(byteString.length);
    const ia = new Uint8Array(ab);
    for (let j = 0; j < byteString.length; j++) ia[j] = byteString.charCodeAt(j);
    const blob = new Blob([ab], { type: mimeString });

    // 💡 FastAPI Body_predict_frame_images_predict_images_post 스펙에 맞춰 필드명을 반드시 'files'로 매핑
    formData.append("files", blob, `frame_${i}.jpg`);
  }

  const response = await fetch(`${serverUrl}/predict_images`, {
    method: "POST",
    headers: { "ngrok-skip-browser-warning": "true" },
    body: formData,
    signal: signal
  });

  if (!response.ok) throw new Error(`HTTP 에러 발생! 상태코드: ${response.status}`);
  return await response.json();
}

// 텍스트 분석 (/detect)
async function handleTextAnalysis(text, signal) {
  const storageData = await chrome.storage.local.get(['serverUrl']);
  const serverUrl = storageData.serverUrl;
  if (!serverUrl) throw new Error("서버 주소가 설정되지 않았습니다.");

  const response = await fetch(`${serverUrl}/detect`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true" },
    body: JSON.stringify({ text: text }),
    signal: signal
  });
  return await response.json();
}