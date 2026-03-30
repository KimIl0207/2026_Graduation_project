package com.example.ai_detection;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;

public class ProcessTextActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // 1. 사용자가 드래그한 글씨를 가져옵니다.
        CharSequence processText = getIntent().getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT);

        if (processText != null) {
            // 2. 글씨가 있다면, 플로팅 서비스에게 "이거 팝업으로 띄워!" 라고 명령을 보냅니다.
            Intent serviceIntent = new Intent(this, FloatingService.class);
            serviceIntent.setAction("ACTION_SHOW_RESULT");
            serviceIntent.putExtra("title", "📝 드래그 텍스트 판독");
            serviceIntent.putExtra("content", processText.toString());
            startService(serviceIntent);
        }

        // 3. 임무를 완수했으니 화면에 아무것도 안 띄우고 즉시 자폭(종료)합니다!
        finish();
    }
}