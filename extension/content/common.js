// content/common.js

// [공통 1] 환경 설정
const CONFIG = {
    CAPTURE_DELAY_MS: 50,
    VIDEO_RECORD_SECONDS: 5,
    VIDEO_TIMEOUT_MS: 5000,
    TOAST_DURATION_MS: 3000
};

// [공통 2] Shadow DOM 초기화
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
        styleLink.href = chrome.runtime.getURL("content/style.css");
        extensionShadowRoot.appendChild(styleLink);
    }
    return extensionShadowRoot;
}

// [공통 3] 토스트 메시지
function showToastMessage(message, duration = CONFIG.TOAST_DURATION_MS) {
    const root = getShadowRoot();
    const toast = document.createElement("div");
    toast.style.cssText = `
        position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
        background: rgba(0, 0, 0, 0.85); color: white; padding: 12px 24px;
        border-radius: 30px; font-size: 14px; z-index: 2147483647;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2); transition: opacity 0.3s;
        pointer-events: none;
    `;
    toast.innerText = message;
    root.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 300);
    }, duration);
}