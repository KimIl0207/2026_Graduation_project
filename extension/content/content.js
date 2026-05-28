// content/content.js
// ==========================================
// [메인 라우터] 백그라운드 신호를 각 파일로 분배
// ==========================================
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Shadow DOMRoot 확보 (common.js 함수)
  const root = getShadowRoot();

  if (msg.action === "ENABLE_SELECTION") {
    // 기존에 남아있을지 모르는 선택 박스 제거
    const existingBox = root.querySelector(".deepfake-selection-box");
    if (existingBox) existingBox.remove();

    document.body.style.cursor = "crosshair";
    // image.js의 startSelection 함수 호출
    document.addEventListener("mousedown", startSelection, { once: true });
  }
  else if (msg.action === "ENABLE_ELEMENT_PICKER") {
    // video.js의 startElementPicker 함수 호출
    if (typeof startElementPicker === "function") {
      startElementPicker();
    }
  }
  else if (msg.action === "ANALYZE_TEXT") {
    // text.js의 showTextResultModal 함수 호출
    if (typeof showTextResultModal === "function") {
      showTextResultModal(msg.text);
    }
  }
  else if (msg.action === "ANALYZE_DIRECT_IMAGE") {
    // image.js의 showImageResultModal 함수 호출
    if (typeof showImageResultModal === "function") {
      showImageResultModal(msg.imgSrc);
    }
  }

  // 비동기 응답 처리를 위해 true 반환 (필요 시)
  return true;
});