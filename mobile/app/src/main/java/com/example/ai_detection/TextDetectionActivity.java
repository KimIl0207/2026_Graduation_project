package com.example.ai_detection;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;

public class TextDetectionActivity extends AppCompatActivity {

    private ActivityResultLauncher<String> filePickerLauncher;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_text_detection);

        EditText editTextInput = findViewById(R.id.editTextAnalysis);
        TextView tvCharCount = findViewById(R.id.textViewCharCount);
        TextView tvStatus = findViewById(R.id.textViewStatus);
        Button btnAnalyze = findViewById(R.id.buttonAnalyze);
        Button btnReset = findViewById(R.id.buttonReset);
        ProgressBar progressBar = findViewById(R.id.progressBarLoading);
        TextView tvHint = findViewById(R.id.textViewHint);

        // (기존) 이전 화면에서 넘어온 텍스트가 있다면 바로 쓰기
        String incomingText = getIntent().getStringExtra("textData");

        // ✨ [핵심 추가] 사용자가 꾹 눌러서(드래그) 보낸 텍스트 받기!
        CharSequence processText = getIntent().getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT);

        if (incomingText != null) {
            editTextInput.setText(incomingText);
        } else if (processText != null) {
            editTextInput.setText(processText.toString());
        }

        filePickerLauncher = registerForActivityResult(
                new ActivityResultContracts.GetContent(),
                uri -> {
                    if (uri != null) {
                        String mimeType = getContentResolver().getType(uri);
                        String uriStr = uri.toString().toLowerCase();

                        if ((mimeType != null && mimeType.startsWith("image/")) || uriStr.contains(".jpg") || uriStr.contains(".png") || uriStr.contains(".jpeg")) {
                            Intent intent = new Intent(this, ImageDetectionActivity.class);
                            intent.setData(uri);
                            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                            startActivity(intent);
                            finish();
                        } else if ((mimeType != null && mimeType.startsWith("text/")) || uriStr.contains(".txt")) {
                            editTextInput.setText(readTextFile(uri));
                        } else {
                            Toast.makeText(this, "지원하지 않는 파일입니다 (.txt, .jpg, .png 등만 가능)", Toast.LENGTH_SHORT).show();
                        }
                    }
                }
        );

        TextView navFile = findViewById(R.id.navFile);
        navFile.setOnClickListener(v -> filePickerLauncher.launch("*/*"));

        TextView navImage = findViewById(R.id.navImage);
        navImage.setOnClickListener(v -> {
            startActivity(new Intent(this, ImageDetectionActivity.class));
            finish();
        });

        editTextInput.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                tvCharCount.setText(s.length() + "/500자");
                if (s.length() > 0) tvHint.setVisibility(View.GONE);
                else tvHint.setVisibility(View.VISIBLE);
            }
            @Override
            public void afterTextChanged(Editable s) {}
        });

        btnAnalyze.setOnClickListener(v -> {
            progressBar.setVisibility(View.VISIBLE);
            tvStatus.setText("AI가 작성했는지 판독하고 있어요!");
            new Handler(Looper.getMainLooper()).postDelayed(() -> {
                progressBar.setVisibility(View.GONE);
                tvStatus.setText("분석 완료: AI가 작성했을 확률 92% 입니다.");
            }, 2000);
        });

        btnReset.setOnClickListener(v -> {
            editTextInput.setText("");
            tvStatus.setText("AI가 텍스트를 작성했는지 판독해요.");
            progressBar.setVisibility(View.GONE);
        });
    }

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