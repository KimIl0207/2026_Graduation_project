// ==========================================
// [비디오 모듈] 태그 인식, 녹화 및 분석 로직
// ==========================================
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
        const chunks = [];
        let isCanceled = false;

        recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };

        recorder.onstop = () => {
            if (isCanceled) return;
            const videoBlob = new Blob(chunks, { type: "video/webm" });
            const videoUrl = URL.createObjectURL(videoBlob);
            showVideoResultModal(videoUrl, videoBlob);
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
        recordingUI.style.display = "flex";
        recordingUI.style.alignItems = "center";
        recordingUI.style.gap = "15px";
        recordingUI.style.pointerEvents = "auto";

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

        recordingUI.appendChild(timerText);
        recordingUI.appendChild(cancelBtn);
        root.appendChild(recordingUI);

        recorder.start();
        const timerInterval = setInterval(() => {
            timeLeft--;
            if (timeLeft >= 0) timerText.innerHTML = `녹화 중... <strong>${timeLeft}초</strong> 남음`;
        }, 1000);

        const stopTimeout = setTimeout(() => {
            clearInterval(timerInterval);
            recordingUI.remove();
            if (recorder.state === "recording") recorder.stop();
        }, CONFIG.VIDEO_TIMEOUT_MS);

        cancelBtn.onclick = () => {
            isCanceled = true;
            clearInterval(timerInterval);
            clearTimeout(stopTimeout);
            recordingUI.remove();
            if (recorder.state === "recording") recorder.stop();
            showToastMessage("🚫 녹화가 취소되었습니다.", 2000);
        };
    } catch (err) {
        showToastMessage("❌ 보안(CORS)이 걸려있거나 캡처할 수 없는 영상입니다.", 4000);
    }
}

function showVideoResultModal(videoSrc, videoBlob) {
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
      <div class="btn-group"><button id="video-retry-btn" class="modal-btn retry-btn">다시 시도</button></div>
    </div>
    <div class="btn-group" style="margin-top: 12px;"><button class="modal-btn close-btn">닫기</button></div>
  `;
    root.appendChild(modal);

    modal.querySelector(".close-btn").onclick = () => {
        chrome.runtime.sendMessage({ action: "CANCEL_ANALYSIS" });
        modal.remove();
    };

    const sendVideoAnalysis = () => {
        root.querySelector("#video-analysis-status").innerText = "서버 전송 및 분석 중...";
        root.querySelector("#video-fill").style.width = "40%";
        root.querySelector("#video-fill").style.backgroundColor = "#007aff";
        root.querySelector("#video-error-container").style.display = "none";

        const reader = new FileReader();
        reader.readAsDataURL(videoBlob);
        reader.onloadend = () => {
            chrome.runtime.sendMessage({ action: "ANALYZE_VIDEO_API", videoDataUrl: reader.result }, (response) => {
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