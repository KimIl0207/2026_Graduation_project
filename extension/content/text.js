// content/text.js
// ==========================================
// [텍스트 모듈] 텍스트 분석 로직
// ==========================================

/**
 * AI 텍스트 분석 결과 모달을 화면에 표시합니다.
 * @param {string} text - 분석할 대상 텍스트
 */
function showTextResultModal(text) {
    // common.js에 정의된 getShadowRoot 호출
    const root = getShadowRoot();

    // 기존에 열려있는 모달이 있다면 제거
    const oldModal = root.querySelector("#deepfake-result-modal");
    if (oldModal) oldModal.remove();

    const modal = document.createElement("div");
    modal.id = "deepfake-result-modal";
    modal.style.pointerEvents = "auto";

    // 분석 대상 텍스트 미리보기 (최대 100자)
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

    // [닫기] 버튼: 분석 취소 메시지 전송 및 모달 제거
    modal.querySelector(".close-btn").onclick = () => {
        chrome.runtime.sendMessage({ action: "CANCEL_ANALYSIS" });
        modal.remove();
    };

    /**
     * 실제 백엔드 API로 분석을 요청하는 내부 함수
     */
    const sendTextAnalysis = () => {
        // UI 초기화: 에러 숨김, 게이지 파란색 복구
        statusTxt = root.querySelector("#text-analysis-status");
        progressFill = root.querySelector("#text-fill");
        errorContainer = root.querySelector("#text-error-container");

        statusTxt.innerText = "서버 전송 및 분석 중...";
        progressFill.style.width = "40%";
        progressFill.style.backgroundColor = "#007aff";
        errorContainer.style.display = "none";

        // background.js로 분석 요청 전달
        chrome.runtime.sendMessage({ action: "ANALYZE_TEXT_API", text: text }, (response) => {
            updateTextResultUI(response);
        });
    };

    // [다시 시도] 버튼 이벤트 연결
    modal.querySelector("#text-retry-btn").onclick = sendTextAnalysis;

    // 모달 생성 즉시 분석 시작
    sendTextAnalysis();
}

/**
 * 분석 결과를 받아 UI(텍스트 및 게이지바)를 업데이트합니다.
 * @param {Object} response - background.js로부터 받은 응답 객체
 */
function updateTextResultUI(response) {
    const root = getShadowRoot();
    const statusTxt = root.querySelector("#text-analysis-status");
    const progressFill = root.querySelector("#text-fill");
    const errorContainer = root.querySelector("#text-error-container");

    // 통신 실패 처리
    if (chrome.runtime.lastError || !response || (!response.success && response.error)) {
        statusTxt.innerText = "분석 실패 (통신 에러)";
        progressFill.style.backgroundColor = "#ff3b30"; // 에러 레드
        root.querySelector("#text-error-msg").innerText =
            (response && response.error) ? response.error : "서버 응답 없음";
        errorContainer.style.display = "block";
        return;
    }

    // 통신 성공: 데이터 파싱 (0~100 수치 사용)
    const data = response.data || response;
    const prob = data.final_ai_prob !== undefined ? data.final_ai_prob : 0;

    // AI 판정 기준 (60% 이상일 경우 AI로 간주)
    const isAI = data.decision === "AI" || prob >= 60;
    const labelText = isAI ? "AI 작성 의심" : "사람이 작성함";
    const labelColor = isAI ? "#ff3b30" : "#34c759"; // AI면 레드, 사람이면 그린

    // UI 업데이트
    statusTxt.innerHTML = `
        <strong>결과: <span style="color:${labelColor};">${labelText}</span></strong>
        <br><span style="font-size: 12px; color:#86868b;">(AI 확률: ${prob.toFixed(2)}%)</span>
    `;
    progressFill.style.width = `${prob}%`;
    progressFill.style.backgroundColor = labelColor;
}