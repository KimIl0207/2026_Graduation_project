package com.example.ai_detection;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;

public class MainActivity extends AppCompatActivity {

    private ActivityResultLauncher<String> filePickerLauncher;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // ✨ 방금 보내주신 activity_main.xml 화면을 연결합니다.
        setContentView(R.layout.activity_main);

        filePickerLauncher = registerForActivityResult(
                new ActivityResultContracts.GetContent(),
                uri -> {
                    if (uri != null) {
                        String mimeType = getContentResolver().getType(uri);
                        String uriStr = uri.toString().toLowerCase();

                        // 이미지 판독 화면으로 넘기기
                        if ((mimeType != null && mimeType.startsWith("image/")) || uriStr.contains(".jpg") || uriStr.contains(".png") || uriStr.contains(".jpeg")) {
                            Intent intent = new Intent(this, ImageDetectionActivity.class);
                            intent.setData(uri);
                            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                            startActivity(intent);
                        }
                        // 텍스트 판독 화면으로 넘기기
                        else if ((mimeType != null && mimeType.startsWith("text/")) || uriStr.contains(".txt")) {
                            String extractedText = readTextFile(uri);
                            Intent intent = new Intent(this, TextDetectionActivity.class);
                            intent.putExtra("textData", extractedText);
                            startActivity(intent);
                        } else {
                            Toast.makeText(this, "지원하지 않는 파일입니다 (.txt, .jpg, .png 등만 가능)", Toast.LENGTH_SHORT).show();
                        }
                    }
                }
        );

        // ✨ XML에 있는 ID(textViewFile 등)와 정확하게 똑같이 맞췄습니다! ✨
        TextView navFile = findViewById(R.id.textViewFile);
        navFile.setOnClickListener(v -> filePickerLauncher.launch("*/*"));

        TextView navText = findViewById(R.id.textViewText);
        navText.setOnClickListener(v -> startActivity(new Intent(this, TextDetectionActivity.class)));

        TextView navImage = findViewById(R.id.textViewImage);
        navImage.setOnClickListener(v -> startActivity(new Intent(this, ImageDetectionActivity.class)));

// ✨ 새로 만든 "위젯 켜기" 버튼과 연결!
        android.widget.Button btnStartWidget = findViewById(R.id.buttonStartWidget);
        if (btnStartWidget != null) {
            btnStartWidget.setOnClickListener(v -> {
                // 권한이 있는지 확인 (다른 앱 위에 그리기 권한)
                if (!android.provider.Settings.canDrawOverlays(this)) {
                    // 권한이 없으면 설정 화면으로 쫓아내서 허락을 받아옵니다.
                    Intent intent = new Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()));
                    Toast.makeText(this, "다른 앱 위에 그리기 권한을 허용해주세요!", Toast.LENGTH_LONG).show();
                    startActivity(intent);
                } else {
                    // 권한이 있으면 백그라운드 서비스(위젯) 실행!
                    startService(new Intent(MainActivity.this, FloatingService.class));
                    Toast.makeText(this, "위젯이 켜졌습니다. 홈 화면으로 나가보세요!", Toast.LENGTH_SHORT).show();
                }
            });
        }
    }

    // 텍스트 파일 읽어주는 함수
    private String readTextFile(Uri uri) {
        StringBuilder stringBuilder = new StringBuilder();
        try (InputStream inputStream = getContentResolver().openInputStream(uri);
             BufferedReader reader = new BufferedReader(new InputStreamReader(inputStream))) {
            String line;
            while ((line = reader.readLine()) != null) {
                stringBuilder.append(line).append("\n");
            }
        } catch (Exception e) { e.printStackTrace(); }
        return stringBuilder.toString();
    }
}