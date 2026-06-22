const CONFIG = {
  CAPTURE_DELAY_MS: 50,
  VIDEO_RECORD_SECONDS: 5,
  VIDEO_TIMEOUT_MS: 5000,
  TOAST_DURATION_MS: 3000
};

let isSelecting = false;
let startX, startY, selectionBox;

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

function finishSelection(e) {
  isSelecting = false;
  document.body.style.cursor = "default";
  document.body.style.userSelect = "";
  document.body.style.webkitUserSelect = "";
  document.removeEventListener("mousemove", resizeSelection);

  const rect = selectionBox.getBoundingClientRect();
  selectionBox.style.display = "none";

  if (rect.width < 5 || rect.height < 5) {
    selectionBox.remove();
    return;
  }

  setTimeout(() => {
    chrome.runtime.sendMessage({ action: "CAPTURE_VISIBLE" }, (response) => {
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
      img, rect.left * dpr, rect.top * dpr, rect.width * dpr, rect.height * dpr,
      0, 0, rect.width * dpr, rect.height * dpr
    );
    const croppedImg = canvas.toDataURL("image/jpeg", 1.0);
    showImageResultModal(croppedImg);
  };
  img.src = dataUrl;
}

function showImageResultModal(imgSrc) {
  const root = getShadowRoot();
  const oldModal = root.querySelector("#deepfake-result-modal");
  if (oldModal) oldModal.remove();

  const modal = document.createElement("div");
  modal.id = "deepfake-result-modal";
  modal.style.pointerEvents = "auto";

  modal.innerHTML = `
    <div class="modal-header">AI 이미지 분석 결과</div>
    <div class="media-container" style="position: relative; width: 100%;">
      <img src="${imgSrc}" class="modal-media" style="display: block; margin-bottom: 0;">
      <img id="img-gradcam-overlay" class="modal-media" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: none; opacity: 0.65; pointer-events: none; margin-bottom: 0; border-radius: 12px;">
    </div>
    
    <div id="img-analysis-status" class="modal-status-text" style="margin-top: 12px;">서버 전송 및 분석 중...</div>
    <div class="progress-bar"><div class="progress-fill" id="img-fill" style="width: 40%;"></div></div>
    
    <div id="img-detail-report" style="display: none; width: 100%; max-height: 180px; overflow-y: auto; background: rgba(0,0,0,0.04); padding: 12px; border-radius: 10px; font-size: 13px; margin-bottom: 12px; box-sizing: border-box; text-align: left; line-height: 1.45;">
    </div>

    <div id="img-error-container" style="display: none; width: 100%;">
      <p id="img-error-msg" class="error-msg">연결 실패</p>
    </div>
    <div class="button-row">
      <button id="img-retry-btn" class="modal-btn retry-btn" style="display: none;">다시 시도</button>
      <button id="img-toggle-report-btn" class="modal-btn" style="display: none; background: #8e8e93; color: white;">세부 정보 보기</button>
      <button class="modal-btn close-btn">닫기</button>
    </div>
  `;
  root.appendChild(modal);

  modal.querySelector(".close-btn").onclick = () => {
    chrome.runtime.sendMessage({ action: "CANCEL_ANALYSIS" });
    modal.remove();
  };

  const sendImageAnalysis = () => {
    root.querySelector("#img-analysis-status").innerText = "서버 전송 및 분석 중...";
    root.querySelector("#img-fill").style.width = "40%";
    root.querySelector("#img-fill").style.backgroundColor = "#007aff";
    root.querySelector("#img-error-container").style.display = "none";
    root.querySelector("#img-retry-btn").style.display = "none";
    root.querySelector("#img-toggle-report-btn").style.display = "none";
    root.querySelector("#img-detail-report").style.display = "none";

    chrome.runtime.sendMessage({ action: "ANALYZE_IMAGE_API", imgSrc: imgSrc }, (response) => {
      updateImageResultUI(response);
    });
  };

  modal.querySelector("#img-retry-btn").onclick = sendImageAnalysis;
  sendImageAnalysis();
}

function updateImageResultUI(response) {
  const root = getShadowRoot();
  const statusTxt = root.querySelector("#img-analysis-status");
  const progressFill = root.querySelector("#img-fill");
  const errorContainer = root.querySelector("#img-error-container");
  const retryBtn = root.querySelector("#img-retry-btn");
  const toggleReportBtn = root.querySelector("#img-toggle-report-btn");
  const detailReport = root.querySelector("#img-detail-report");
  const gradCamOverlay = root.querySelector("#img-gradcam-overlay");

  if (chrome.runtime.lastError || !response || (!response.success && response.error)) {
    statusTxt.innerText = "분석 실패 (통신 에러)";
    progressFill.style.backgroundColor = "#ff3b30";
    root.querySelector("#img-error-msg").innerText = response && response.error ? response.error : "서버 응답 없음";
    if (errorContainer) errorContainer.style.display = "block";
    if (retryBtn) retryBtn.style.display = "block";
    return;
  }

  const data = response.data || response;

  let rawScore = 0;
  if (data.suspicious_score !== undefined) rawScore = data.suspicious_score;
  else if (data.predicted_probability !== undefined) rawScore = data.predicted_probability;
  else if (data.prob !== undefined) rawScore = data.prob;

  let finalProb = parseFloat(rawScore);
  if (isNaN(finalProb)) finalProb = 0;
  if (finalProb >= 0 && finalProb <= 1.0) finalProb = finalProb * 100;

  const labelText = data.label ? data.label : "판별 완료";
  const isFake = labelText.toLowerCase().includes("fake") || labelText.toLowerCase().includes("generated") || finalProb >= 50;
  const labelColor = isFake ? "#ff3b30" : "#34c759";

  let displayLabel = isFake ? "딥페이크 의심" : "진짜(원본)";
  if (labelText.toLowerCase().includes("human")) displayLabel = "실제 인물 확인";

  statusTxt.innerHTML = `<strong>결과: <span style="color:${labelColor};">${displayLabel}</span></strong> <br><span style="font-size: 12px; color:#86868b;">(딥페이크 확률: ${finalProb.toFixed(2)}%)</span>`;
  progressFill.style.width = `${finalProb}%`;
  progressFill.style.backgroundColor = labelColor;
  if (retryBtn) retryBtn.style.display = "none";

  if (toggleReportBtn && detailReport) {
    toggleReportBtn.style.display = "block";
    let reportHtml = `<strong style="color:#1d1d1f; font-size:14px;">🔍 탐지 모델 세부 지표</strong><hr style="border:0; border-top:1px solid rgba(60,60,67,0.15); margin:6px 0;">`;

    // ⚙️ 1. 알고리즘별 합성 지표 자동 순회 (mj6, univfd 포함)
    if (data.model_probs) {
      reportHtml += `<p style="margin:4px 0; font-weight:600;">[알고리즘별 합성 지표]</p><ul style="margin:2px 0 6px 0; padding-left:18px; color:#424245;">`;
      for (const [modelName, score] of Object.entries(data.model_probs)) {
        if (score !== null && score !== undefined) {
          const percent = (parseFloat(score) * (score <= 1.0 ? 100 : 1)).toFixed(1);
          reportHtml += `<li>${modelName.toUpperCase()}: <span style="font-weight:600; color:#1d1d1f;">${percent}%</span></li>`;
        }
      }
      reportHtml += `</ul>`;
    }

    // 🧠 2. 복합 신경망 융합 분석 필드 연동
    if (data.signals) {
      reportHtml += `<p style="margin:6px 0 2px 0; font-weight:600;">[신경망 판독 시그널]</p>`;
      reportHtml += `<div style="color:#424245; padding-left:4px; font-size:12px;">`;
      if (data.signals.model_fusion !== undefined) reportHtml += `• 종합 모델 융합 복잡도: ${(data.signals.model_fusion * 100).toFixed(1)}%<br>`;
      if (data.signals.model_disagreement !== undefined) reportHtml += `• 픽셀 변형 불일치도: ${(data.signals.model_disagreement * 100).toFixed(1)}%<br>`;

      if (data.signals.active_fusion_models && data.signals.active_fusion_models.length > 0) {
        const activeModels = data.signals.active_fusion_models.join(', ').toUpperCase();
        reportHtml += `• 실시간 가동 신경망: <span style="color:#1d1d1f; font-weight:600;">${activeModels}</span><br>`;
      }
      reportHtml += `</div>`;
    }

    // 🗺️ 3. Grad-CAM 히트맵 처리
    if (data.grad_cam) {
      if (data.grad_cam.image_base64) {
        const srcPrefix = data.grad_cam.image_base64.startsWith('data:') ? '' : 'data:image/jpeg;base64,';
        gradCamOverlay.src = srcPrefix + data.grad_cam.image_base64;
      }
      if (data.grad_cam.note) {
        reportHtml += `<p style="margin:8px 0 0 0; color:#007aff; font-weight:500; font-size:12px;">💡 AI 분석 코멘트: ${data.grad_cam.note}</p>`;
      }
    }

    detailReport.innerHTML = reportHtml;

    toggleReportBtn.onclick = () => {
      if (detailReport.style.display === "none") {
        detailReport.style.display = "block";
        toggleReportBtn.innerText = "세부 정보 접기";
        if (gradCamOverlay.src) gradCamOverlay.style.display = "block";
      } else {
        detailReport.style.display = "none";
        toggleReportBtn.innerText = "세부 정보 보기";
        gradCamOverlay.style.display = "none";
      }
    };
  }
}

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
    
    <div id="text-detail-report" style="display: none; width: 100%; max-height: 180px; overflow-y: auto; background: rgba(0,0,0,0.04); padding: 12px; border-radius: 10px; font-size: 13px; margin-bottom: 12px; box-sizing: border-box; text-align: left; line-height: 1.45;">
    </div>

    <div id="text-error-container" style="display: none; width: 100%;">
      <p id="text-error-msg" class="error-msg">연결 실패</p>
    </div>
    <div class="button-row">
      <button id="text-retry-btn" class="modal-btn retry-btn" style="display: none;">다시 시도</button>
      <button id="text-toggle-report-btn" class="modal-btn" style="display: none; background: #8e8e93; color: white;">세부 정보 보기</button>
      <button class="modal-btn close-btn">닫기</button>
    </div>
  `;
  root.appendChild(modal);

  modal.querySelector(".close-btn").onclick = () => {
    chrome.runtime.sendMessage({ action: "CANCEL_ANALYSIS" });
    modal.remove();
  };

  const sendTextAnalysis = () => {
    const statusTxt = root.querySelector("#text-analysis-status");
    const progressFill = root.querySelector("#text-fill");
    const errorContainer = root.querySelector("#text-error-container");
    const retryBtn = root.querySelector("#text-retry-btn");
    const toggleReportBtn = root.querySelector("#text-toggle-report-btn");
    const detailReport = root.querySelector("#text-detail-report");

    statusTxt.innerText = "서버 전송 및 분석 중...";
    progressFill.style.width = "40%";
    progressFill.style.backgroundColor = "#007aff";
    errorContainer.style.display = "none";
    if (retryBtn) retryBtn.style.display = "none";
    if (toggleReportBtn) toggleReportBtn.style.display = "none";
    if (detailReport) detailReport.style.display = "none";

    chrome.runtime.sendMessage({ action: "ANALYZE_TEXT_API", text: text }, (response) => {
      updateTextResultUI(response);
    });
  };

  modal.querySelector("#text-retry-btn").onclick = sendTextAnalysis;
  sendTextAnalysis();
}

function updateTextResultUI(response) {
  const root = getShadowRoot();
  const statusTxt = root.querySelector("#text-analysis-status");
  const progressFill = root.querySelector("#text-fill");
  const errorContainer = root.querySelector("#text-error-container");
  const retryBtn = root.querySelector("#text-retry-btn");
  const toggleReportBtn = root.querySelector("#text-toggle-report-btn");
  const detailReport = root.querySelector("#text-detail-report");

  if (chrome.runtime.lastError || !response || (!response.success && response.error)) {
    statusTxt.innerText = "분석 실패 (통신 에러)";
    progressFill.style.backgroundColor = "#ff3b30";
    root.querySelector("#text-error-msg").innerText = response && response.error ? response.error : "서버 응답 없음";
    if (errorContainer) errorContainer.style.display = "block";
    if (retryBtn) retryBtn.style.display = "block";
    return;
  }

  const data = response.data || response;

  let rawProb = 0;
  if (data.final_ai_prob !== undefined) rawProb = data.final_ai_prob;
  else if (data.predicted_probability !== undefined) rawProb = data.predicted_probability;

  let finalProb = parseFloat(rawProb);
  if (isNaN(finalProb)) finalProb = 0;
  if (finalProb >= 0 && finalProb <= 1.0) finalProb = finalProb * 100;

  const isAI = data.decision === "AI" || finalProb >= 60;
  const labelText = isAI ? "AI 작성 의심" : "사람이 작성함";
  const labelColor = isAI ? "#ff3b30" : "#34c759";

  statusTxt.innerHTML = `<strong>결과: <span style="color:${labelColor};">${labelText}</span></strong> <br><span style="font-size: 12px; color:#86868b;">(AI 확률: ${finalProb.toFixed(2)}%)</span>`;
  progressFill.style.width = `${finalProb}%`;
  progressFill.style.backgroundColor = labelColor;
  if (retryBtn) retryBtn.style.display = "none";

  if (toggleReportBtn && detailReport) {
    toggleReportBtn.style.display = "block";
    let reportHtml = `<strong style="color:#1d1d1f; font-size:14px;">🔍 텍스트 언어모델 신경망 데이터</strong><hr style="border:0; border-top:1px solid rgba(60,60,67,0.15); margin:6px 0;">`;

    reportHtml += `<div style="color:#424245;">`;
    if (data.language) reportHtml += `• 감지된 언어: <strong>${data.language.toUpperCase()}</strong><br>`;
    if (data.roberta_ai_prob !== undefined) reportHtml += `• RoBERTa 신경망 스코어: ${(data.roberta_ai_prob * (data.roberta_ai_prob <= 1 ? 100 : 1)).toFixed(1)}%<br>`;
    if (data.perplexity !== undefined) reportHtml += `• Perplexity (문장 복잡도): ${data.perplexity.toFixed(2)}<br>`;
    if (data.burstiness !== undefined) reportHtml += `• Burstiness (문장 변동성): ${data.burstiness.toFixed(2)}<br>`;
    reportHtml += `</div>`;

    if (data.sentence_highlights && data.sentence_highlights.length > 0) {
      reportHtml += `<p style="margin:8px 0 4px 0; font-weight:600; color:#ff3b30;">[AI 생성 의심 문장 구간 리포트]</p>`;
      reportHtml += `<ol style="margin:2px 0 0 0; padding-left:18px; color:#515154; font-size:12px;">`;
      data.sentence_highlights.forEach((item) => {
        if (item.text) {
          const scoreText = item.ai_prob !== undefined ? ` (의심도: ${(item.ai_prob * (item.ai_prob <= 1 ? 100 : 1)).toFixed(0)}%)` : '';
          reportHtml += `<li style="margin-bottom:4px; word-break:break-all;">"${item.text}" <span style="color:#ff3b30; font-weight:600;">${scoreText}</span></li>`;
        }
      });
      reportHtml += `</ol>`;
    }

    detailReport.innerHTML = reportHtml;
    toggleReportBtn.onclick = () => {
      if (detailReport.style.display === "none") detailReport.style.display = "block";
      else detailReport.style.display = "none";
    };
  }
}

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

  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

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

  if (target.tagName.toLowerCase() !== 'video') {
    showToastMessage("⚠️ 동영상(video) 태그가 아닙니다! 재생 중인 영상 위를 클릭해주세요.", 3000);
    return;
  }
  startDirectVideoRecording(target);
}

async function startDirectVideoRecording(videoElement) {
  try {
    const stream = videoElement.captureStream ? videoElement.captureStream() : videoElement.mozCaptureStream();
    if (!stream) throw new Error("스트림을 추출할 수 없습니다.");

    const recorder = new MediaRecorder(stream, { mimeType: "video/webm" });
    const collectedFrames = [];
    let isCanceled = false;

    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");

    const captureInterval = setInterval(() => {
      if (isCanceled) return;
      canvas.width = videoElement.videoWidth || videoElement.clientWidth;
      canvas.height = videoElement.videoHeight || videoElement.clientHeight;
      ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);

      const frameDataUrl = canvas.toDataURL("image/jpeg", 0.85);
      collectedFrames.push(frameDataUrl);
      console.log(`[프레임 데이터 적재 수집] 현재 카운트: ${collectedFrames.length}장`);
    }, 1000);

    recorder.onstop = () => {
      clearInterval(captureInterval);
      if (isCanceled) return;

      const previewImg = collectedFrames[collectedFrames.length - 1] || "";
      showVideoResultModal(previewImg, collectedFrames);
    };

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
    recordingUI.style.pointerEvents = "auto";

    const timerText = document.createElement("span");
    let timeLeft = CONFIG.VIDEO_RECORD_SECONDS;
    timerText.innerHTML = `🔴 영상 데이터 추출 중... <strong>${timeLeft}초</strong> 남음`;

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

    recorder.start();

    const timerInterval = setInterval(() => {
      timeLeft--;
      if (timeLeft >= 0) {
        timerText.innerHTML = `영상 데이터 추출 중... <strong>${timeLeft}초</strong> 남음`;
      }
    }, 1000);

    const stopTimeout = setTimeout(() => {
      clearInterval(timerInterval);
      recordingUI.remove();
      if (recorder.state === "recording") recorder.stop();
    }, CONFIG.VIDEO_TIMEOUT_MS);

    cancelBtn.onclick = () => {
      isCanceled = true;
      clearInterval(timerInterval);
      clearInterval(captureInterval);
      clearTimeout(stopTimeout);
      recordingUI.remove();
      if (recorder.state === "recording") recorder.stop();
      showToastMessage("🚫 작업이 취소되었습니다.", 2000);
    };

  } catch (err) {
    console.error("녹화 실패:", err);
    showToastMessage("❌ 보안(CORS)이 걸려있거나 캡처할 수 없는 영상입니다.", 4000);
  }
}

// ==========================================================================
// 🎥 비디오 모달 및 데이터 처리 파트 (인물 신뢰도 제거 반영)
// ==========================================================================
function showVideoResultModal(frameSnapshotUrl, collectedFrames) {
  const root = getShadowRoot();
  const oldModal = root.querySelector("#deepfake-result-modal");
  if (oldModal) oldModal.remove();

  const modal = document.createElement("div");
  modal.id = "deepfake-result-modal";
  modal.style.pointerEvents = "auto";

  modal.innerHTML = `
    <div class="modal-header">AI 영상 분석 결과</div>
    <div class="media-container" style="position: relative; width: 100%;">
      <img src="${frameSnapshotUrl}" class="modal-media" style="display: block; margin-bottom: 0;">
      <img id="video-gradcam-overlay" class="modal-media" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: none; opacity: 0.65; pointer-events: none; margin-bottom: 0; border-radius: 12px;">
    </div>
    
    <div id="video-analysis-status" class="modal-status-text" style="margin-top: 12px;">프레임 리스트 서버 전송 중...</div>
    <div class="progress-bar"><div class="progress-fill" id="video-fill" style="width: 40%;"></div></div>
    
    <div id="video-detail-report" style="display: none; width: 100%; max-height: 180px; overflow-y: auto; background: rgba(0,0,0,0.04); padding: 12px; border-radius: 10px; font-size: 13px; margin-bottom: 12px; box-sizing: border-box; text-align: left; line-height: 1.45;">
    </div>
    
    <div id="video-error-container" style="display: none; width: 100%;">
      <p id="video-error-msg" class="error-msg">연결 실패</p>
    </div>
    <div class="button-row">
      <button id="video-retry-btn" class="modal-btn retry-btn" style="display: none;">다시 시도</button>
      <button id="video-toggle-report-btn" class="modal-btn" style="display: none; background: #8e8e93; color: white;">세부 정보 보기</button>
      <button class="modal-btn close-btn">닫기</button>
    </div>
  `;
  root.appendChild(modal);

  modal.querySelector(".close-btn").onclick = () => {
    chrome.runtime.sendMessage({ action: "CANCEL_ANALYSIS" });
    modal.remove();
  };

  const sendVideoAnalysis = () => {
    root.querySelector("#video-analysis-status").innerText = "프레임 리스트 서버 분석 중...";
    root.querySelector("#video-fill").style.width = "40%";
    root.querySelector("#video-fill").style.backgroundColor = "#007aff";
    root.querySelector("#video-error-container").style.display = "none";
    root.querySelector("#video-retry-btn").style.display = "none";
    root.querySelector("#video-toggle-report-btn").style.display = "none";
    root.querySelector("#video-detail-report").style.display = "none";

    chrome.runtime.sendMessage({ action: "ANALYZE_VIDEO_LIST_API", imgSrcList: collectedFrames }, (response) => {
      updateVideoResultUI(response);
    });
  };

  modal.querySelector("#video-retry-btn").onclick = sendVideoAnalysis;
  sendVideoAnalysis();
}

function updateVideoResultUI(response) {
  const root = getShadowRoot();
  const statusTxt = root.querySelector("#video-analysis-status");
  const progressFill = root.querySelector("#video-fill");
  const errorContainer = root.querySelector("#video-error-container");
  const retryBtn = root.querySelector("#video-retry-btn");
  const toggleReportBtn = root.querySelector("#video-toggle-report-btn");
  const detailReport = root.querySelector("#video-detail-report");
  const gradCamOverlay = root.querySelector("#video-gradcam-overlay");

  if (chrome.runtime.lastError || !response || (!response.success && response.error)) {
    statusTxt.innerText = "분석 실패 (통신 에러)";
    progressFill.style.backgroundColor = "#ff3b30";
    root.querySelector("#video-error-msg").innerText = response && response.error ? response.error : "서버 응답 없음";
    if (errorContainer) errorContainer.style.display = "block";
    if (retryBtn) retryBtn.style.display = "block";
    return;
  }

  const data = response.data || response;

  let rawScore = 0;
  if (data.suspicious_score !== undefined) rawScore = data.suspicious_score;
  else if (data.prob !== undefined) rawScore = data.prob;
  else if (data.predicted_probability !== undefined) rawScore = data.predicted_probability;

  let finalProb = parseFloat(rawScore);
  if (isNaN(finalProb)) finalProb = 0;
  if (finalProb >= 0 && finalProb <= 1.0) finalProb = finalProb * 100;

  const labelText = data.label ? data.label : "판별 완료";
  const isFake = labelText.toLowerCase().includes("fake") || labelText.toLowerCase().includes("generated") || finalProb >= 50;
  const displayLabel = isFake ? "딥페이크 의심 영상" : "진짜(원본) 영상";
  const labelColor = isFake ? "#ff3b30" : "#34c759";

  statusTxt.innerHTML = `<strong>결과: <span style="color:${labelColor};">${displayLabel}</span></strong> <br><span style="font-size: 12px; color:#86868b;">(딥페이크 확률: ${finalProb.toFixed(2)}%)</span>`;
  progressFill.style.width = `${finalProb}%`;
  progressFill.style.backgroundColor = labelColor;
  if (retryBtn) retryBtn.style.display = "none";

  if (toggleReportBtn && detailReport) {
    toggleReportBtn.style.display = "block";
    let reportHtml = `<strong style="color:#1d1d1f; font-size:14px;">🔍 AI 영상 다중 교차분석 리포트</strong><hr style="border:0; border-top:1px solid rgba(60,60,67,0.15); margin:6px 0;">`;

    if (data.frame_count !== undefined) {
      reportHtml += `<p style="margin:4px 0; color:#1d1d1f;">• 총 샘플링 프레임 수: <strong>${data.frame_count}장 (연속 프레임 추적)</strong></p>`;
    }

    // ⚙️ 알고리즘별 가중치 지표 자동 순회 파싱
    if (data.model_probs) {
      reportHtml += `<p style="margin:6px 0 2px 0; font-weight:600;">[영상 합성 알고리즘 분석]</p><ul style="margin:2px 0 6px 0; padding-left:18px; color:#424245;">`;
      for (const [modelName, score] of Object.entries(data.model_probs)) {
        if (score !== null && score !== undefined) {
          const percent = (parseFloat(score) * (score <= 1.0 ? 100 : 1)).toFixed(1);
          reportHtml += `<li>${modelName.toUpperCase()}: <span style="font-weight:600; color:#1d1d1f;">${percent}%</span></li>`;
        }
      }
      reportHtml += `</ul>`;
    }

    // 🧠 하이브리드 가동 신경망 명단 동적 매핑
    if (data.signals) {
      reportHtml += `<p style="margin:6px 0 2px 0; font-weight:600;">[프레임 연산 분석 시그널]</p>`;
      reportHtml += `<div style="color:#424245; padding-left:4px; font-size:12px;">`;
      if (data.signals.model_fusion !== undefined) reportHtml += `• 프레임 융합 복잡도: ${(data.signals.model_fusion * 100).toFixed(1)}%<br>`;
      if (data.signals.model_disagreement !== undefined) reportHtml += `• 타임라인 픽셀 불일치도: ${(data.signals.model_disagreement * 100).toFixed(1)}%<br>`;

      if (data.signals.active_fusion_models && data.signals.active_fusion_models.length > 0) {
        const activeModels = data.signals.active_fusion_models.join(', ').toUpperCase();
        reportHtml += `• 실시간 가동 신경망: <span style="color:#1d1d1f; font-weight:600;">${activeModels}</span><br>`;
      }
      reportHtml += `</div>`;
    }

    // 🗺️ Grad-CAM 및 코멘트 가공
    if (data.grad_cam) {
      if (data.grad_cam.image_base64) {
        const srcPrefix = data.grad_cam.image_base64.startsWith('data:') ? '' : 'data:image/jpeg;base64,';
        gradCamOverlay.src = srcPrefix + data.grad_cam.image_base64;
      }
      if (data.grad_cam.note) {
        reportHtml += `<p style="margin:8px 0 0 0; color:#007aff; font-weight:500; font-size:12px;">💡 AI 분석 코멘트: ${data.grad_cam.note}</p>`;
      }
    }

    detailReport.innerHTML = reportHtml;

    toggleReportBtn.onclick = () => {
      if (detailReport.style.display === "none") {
        detailReport.style.display = "block";
        toggleReportBtn.innerText = "세부 정보 접기";
        if (gradCamOverlay.src) gradCamOverlay.style.display = "block";
      } else {
        detailReport.style.display = "none";
        toggleReportBtn.innerText = "세부 정보 보기";
        gradCamOverlay.style.display = "none";
      }
    };
  }
}