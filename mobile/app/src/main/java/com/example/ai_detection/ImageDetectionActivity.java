package com.example.ai_detection;

import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color; // ✨ 색상 제어를 위해 추가
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;

import org.json.JSONObject; // ✨ 서버 응답(JSON) 분석을 위해 추가

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;

// ✨ 서버 통신을 위한 OkHttp 라이브러리
import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.MultipartBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

public class ImageDetectionActivity extends AppCompatActivity {

    private ActivityResultLauncher<String> galleryLauncher;
    private ActivityResultLauncher<String> filePickerLauncher;

    // ✨ 서버 통신을 위한 클라이언트 객체
    private final OkHttpClient client = new OkHttpClient();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_image_detection);

        TextView tvStatus = findViewById(R.id.textViewStatus);
        Button btnAnalyze = findViewById(R.id.buttonAnalyze);
        Button btnReset = findViewById(R.id.buttonReset);
        ProgressBar progressBar = findViewById(R.id.progressBarLoading);

        FrameLayout layoutImageArea = findViewById(R.id.layoutImageArea);
        TextView tvImageHint = findViewById(R.id.textViewImageHint);
        ImageView imageViewUploaded = findViewById(R.id.imageViewUploaded);

        // --- 외부 앱 공유나 위젯 캡처 등 넘어온 이미지 처리 ---
        Intent intent = getIntent();
        String action = intent.getAction();
        String type = intent.getType();

        Uri imageUri = null;

        if (intent.getData() != null) {
            imageUri = intent.getData();
        } else if (Intent.ACTION_SEND.equals(action) && type != null && type.startsWith("image/")) {
            imageUri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
        } else {
            String capturedImagePath = intent.getStringExtra("capturedImagePath");
            if (capturedImagePath != null) {
                Bitmap capturedBitmap = BitmapFactory.decodeFile(capturedImagePath);
                imageViewUploaded.setImageBitmap(capturedBitmap);
                imageViewUploaded.setVisibility(View.VISIBLE);
                tvImageHint.setVisibility(View.GONE);
            }
        }

        if (imageUri != null) {
            imageViewUploaded.setImageURI(imageUri);
            imageViewUploaded.setVisibility(View.VISIBLE);
            tvImageHint.setVisibility(View.GONE);
        }

        // 파일/텍스트 선택 핸들러
        filePickerLauncher = registerForActivityResult(
                new ActivityResultContracts.GetContent(),
                uri -> {
                    if (uri != null) {
                        String mimeType = getContentResolver().getType(uri);
                        String uriStr = uri.toString().toLowerCase();

                        if ((mimeType != null && mimeType.startsWith("image/")) || uriStr.contains(".jpg") || uriStr.contains(".png") || uriStr.contains(".jpeg")) {
                            imageViewUploaded.setImageURI(uri);
                            imageViewUploaded.setVisibility(View.VISIBLE);
                            tvImageHint.setVisibility(View.GONE);
                        } else if ((mimeType != null && mimeType.startsWith("text/")) || uriStr.contains(".txt")) {
                            String extractedText = readTextFile(uri);
                            Intent textIntent = new Intent(this, TextDetectionActivity.class);
                            textIntent.putExtra("textData", extractedText);
                            startActivity(textIntent);
                            finish();
                        }
                    }
                }
        );

        TextView navFile = findViewById(R.id.navFile);
        navFile.setOnClickListener(v -> filePickerLauncher.launch("*/*"));

        TextView navText = findViewById(R.id.navText);
        navText.setOnClickListener(v -> {
            startActivity(new Intent(this, TextDetectionActivity.class));
            finish();
        });

        galleryLauncher = registerForActivityResult(
                new ActivityResultContracts.GetContent(),
                uri -> {
                    if (uri != null) {
                        imageViewUploaded.setImageURI(uri);
                        imageViewUploaded.setVisibility(View.VISIBLE);
                        tvImageHint.setVisibility(View.GONE);
                    }
                }
        );

        layoutImageArea.setOnClickListener(v -> galleryLauncher.launch("image/*"));

        // ✨ [핵심] 판독하기 버튼: 진짜 서버 연동 로직
        btnAnalyze.setOnClickListener(v -> {
            if (imageViewUploaded.getVisibility() == View.GONE || imageViewUploaded.getDrawable() == null) {
                Toast.makeText(this, "먼저 판독할 이미지를 선택해주세요!", Toast.LENGTH_SHORT).show();
                return;
            }

            progressBar.setVisibility(View.VISIBLE);
            tvStatus.setText("AI 분석 서버와 통신 중입니다...");
            tvStatus.setTextColor(Color.BLACK); // 문구 색상 초기화

            // 1. ImageView에서 비트맵 추출
            Bitmap bitmap;
            Drawable drawable = imageViewUploaded.getDrawable();
            if (drawable instanceof BitmapDrawable) {
                bitmap = ((BitmapDrawable) drawable).getBitmap();
            } else {
                bitmap = Bitmap.createBitmap(drawable.getIntrinsicWidth(), drawable.getIntrinsicHeight(), Bitmap.Config.ARGB_8888);
                Canvas canvas = new Canvas(bitmap);
                drawable.setBounds(0, 0, canvas.getWidth(), canvas.getHeight());
                drawable.draw(canvas);
            }

            // 2. JPG 데이터로 압축 (친구 서버 요구사항)
            ByteArrayOutputStream stream = new ByteArrayOutputStream();
            bitmap.compress(Bitmap.CompressFormat.JPEG, 100, stream);
            byte[] byteArray = stream.toByteArray();

            // 3. 폼 데이터 구성 (필드명: file)
            RequestBody requestBody = new MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart("file", "detect.jpg",
                            RequestBody.create(byteArray, MediaType.parse("image/jpeg")))
                    .build();

            // 4. 서버 요청 생성
            Request request = new Request.Builder()
                    .url("https://abc8-119-207-138-153.ngrok-free.app/predict")
                    .post(requestBody)
                    .build();

            // 5. 서버 전송 및 응답 처리
            client.newCall(request).enqueue(new Callback() {
                @Override
                public void onFailure(Call call, IOException e) {
                    new Handler(Looper.getMainLooper()).post(() -> {
                        progressBar.setVisibility(View.GONE);
                        tvStatus.setText("❌ 서버 연결 실패\n(네트워크나 서버 상태를 확인해주세요)");
                        tvStatus.setTextColor(Color.RED);
                    });
                }

                @Override
                public void onResponse(Call call, Response response) throws IOException {
                    if (response.isSuccessful() && response.body() != null) {
                        String responseData = response.body().string();
                        try {
                            JSONObject jsonObject = new JSONObject(responseData);
                            String label = jsonObject.getString("label");
                            double probability = jsonObject.getDouble("probability");
                            int percent = (int) (probability * 100);

                            // ✨ 결과에 따른 맞춤형 문구 및 색상 로직
                            final String resultMsg;
                            final int color;

                            if ("AI Generated".equals(label)) {
                                resultMsg = "판독 완료: AI 생성 확률 " + percent + "% 입니다.";
                                 // color = Color.parseColor("#E91E63"); // 경고용 분홍/빨강
                            } else if ("Real Image".equals(label)) {
                                resultMsg = "판독 완료: AI 생성 확률 " + percent + "% 입니다.";
                                 // color = Color.parseColor("#4CAF50"); // 안전용 초록색
                            } else {
                                resultMsg = "💡 판독 완료: [" + label + "] 확률 " + percent + "%";
                                color = Color.BLACK;
                            }

                            new Handler(Looper.getMainLooper()).post(() -> {
                                progressBar.setVisibility(View.GONE);
                                tvStatus.setText(resultMsg);
                                // tvStatus.setTextColor(color);
                            });

                        } catch (Exception e) {
                            new Handler(Looper.getMainLooper()).post(() -> {
                                progressBar.setVisibility(View.GONE);
                                tvStatus.setText("⚠️ 응답 데이터 분석 오류가 발생했습니다.");
                            });
                        }
                    } else {
                        new Handler(Looper.getMainLooper()).post(() -> {
                            progressBar.setVisibility(View.GONE);
                            tvStatus.setText("⚠️ 서버 에러 (코드: " + response.code() + ")");
                        });
                    }
                }
            });
        });

        btnReset.setOnClickListener(v -> {
            tvStatus.setText("AI가 이미지를 생성했는지 판독해요.");
            tvStatus.setTextColor(Color.BLACK);
            progressBar.setVisibility(View.GONE);
            imageViewUploaded.setImageURI(null);
            imageViewUploaded.setVisibility(View.GONE);
            tvImageHint.setVisibility(View.VISIBLE);
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