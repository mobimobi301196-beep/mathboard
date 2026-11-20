import java.net.URI

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val serverUrl = (project.findProperty("serverUrl") as String).trim().trimEnd('/')

android {
    namespace = "ua.mathboard.app"
    compileSdk = 34
    defaultConfig {
        applicationId = "ua.mathboard.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
        buildConfigField("String", "SERVER_URL", "\"$serverUrl\"")
        manifestPlaceholders["serverHost"] = URI(serverUrl).host
    }
    buildFeatures { buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
}
