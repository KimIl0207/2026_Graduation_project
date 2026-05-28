// 1. 이미지 영역 드래그 버튼 클릭 시
document.getElementById('btn-image').addEventListener('click', () => {
    // 현재 활성화된(보고 있는) 탭을 찾아서
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs[0]) {
            // content.js 로 드래그 모드 켜기 신호 전송
            chrome.tabs.sendMessage(tabs[0].id, { action: "ENABLE_SELECTION" }).catch(err => console.error(err));
            // 신호를 보낸 후 팝업창은 스스로 닫힘
            window.close();
        }
    });
});

// 2. 영상 태그 인식 버튼 클릭 시
document.getElementById('btn-video').addEventListener('click', () => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs[0]) {
            // content.js 로 태그 인식 모드 켜기 신호 전송
            chrome.tabs.sendMessage(tabs[0].id, { action: "ENABLE_ELEMENT_PICKER" }).catch(err => console.error(err));
            window.close();
        }
    });
});