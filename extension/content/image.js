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

    // 🔍 [그물망 코드] 서버가 어떤 이름으로 확률을 보내든 전부 잡아냅니다.
    let rawProb = 0;
    if (data.predicted_probability !== undefined) {
        rawProb = data.predicted_probability;
    } else if (data.prob !== undefined) {
        rawProb = data.prob;
    } else if (data.confidence !== undefined) {
        rawProb = data.confidence;
    } else if (data.probability !== undefined) {
        rawProb = data.probability;
    } else if (data.final_ai_prob !== undefined) {
        rawProb = data.final_ai_prob;
    }

    // 숫자로 안전하게 변환
    let finalProb = parseFloat(rawProb);
    if (isNaN(finalProb)) finalProb = 0;

    // 서버가 0~1 사이의 소수점으로 보냈다면 100을 곱해 퍼센트로 변환 (예: 0.954 -> 95.4)
    if (finalProb > 0 && finalProb <= 1.0) {
        finalProb = finalProb * 100;
    }

    // 판정 결과 라벨 매칭 (Real이 포함되어 있으면 진짜, 아니면 딥페이크)
    const label = (data.predicted_label || data.decision || "").toLowerCase();
    const isReal = label.includes("real") || label.includes("사람");

    const labelText = isReal ? "진짜(원본)" : "딥페이크 의심";
    const labelColor = isReal ? "#34c759" : "#ff3b30";

    // UI 업데이트 (확률 반영)
    statusTxt.innerHTML = `<strong>결과: <span style="color:${labelColor};">${labelText}</span></strong> <br><span style="font-size: 12px; color:#86868b;">(딥페이크 확률: ${finalProb.toFixed(2)}%)</span>`;
    progressFill.style.width = `${finalProb}%`;
    progressFill.style.backgroundColor = labelColor;
}