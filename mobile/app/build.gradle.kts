plugins {
    id("com.android.application")
}

android {
    namespace = "com.example.ai_detection"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.example.ai_detection"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }
}

dependencies {

    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")

    // ✨ 구글 ML Kit: 한국어 텍스트 인식 인공지능 탑재!
    implementation("com.google.mlkit:text-recognition-korean:16.0.0")

    // ✨ Google ML Kit: 온디바이스 텍스트 인식 (OCR)
    implementation("com.google.android.gms:play-services-mlkit-text-recognition:19.0.0")

    // ✨ Google ML Kit: 온디바이스 이미지 라벨링 (판독)
    implementation("com.google.android.gms:play-services-mlkit-image-labeling:16.0.8")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}