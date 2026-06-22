// 환경 설정 및 상수 (Config & Constants)

const CONFIG = {
  CAPTURE_DELAY_MS: 50,          // 캡처 전 격자선 숨김 딜레이 (ms)
  VIDEO_RECORD_SECONDS: 5,       // 비디오 녹화 시간 (초)
  VIDEO_TIMEOUT_MS: 5000,        // 비디오 녹화 강제 종료 시간 (ms)
  TOAST_DURATION_MS: 3000        // 토스트 알림창 기본 표시 시간 (ms)
};

let isSelecting = false;
let startX, startY, selectionBox;

// [0] Shadow DOM 초기화 및 가져오기 (핵심 리팩토링)
let extensionShadowRoot = null;
function getShadowRoot() {
  if (!extensionShadowRoot) {
    const host = document.createElement("div");
    host.id = "deepfake-extension-host";
    host.style.position = "fixed";
    host.style.top = "0";
    host.style.left = "0";
    host.style.width = "100%";
    host.style.height = "100%";
    host.style.pointerEvents = "none";
    host.style.zIndex = "2147483647";
    document.body.appendChild(host);

    extensionShadowRoot = host.attachShadow({ mode: "open" });

    const styleLink = document.createElement("link");
    styleLink.rel = "stylesheet";
    styleLink.href = chrome.runtime.getURL("style.css");
    extensionShadowRoot.appendChild(styleLink);
  }
  return extensionShadowRoot;
}

// [1] 배경에서 보내는 신호 받기
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === "ENABLE_SELECTION") {
    const root = getShadowRoot();
    const existingBox = root.querySelector(".deepfake-selection-box");
    if (existingBox) existingBox.remove();
    document.body.style.cursor = "crosshair";
    document.addEventListener("mousedown", startSelection, { once: true });
  }
  else if (msg.action === "ENABLE_ELEMENT_PICKER") {
    startElementPicker();
  }
  else if (msg.action === "ANALYZE_TEXT") {
    showTextResultModal(msg.text);
  }
  else if (msg.action === "ANALYZE_DIRECT_IMAGE") {
    showImageResultModal(msg.imgSrc);
  }
});

// [2] 드래그 캡처 관련 로직
function startSelection(e) {
  isSelecting = true;
  startX = e.clientX;
  startY = e.clientY;

  document.body.style.userSelect = "none";
  document.body.style.webkitUserSelect = "none";

  selectionBox = document.createElement("div");
  selectionBox.className = "deepfake-selection-box";
  getShadowRoot().appendChild(selectionBox);

  document.addEventListener("mousemove", resizeSelection);
  document.addEventListener("mouseup", finishSelection, { once: true });
}

function resizeSelection(e) {
  if (!isSelecting) return;
  const curX = e.clientX;
  const curY = e.clientY;
  selectionBox.style.left = Math.min(startX, curX) + "px";
  selectionBox.style.top = Math.min(startY, curY) + "px";
  selectionBox.style.width = Math.abs(startX - curX) + "px";
  selectionBox.style.height = Math.abs(startY - curY) + "px";
}

// [수정됨] 드래그가 끝났을 때 캡처하는 함수 (격자선 찍힘 방지 적용)
function finishSelection(e) {
  isSelecting = false;
  document.body.style.cursor = "default";
  document.body.style.userSelect = "";
  document.body.style.webkitUserSelect = "";
  document.removeEventListener("mousemove", resizeSelection);

  const rect = selectionBox.getBoundingClientRect();

  // 1. 화면에서 박스를 즉시 투명하게 숨깁니다 (remove 하기 전에 먼저 안 보이게 처리)
  selectionBox.style.display = "none";

  if (rect.width < 5 || rect.height < 5) {
    selectionBox.remove();
    return;
  }

  // 2. 브라우저가 격자선을 화면에서 완전히 지울 수 있도록 0.05초(50ms) 아주 잠깐 기다려줍니다.
  setTimeout(() => {
    chrome.runtime.sendMessage({ action: "CAPTURE_VISIBLE" }, (response) => {
      // 3. 캡처가 끝나면 박스 찌꺼기를 완전히 삭제합니다.
      selectionBox.remove();

      if (chrome.runtime.lastError || (response && response.error)) return;
      if (response && response.dataUrl) {
        cropAndAnalyze(response.dataUrl, rect);
      }
    });
  }, CONFIG.CAPTURE_DELAY_MS);
}

function cropAndAnalyze(dataUrl, rect) {
  const canvas = document.createElement("canvas");
  const img = new Image();
  img.onload = () => {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;

    const ctx = canvas.getContext("2d");
    ctx.drawImage(
      img,
      rect.left * dpr, rect.top * dpr,
      rect.width * dpr, rect.height * dpr,
      0, 0,
      rect.width * dpr, rect.height * dpr
    );

    const croppedImg = canvas.toDataURL("image/jpeg", 1.0);
    showImageResultModal(croppedImg);
  };
  img.src = dataUrl;
}

// [3] 공통 이미지 결과 모달 UI (애플 스타일 & 다시 시도 기능 완벽 적용)
function showImageResultModal(imgSrc) {
  const root = getShadowRoot();
  const oldModal = root.querySelector("#deepfake-result-modal");
  if (oldModal) oldModal.remove();

  const modal = document.createElement("div");
  modal.id = "deepfake-result-modal";
  modal.style.pointerEvents = "auto";

  // 텍스트, 비디오와 완전히 동일한 HTML 구조 및 CSS 클래스 적용
  modal.innerHTML = `
    <div class="modal-header">AI 이미지 분석 결과</div>
    
    <img src="${imgSrc}" class="modal-media">
    
    <div id="img-analysis-status" class="modal-status-text">서버 전송 및 분석 중...</div>
    
    <div class="progress-bar"><div class="progress-fill" id="img-fill" style="width: 40%;"></div></div>
    
    <div id="img-error-container" style="display: none; width: 100%;">
      <p id="img-error-msg" class="error-msg">연결 실패</p>
      <div class="btn-group">
        <button id="img-retry-btn" class="modal-btn retry-btn">다시 시도</button>
      </div>
    </div>
    
    <div class="btn-group" style="margin-top: 12px;">
      <button class="modal-btn close-btn">닫기</button>
    </div>
  `;
  root.appendChild(modal);

  // 닫기 버튼 클릭 시 통신 취소
  modal.querySelector(".close-btn").onclick = () => {
    chrome.runtime.sendMessage({ action: "CANCEL_ANALYSIS" });
    modal.remove();
  };

  // 텍스트/비디오와 동일하게 '요청 로직'을 묶어서 재사용 가능하게 만듦
  const sendImageAnalysis = () => {
    // UI 초기화 (에러 메시지 숨기고 파란색 게이지바로 복구)
    root.querySelector("#img-analysis-status").innerText = "서버 전송 및 분석 중...";
    root.querySelector("#img-fill").style.width = "40%";
    root.querySelector("#img-fill").style.backgroundColor = "#007aff";
    root.querySelector("#img-error-container").style.display = "none";

    chrome.runtime.sendMessage({ action: "ANALYZE_IMAGE_API", imgSrc: imgSrc }, (response) => {
      updateImageResultUI(response);
    });
  };

  // 다시 시도 버튼에 요청 함수 연결
  modal.querySelector("#img-retry-btn").onclick = sendImageAnalysis;

  // 최초 창이 뜰 때 바로 1회 실행
  sendImageAnalysis();
}

// [3-1] 이미지 분석 결과를 UI에 업데이트하는 함수
function updateImageResultUI(response) {
  const root = getShadowRoot();
  const statusTxt = root.querySelector("#img-analysis-status");
  const progressFill = root.querySelector("#img-fill");
  const errorContainer = root.querySelector("#img-error-container");

  if (chrome.runtime.lastError || !response || (!response.success && response.error)) {
    statusTxt.innerText = "분석 실패 (통신 에러)";
    progressFill.style.backgroundColor = "#ff3b30";
    root.querySelector("#img-error-msg").innerText = response && response.error ? response.error : "서버 응답 없음";
    errorContainer.style.display = "block";
    return;
  }

  // 정상 응답 처리 로직
  const data = response.data || response;
  const prob = data.predicted_probability !== undefined ? (data.predicted_probability * 100).toFixed(2) : 0;
  const isReal = data.predicted_label === "Real Image" || data.predicted_label === "Real";
  const labelText = isReal ? "진짜(원본)" : "딥페이크 의심";
  const labelColor = isReal ? "#34c759" : "#ff3b30";

  statusTxt.innerHTML = `<strong>결과: <span style="color:${labelColor};">${labelText}</span></strong> <br><span style="font-size: 12px; color:#86868b;">(딥페이크 확률: ${prob}%)</span>`;
  progressFill.style.width = `${prob}%`;
  progressFill.style.backgroundColor = labelColor;
}

// [4] 텍스트 결과 모달 UI (다시 시도 기능 추가)
function showTextResultModal(text) {
  const root = getShadowRoot();
  const oldModal = root.querySelector("#deepfake-result-modal");
  if (oldModal) oldModal.remove();

  const modal = document.createElement("div");
  modal.id = "deepfake-result-modal";
  modal.style.pointerEvents = "auto";

  const displayText = text.length > 100 ? text.substring(0, 100) + "..." : text;

  modal.innerHTML = `
    <div class="modal-header">AI 텍스트 분석 결과</div>
    <div style="width: 100%; background: rgba(0, 0, 0, 0.04); padding: 16px; border-radius: 12px; margin-bottom: 20px; font-size: 14px; line-height: 1.5; color: #424245; word-break: break-all; box-sizing: border-box;">
      "${displayText}"
    </div>
    <div id="text-analysis-status" class="modal-status-text">서버 전송 및 분석 중...</div>
    <div class="progress-bar"><div class="progress-fill" id="text-fill" style="width: 40%;"></div></div>
    
    <div id="text-error-container" style="display: none; width: 100%;">
      <p id="text-error-msg" class="error-msg">연결 실패</p>
      <div class="btn-group">
        <button id="text-retry-btn" class="modal-btn retry-btn">다시 시도</button>
      </div>
    </div>
    
    <div class="btn-group" style="margin-top: 12px;">
      <button class="modal-btn close-btn">닫기</button>
    </div>
  `;
  root.appendChild(modal);

  // 닫기 버튼 클릭 시 취소
  modal.querySelector(".close-btn").onclick = () => {
    chrome.runtime.sendMessage({ action: "CANCEL_ANALYSIS" });
    modal.remove();
  };

  // 재사용을 위해 분석 요청 로직을 함수로 묶음
  const sendTextAnalysis = () => {
    // UI 초기화 (에러 감추고 파란색 게이지바로 복구)
    root.querySelector("#text-analysis-status").innerText = "서버 전송 및 분석 중...";
    root.querySelector("#text-fill").style.width = "40%";
    root.querySelector("#text-fill").style.backgroundColor = "#007aff";
    root.querySelector("#text-error-container").style.display = "none";

    chrome.runtime.sendMessage({ action: "ANALYZE_TEXT_API", text: text }, (response) => {
      updateTextResultUI(response);
    });
  };

  // 다시 시도 버튼에 요청 함수 연결
  modal.querySelector("#text-retry-btn").onclick = sendTextAnalysis;

  // 최초 창이 뜰 때 바로 1회 실행
  sendTextAnalysis();
}

// 텍스트 UI 업데이트 함수 (에러 처리 구문 추가)
function updateTextResultUI(response) {
  const root = getShadowRoot();
  const statusTxt = root.querySelector("#text-analysis-status");
  const progressFill = root.querySelector("#text-fill");
  const errorContainer = root.querySelector("#text-error-container");

  if (chrome.runtime.lastError || !response || (!response.success && response.error)) {
    statusTxt.innerText = "분석 실패 (통신 에러)";
    progressFill.style.backgroundColor = "#ff3b30";
    root.querySelector("#text-error-msg").innerText = response && response.error ? response.error : "서버 응답 없음";
    errorContainer.style.display = "block";
    return;
  }

  const data = response.data || response;
  const prob = data.final_ai_prob !== undefined ? data.final_ai_prob.toFixed(2) : 0;
  const isAI = data.decision === "AI";
  const labelText = isAI ? "AI 작성 의심" : "사람이 작성함";
  const labelColor = isAI ? "#ff3b30" : "#34c759";

  statusTxt.innerHTML = `<strong>결과: <span style="color:${labelColor};">${labelText}</span></strong> <br><span style="font-size: 12px; color:#86868b;">(AI 확률: ${prob}%)</span>`;
  progressFill.style.width = `${prob}%`;
  progressFill.style.backgroundColor = labelColor;
}

// [5] 신규 기능: 토스트 알림 메시지 (alert 대체용)
function showToastMessage(message, duration = CONFIG.TOAST_DURATION_MS) {
  const root = getShadowRoot();

  const toast = document.createElement("div");
  toast.style.position = "fixed";
  toast.style.bottom = "30px";
  toast.style.left = "50%";
  toast.style.transform = "translateX(-50%)";
  toast.style.backgroundColor = "rgba(0, 0, 0, 0.8)";
  toast.style.color = "white";
  toast.style.padding = "12px 24px";
  toast.style.borderRadius = "30px";
  toast.style.fontSize = "14px";
  toast.style.zIndex = "2147483647";
  toast.style.boxShadow = "0 4px 12px rgba(0,0,0,0.15)";
  toast.style.transition = "opacity 0.3s ease-in-out";
  toast.style.pointerEvents = "none";
  toast.innerText = message;

  root.appendChild(toast);

  // 지정된 시간 후 서서히 사라짐
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// [6] HTML 요소 인식 모드 (비디오 영역 직접 캡처용)
let isElementPicking = false;
let hoverBox = null;

function startElementPicker() {
  isElementPicking = true;
  const root = getShadowRoot();

  hoverBox = document.createElement("div");
  hoverBox.style.position = "fixed";
  hoverBox.style.border = "3px solid #ff4d4d";
  hoverBox.style.backgroundColor = "rgba(255, 77, 77, 0.2)";
  hoverBox.style.zIndex = "2147483646";
  hoverBox.style.pointerEvents = "none";
  hoverBox.style.transition = "all 0.1s ease-out";

  root.appendChild(hoverBox);

  document.addEventListener("mousemove", handleMouseMove);
  document.addEventListener("click", handleElementClick, { capture: true, once: true });
  document.body.style.cursor = "crosshair";
}

function handleMouseMove(e) {
  if (!isElementPicking) return;
  const target = e.target;
  if (target === document.body || target === document.documentElement) return;

  const rect = target.getBoundingClientRect();
  hoverBox.style.top = rect.top + "px";
  hoverBox.style.left = rect.left + "px";
  hoverBox.style.width = rect.width + "px";
  hoverBox.style.height = rect.height + "px";
}

function handleElementClick(e) {
  if (!isElementPicking) return;
  e.preventDefault();
  e.stopPropagation();

  isElementPicking = false;
  document.removeEventListener("mousemove", handleMouseMove);
  document.body.style.cursor = "default";

  const target = e.target;
  hoverBox.remove();

  // alert 대신 showToastMessage 적용
  if (target.tagName.toLowerCase() !== 'video') {
    showToastMessage("⚠️ 동영상(video) 태그가 아닙니다! 재생 중인 영상 위를 클릭해주세요.", 3000);
    return;
  }

  startDirectVideoRecording(target);
}

// [7] 화면 공유 팝업 없이 비디오 태그에서 직접 5초 녹화 + 실시간 타이머 및 취소 기능
async function startDirectVideoRecording(videoElement) {
  try {
    const stream = videoElement.captureStream ? videoElement.captureStream() : videoElement.mozCaptureStream();

    if (!stream) {
      throw new Error("스트림을 추출할 수 없습니다.");
    }

    const recorder = new MediaRecorder(stream, { mimeType: "video/webm" });
    const chunks = [];

    // [핵심] 취소 버튼을 눌렀는지 확인하는 스위치
    let isCanceled = false;

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };

    recorder.onstop = () => {
      // 만약 사용자가 취소를 눌렀다면, 서버로 안 보내고 여기서 함수 종료!
      if (isCanceled) return;

      const videoBlob = new Blob(chunks, { type: "video/webm" });
      const videoUrl = URL.createObjectURL(videoBlob);

      showVideoResultModal(videoUrl, videoBlob);

      const reader = new FileReader();
      reader.readAsDataURL(videoBlob);
      reader.onloadend = () => {
        const base64data = reader.result;
        chrome.runtime.sendMessage({ action: "ANALYZE_VIDEO_API", videoDataUrl: base64data }, (response) => {
          updateVideoResultUI(response);
        });
      };
    };

    // --- 녹화 중 상태바 UI (타이머 + 취소버튼) 생성 ---
    const root = getShadowRoot();
    const recordingUI = document.createElement("div");
    recordingUI.style.position = "fixed";
    recordingUI.style.bottom = "30px";
    recordingUI.style.left = "50%";
    recordingUI.style.transform = "translateX(-50%)";
    recordingUI.style.backgroundColor = "rgba(0, 0, 0, 0.85)";
    recordingUI.style.color = "white";
    recordingUI.style.padding = "12px 24px";
    recordingUI.style.borderRadius = "30px";
    recordingUI.style.fontSize = "15px";
    recordingUI.style.zIndex = "2147483647";
    recordingUI.style.boxShadow = "0 4px 12px rgba(0,0,0,0.2)";
    recordingUI.style.display = "flex";
    recordingUI.style.alignItems = "center";
    recordingUI.style.gap = "15px";
    recordingUI.style.pointerEvents = "auto"; // 클릭 가능하게 설정!

    const timerText = document.createElement("span");
    let timeLeft = CONFIG.VIDEO_RECORD_SECONDS;
    timerText.innerHTML = `🔴 녹화 중... <strong>${timeLeft}초</strong> 남음`;

    const cancelBtn = document.createElement("button");
    cancelBtn.innerText = "취소";
    cancelBtn.style.backgroundColor = "#ff4d4d";
    cancelBtn.style.color = "white";
    cancelBtn.style.border = "none";
    cancelBtn.style.padding = "6px 14px";
    cancelBtn.style.borderRadius = "15px";
    cancelBtn.style.cursor = "pointer";
    cancelBtn.style.fontWeight = "bold";

    recordingUI.appendChild(timerText);
    recordingUI.appendChild(cancelBtn);
    root.appendChild(recordingUI);

    // --- 타이머 및 녹화 로직 시작 ---
    recorder.start();

    const timerInterval = setInterval(() => {
      timeLeft--;
      if (timeLeft >= 0) {
        timerText.innerHTML = `녹화 중... <strong>${timeLeft}초</strong> 남음`;
      }
    }, 1000);

    // 강제 종료 시간을 5000ms(5초).
    const stopTimeout = setTimeout(() => {
      clearInterval(timerInterval);
      recordingUI.remove();
      if (recorder.state === "recording") recorder.stop();
    }, CONFIG.VIDEO_TIMEOUT_MS);

    // 취소 버튼 클릭 이벤트
    cancelBtn.onclick = () => {
      isCanceled = true; // 취소 플래그 켜기
      clearInterval(timerInterval);
      clearTimeout(stopTimeout);
      recordingUI.remove();
      if (recorder.state === "recording") recorder.stop(); // 녹화 중지 (onstop 발동되지만 서버로는 안 감)
      showToastMessage("🚫 녹화가 취소되었습니다.", 2000);
    };

  } catch (err) {
    console.error("녹화 실패:", err);
    showToastMessage("❌ 보안(CORS)이 걸려있거나 캡처할 수 없는 영상입니다.", 4000);
  }
}

// [8] 비디오 모달창 (다시 시도 기능 추가)
function showVideoResultModal(videoSrc, videoBlob) { // 👈 인자에 videoBlob 추가됨
  const root = getShadowRoot();
  const oldModal = root.querySelector("#deepfake-result-modal");
  if (oldModal) oldModal.remove();

  const modal = document.createElement("div");
  modal.id = "deepfake-result-modal";
  modal.style.pointerEvents = "auto";

  modal.innerHTML = `
    <div class="modal-header">AI 영상 분석 결과</div>
    <video src="${videoSrc}" class="modal-media" autoplay loop muted playsinline></video>
    <div id="video-analysis-status" class="modal-status-text">서버 전송 및 분석 중...</div>
    <div class="progress-bar"><div class="progress-fill" id="video-fill" style="width: 40%;"></div></div>
    
    <div id="video-error-container" style="display: none; width: 100%;">
      <p id="video-error-msg" class="error-msg">연결 실패</p>
      <div class="btn-group">
        <button id="video-retry-btn" class="modal-btn retry-btn">다시 시도</button>
      </div>
    </div>
    
    <div class="btn-group" style="margin-top: 12px;">
      <button class="modal-btn close-btn">닫기</button>
    </div>
  `;
  root.appendChild(modal);

  modal.querySelector(".close-btn").onclick = () => {
    chrome.runtime.sendMessage({ action: "CANCEL_ANALYSIS" });
    modal.remove();
  };

  // 재사용을 위해 분석 요청 로직을 함수로 묶음
  const sendVideoAnalysis = () => {
    // UI 초기화
    root.querySelector("#video-analysis-status").innerText = "서버 전송 및 분석 중...";
    root.querySelector("#video-fill").style.width = "40%";
    root.querySelector("#video-fill").style.backgroundColor = "#007aff";
    root.querySelector("#video-error-container").style.display = "none";

    // 원본 비디오(Blob)를 Base64로 변환해서 백그라운드로 전송
    const reader = new FileReader();
    reader.readAsDataURL(videoBlob);
    reader.onloadend = () => {
      const base64data = reader.result;
      chrome.runtime.sendMessage({ action: "ANALYZE_VIDEO_API", videoDataUrl: base64data }, (response) => {
        updateVideoResultUI(response);
      });
    };
  };

  modal.querySelector("#video-retry-btn").onclick = sendVideoAnalysis;

  sendVideoAnalysis();
}

function updateVideoResultUI(response) {
  const root = getShadowRoot();
  const statusTxt = root.querySelector("#video-analysis-status");
  const progressFill = root.querySelector("#video-fill");
  const errorContainer = root.querySelector("#video-error-container");

  if (chrome.runtime.lastError || !response || (!response.success && response.error)) {
    statusTxt.innerText = "분석 실패 (통신 에러)";
    progressFill.style.backgroundColor = "#ff3b30";
    root.querySelector("#video-error-msg").innerText = response && response.error ? response.error : "서버 응답 없음";
    errorContainer.style.display = "block";
    return;
  }

  const data = response.data || response;
  const prob = data.predicted_probability !== undefined ? (data.predicted_probability * 100).toFixed(2) : 0;
  const isReal = data.predicted_label === "Real Video" || data.predicted_label === "Real Image" || data.predicted_label === "Real";
  const labelText = isReal ? "진짜(원본) 영상" : "딥페이크 의심";
  const labelColor = isReal ? "#34c759" : "#ff3b30";

  statusTxt.innerHTML = `<strong>결과: <span style="color:${labelColor};">${labelText}</span></strong> <br><span style="font-size: 12px; color:#86868b;">(딥페이크 확률: ${prob}%)</span>`;
  progressFill.style.width = `${prob}%`;
  progressFill.style.backgroundColor = labelColor;
}