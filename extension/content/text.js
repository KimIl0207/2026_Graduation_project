// content/text.js
// ==========================================
// [텍스트 모듈] 텍스트 분석 로직
// ==========================================

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
        <div class="progress-bar">
            <div class="progress-fill" id="text-fill" style="width: 40%;"></div>
        </div>
        
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

    modal.querySelector(".close-btn").onclick = () => {
        chrome.runtime.sendMessage({ action: "CANCEL_ANALYSIS" });
        modal.remove();
    };

    const sendTextAnalysis = () => {
        // [문법 에러 고침] const 키워드 추가로 ReferenceError 근절
        const statusTxt = root.querySelector("#text-analysis-status");
        const progressFill = root.querySelector("#text-fill");
        const errorContainer = root.querySelector("#text-error-container");

        statusTxt.innerText = "서버 전송 및 분석 중...";
        progressFill.style.width = "40%";
        progressFill.style.backgroundColor = "#007aff";
        errorContainer.style.display = "none";

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

    if (chrome.runtime.lastError || !response || (!response.success && response.error)) {
        statusTxt.innerText = "분석 실패 (통신 에러)";
        progressFill.style.backgroundColor = "#ff3b30";
        root.querySelector("#text-error-msg").innerText =
            (response && response.error) ? response.error : "서버 응답 없음";
        errorContainer.style.display = "block";
        return;
    }

    const data = response.data || response;
    let prob = data.final_ai_prob !== undefined ? data.final_ai_prob : 0;
    let finalProb = parseFloat(prob);

    // 만약 텍스트도 서버가 소수점으로 주면 자동으로 100 곱해주는 로직 안전망 배치
    if (finalProb > 0 && finalProb <= 1.0) {
        finalProb = finalProb * 100;
    }

    const isAI = data.decision === "AI" || finalProb >= 60;
    const labelText = isAI ? "AI 작성 의심" : "사람이 작성함";
    const labelColor = isAI ? "#ff3b30" : "#34c759";

    statusTxt.innerHTML = `
        <strong>결과: <span style="color:${labelColor};">${labelText}</span></strong>
        <br><span style="font-size: 12px; color:#86868b;">(AI 확률: ${finalProb.toFixed(2)}%)</span>
    `;
    progressFill.style.width = `${finalProb}%`;
    progressFill.style.backgroundColor = labelColor;
}