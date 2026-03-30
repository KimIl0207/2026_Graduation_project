package com.example.ai_detection;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Bundle;
import android.widget.Toast;

public class CaptureActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        MediaProjectionManager projectionManager = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        startActivityForResult(projectionManager.createScreenCaptureIntent(), 1000);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == 1000 && resultCode == RESULT_OK) {
            Intent serviceIntent = new Intent(this, FloatingService.class);
            serviceIntent.setAction("ACTION_START_CAPTURE");
            serviceIntent.putExtra("resultCode", resultCode);
            serviceIntent.putExtra("data", data);

            // ✨ [핵심] 사용자가 누른 버튼 종류(TEXT or IMAGE)를 전달!
            serviceIntent.putExtra("captureType", getIntent().getStringExtra("captureType"));

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(serviceIntent);
            } else {
                startService(serviceIntent);
            }
        } else {
            Toast.makeText(this, "화면 캡처 권한이 거부되었습니다.", Toast.LENGTH_SHORT).show();
        }
        finish();
    }
}