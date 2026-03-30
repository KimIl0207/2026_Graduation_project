package com.example.ai_detection;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.PorterDuff;
import android.graphics.PorterDuffXfermode;
import android.graphics.Rect;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.LayoutInflater;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.MultipartBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

public class FloatingService extends Service {

    private WindowManager windowManager;
    private View floatingView;
    private final OkHttpClient client = new OkHttpClient();

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        floatingView = LayoutInflater.from(this).inflate(R.layout.layout_floating_widget, null);

        int layoutFlag = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) ?
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY : WindowManager.LayoutParams.TYPE_PHONE;

        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
                layoutFlag, WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE, PixelFormat.TRANSLUCENT);

        params.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
        params.x = 0; params.y = 150;
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        windowManager.addView(floatingView, params);

        floatingView.findViewById(R.id.btnCaptureText).setOnClickListener(v -> startCaptureFlow("TEXT"));
        floatingView.findViewById(R.id.btnCaptureImage).setOnClickListener(v -> startCaptureFlow("IMAGE"));
        floatingView.findViewById(R.id.btnClose).setOnClickListener(v -> stopSelf());

        floatingView.findViewById(R.id.dragHandle).setOnTouchListener(new View.OnTouchListener() {
            private int initialX, initialY; private float initialTouchX, initialTouchY;
            @Override
            public boolean onTouch(View v, MotionEvent event) {
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        initialX = params.x; initialY = params.y;
                        initialTouchX = event.getRawX(); initialTouchY = event.getRawY();
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        params.x = initialX + (int) (event.getRawX() - initialTouchX);
                        params.y = initialY - (int) (event.getRawY() - initialTouchY);
                        windowManager.updateViewLayout(floatingView, params);
                        return true;
                }
                return false;
            }
        });
    }

    private void startCaptureFlow(String type) {
        Intent captureIntent = new Intent(this, CaptureActivity.class);
        captureIntent.putExtra("captureType", type);
        captureIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(captureIntent);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "ACTION_START_CAPTURE".equals(intent.getAction())) {
            int resultCode = intent.getIntExtra("resultCode", Activity.RESULT_CANCELED);
            Intent data = intent.getParcelableExtra("data");
            String captureType = intent.getStringExtra("captureType");
            if (resultCode == Activity.RESULT_OK && data != null) showCropOverlay(resultCode, data, captureType);
        }
        return START_NOT_STICKY;
    }

    private void showCropOverlay(int resultCode, Intent data, String captureType) {
        floatingView.setVisibility(View.GONE);
        View cropOverlay = new View(this) {
            Paint pDim = new Paint(); Paint pClear = new Paint(); Paint pBorder = new Paint();
            float sX, sY, eX, eY; boolean drawing = false;
            {
                pDim.setColor(Color.parseColor("#66000000"));
                pClear.setXfermode(new PorterDuffXfermode(PorterDuff.Mode.CLEAR));
                pBorder.setColor(Color.parseColor("#6A65FF")); pBorder.setStyle(Paint.Style.STROKE); pBorder.setStrokeWidth(8f);
                setLayerType(LAYER_TYPE_HARDWARE, null);
            }
            @Override
            public boolean onTouchEvent(MotionEvent event) {
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN: sX = event.getRawX(); sY = event.getRawY(); drawing = true; return true;
                    case MotionEvent.ACTION_MOVE: eX = event.getRawX(); eY = event.getRawY(); invalidate(); return true;
                    case MotionEvent.ACTION_UP:
                        drawing = false; Rect r = new Rect((int)Math.min(sX, eX), (int)Math.min(sY, eY), (int)Math.max(sX, eX), (int)Math.max(sY, eY));
                        windowManager.removeView(this);
                        if (r.width() > 50) new Handler(Looper.getMainLooper()).postDelayed(() -> startForegroundCapture(resultCode, data, captureType, r), 300);
                        else floatingView.setVisibility(View.VISIBLE);
                        return true;
                } return false;
            }
            @Override
            protected void onDraw(Canvas c) {
                super.onDraw(c); c.drawRect(0, 0, getWidth(), getHeight(), pDim);
                if (drawing) {
                    c.drawRect(Math.min(sX, eX), Math.min(sY, eY), Math.max(sX, eX), Math.max(sY, eY), pClear);
                    c.drawRect(Math.min(sX, eX), Math.min(sY, eY), Math.max(sX, eX), Math.max(sY, eY), pBorder);
                }
            }
        };
        int layoutFlag = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY : WindowManager.LayoutParams.TYPE_PHONE;
        WindowManager.LayoutParams p = new WindowManager.LayoutParams(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT, layoutFlag, WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN, PixelFormat.TRANSLUCENT);
        windowManager.addView(cropOverlay, p);
    }

    private void startForegroundCapture(int resultCode, Intent data, String captureType, Rect cropRect) {
        String CHANNEL_ID = "capture_channel";
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(CHANNEL_ID, "분석", NotificationManager.IMPORTANCE_LOW);
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
        Notification notification = null;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            notification = new Notification.Builder(this, CHANNEL_ID).setContentTitle("AI 판독기").setContentText("분석 중...").setSmallIcon(android.R.drawable.ic_menu_camera).build();
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
        } else {
            startForeground(1, notification);
        }

        MediaProjection mp = ((MediaProjectionManager)getSystemService(Context.MEDIA_PROJECTION_SERVICE)).getMediaProjection(resultCode, data);
        mp.registerCallback(new MediaProjection.Callback() {}, new Handler(Looper.getMainLooper()));
        DisplayMetrics dm = getResources().getDisplayMetrics();
        ImageReader ir = ImageReader.newInstance(dm.widthPixels, dm.heightPixels, PixelFormat.RGBA_8888, 2);
        VirtualDisplay vd = mp.createVirtualDisplay("Capture", dm.widthPixels, dm.heightPixels, dm.densityDpi, 0, ir.getSurface(), null, null);

        ir.setOnImageAvailableListener(reader -> {
            Image img = reader.acquireLatestImage();
            if (img != null) {
                ByteBuffer buf = img.getPlanes()[0].getBuffer();
                int rs = img.getPlanes()[0].getRowStride(), ps = img.getPlanes()[0].getPixelStride();
                Bitmap b = Bitmap.createBitmap(rs/ps, dm.heightPixels, Bitmap.Config.ARGB_8888);
                b.copyPixelsFromBuffer(buf);
                int cLeft = Math.max(0, cropRect.left);
                int cTop = Math.max(0, cropRect.top);
                int cWidth = Math.min(b.getWidth() - cLeft, cropRect.width());
                int cHeight = Math.min(b.getHeight() - cTop, cropRect.height());
                Bitmap cropped = Bitmap.createBitmap(b, cLeft, cTop, cWidth, cHeight);
                vd.release(); mp.stop(); ir.setOnImageAvailableListener(null, null);

                if ("TEXT".equals(captureType)) {
                    analyzeText(cropped);
                } else {
                    sendImageToServer(cropped);
                }
                img.close();
            }
        }, new Handler(Looper.getMainLooper()));
    }

    private void analyzeText(Bitmap b) {
        TextRecognition.getClient(new KoreanTextRecognizerOptions.Builder().build()).process(InputImage.fromBitmap(b, 0))
                .addOnSuccessListener(t -> {
                    showResultWindow("📝 추출된 텍스트", t.getText().isEmpty() ? "텍스트가 없습니다." : t.getText(), true, "95%", null);
                });
    }

    private void sendImageToServer(Bitmap bitmap) {
        Handler mainHandler = new Handler(Looper.getMainLooper());
        mainHandler.post(() -> Toast.makeText(FloatingService.this, "AI 분석을 요청합니다...", Toast.LENGTH_SHORT).show());

        ByteArrayOutputStream stream = new ByteArrayOutputStream();
        bitmap.compress(Bitmap.CompressFormat.JPEG, 100, stream);
        byte[] byteArray = stream.toByteArray();

        RequestBody requestBody = new MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("file", "capture.jpg",
                        RequestBody.create(byteArray, MediaType.parse("image/jpeg")))
                .build();

        Request request = new Request.Builder()
                .url("https://abc8-119-207-138-153.ngrok-free.app/predict")
                .post(requestBody)
                .build();

        client.newCall(request).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                e.printStackTrace();
                mainHandler.post(() -> showResultWindow("🖼️ 판독 실패", "서버 연결 오류:\n" + e.getMessage(), true, "에러", bitmap));
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                if (response.isSuccessful() && response.body() != null) {
                    String responseData = response.body().string();
                    try {
                        // ✨ [JSON 파싱 시작] 서버 응답에서 필요한 데이터만 쏙쏙!
                        JSONObject jsonObject = new JSONObject(responseData);
                        String label = jsonObject.getString("label"); // "Real Image" 등
                        double probability = jsonObject.getDouble("probability"); // 0.2822

                        int percent = (int) (probability * 100);
                        String resultMessage = "분석 결과: [" + label + "] 로 판독되었습니다.";
                        String probText = percent + "%";

                        mainHandler.post(() -> showResultWindow("🖼️ 판독 완료", resultMessage, true, probText, bitmap));
                    } catch (Exception e) {
                        e.printStackTrace();
                        mainHandler.post(() -> showResultWindow("🖼️ 판독 완료", "응답 데이터 분석 오류", true, "에러", bitmap));
                    }
                } else {
                    mainHandler.post(() -> showResultWindow("🖼️ 서버 에러", "코드: " + response.code(), true, "에러", bitmap));
                }
            }
        });
    }

    private void showResultWindow(String title, String content, boolean showProb, String probValue, Bitmap capturedBitmap) {
        new Handler(Looper.getMainLooper()).post(() -> {
            if (floatingView != null) floatingView.setVisibility(View.VISIBLE);
            View rv = LayoutInflater.from(this).inflate(R.layout.layout_floating_result, null);

            ((TextView)rv.findViewById(R.id.tvResultTitle)).setText(title);
            ((TextView)rv.findViewById(R.id.tvResultContent)).setText(content);

            ImageView ivCaptured = rv.findViewById(R.id.ivCapturedImage);
            LinearLayout probLayout = rv.findViewById(R.id.layoutAiProbability);
            TextView probTv = rv.findViewById(R.id.tvAiProbability);

            if (capturedBitmap != null) {
                ivCaptured.setImageBitmap(capturedBitmap);
                ivCaptured.setVisibility(View.VISIBLE);
            } else {
                ivCaptured.setVisibility(View.GONE);
            }

            if (showProb) {
                probLayout.setVisibility(View.VISIBLE);
                probTv.setText("AI가 생성했을 확률: " + probValue);
            } else {
                probLayout.setVisibility(View.GONE);
            }

            int layoutFlag = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) ?
                    WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY : WindowManager.LayoutParams.TYPE_PHONE;
            int widthInPx = (int) (360 * getResources().getDisplayMetrics().density);
            WindowManager.LayoutParams p = new WindowManager.LayoutParams(widthInPx, WindowManager.LayoutParams.WRAP_CONTENT, layoutFlag, WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE, PixelFormat.TRANSLUCENT);
            p.gravity = Gravity.CENTER;
            windowManager.addView(rv, p);
            rv.findViewById(R.id.btnCloseResult).setOnClickListener(v -> windowManager.removeView(rv));
        });
    }

    @Override
    public void onDestroy() { super.onDestroy(); if (floatingView != null) windowManager.removeView(floatingView); }
}