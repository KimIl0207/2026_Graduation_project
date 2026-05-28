// 페이지가 열릴 때, 기존에 저장된 주소가 있으면 불러와서 입력창에 채워줌
document.addEventListener('DOMContentLoaded', () => {
    chrome.storage.local.get(['serverUrl'], (result) => {
        if (result.serverUrl) {
            document.getElementById('server-url').value = result.serverUrl;
        }
    });
});

// 저장 버튼을 눌렀을 때의 동작
document.getElementById('save-btn').addEventListener('click', () => {
    let url = document.getElementById('server-url').value.trim();

    // 주소 끝에 슬래시(/)가 있다면 제거해서 깔끔하게 만듦
    if (url.endsWith('/')) {
        url = url.slice(0, -1);
    }

    // 크롬 로컬 저장소에 저장
    chrome.storage.local.set({ serverUrl: url }, () => {
        const status = document.getElementById('status');
        status.textContent = "주소가 성공적으로 저장되었습니다!";
        setTimeout(() => {
            status.textContent = "";
        }, 2000);
    });
});