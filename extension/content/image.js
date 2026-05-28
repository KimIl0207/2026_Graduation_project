// ==========================================
// [이미지 모듈] 드래그 캡처 및 분석 로직
// ==========================================
let isSelecting = false;
let startX, startY, selectionBox;

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
    <img src="${imgSrc}" class="modal-media">
    <div id="img-analysis-status" class="modal-status-text">서버 전송 및 분석 중...</div>
    <div class="progress-bar"><div class="progress-fill" id="img-fill" style="width: 40%;"></div></div>
    <div id="img-error-container" style="display: none; width: 100%;">
      <p id="img-error-msg" class="error-msg">연결 실패</p>
      <div class="btn-group"><button id="img-retry-btn" class="modal-btn retry-btn">다시 시도</button></div>
    </div>
    <div class="btn-group" style="margin-top: 12px;"><button class="modal-btn close-btn">닫기</button></div>
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

    if (chrome.runtime.lastError || !response || (!response.success && response.error)) {
        statusTxt.innerText = "분석 실패 (통신 에러)";
        progressFill.style.backgroundColor = "#ff3b30";
        root.querySelector("#img-error-msg").innerText = response && response.error ? response.error : "서버 응답 없음";
        errorContainer.style.display = "block";
        return;
    }

    const data = response.data || response;
    const prob = data.predicted_probability !== undefined ? (data.predicted_probability * 100).toFixed(2) : 0;
    const isReal = data.predicted_label === "Real Image" || data.predicted_label === "Real";
    const labelText = isReal ? "진짜(원본)" : "딥페이크 의심";
    const labelColor = isReal ? "#34c759" : "#ff3b30";

    statusTxt.innerHTML = `<strong>결과: <span style="color:${labelColor};">${labelText}</span></strong> <br><span style="font-size: 12px; color:#86868b;">(딥페이크 확률: ${prob}%)</span>`;
    progressFill.style.width = `${prob}%`;
    progressFill.style.backgroundColor = labelColor;
}