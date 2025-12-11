// In android/app/build.gradle.kts

// 1. ADD CRITICAL IMPORTS FOR PROPERTY LOADING
import java.util.Properties

// 1. PLUGINS BLOCK (The ONLY place plugins should be applied)
plugins {
    id("com.android.application")
    id("kotlin-android")
    id("dev.flutter.flutter-gradle-plugin")
    id("com.google.gms.google-services") 
}

// 2. KOTLIN DSL WAY TO LOAD PROPERTIES (FIXED IMPORTS)
val keyProperties = Properties().apply {
    val keyPropertiesFile = rootProject.file("key.properties")
    if (keyPropertiesFile.exists()) {
        keyPropertiesFile.inputStream().use { load(it) }
    }
}

android {
    namespace = "com.example.app"
    
    compileSdk = 36 
    ndkVersion = "27.0.12077973"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // 3. SIGNING CONFIGS (SIMPLIFIED CASTING)
    signingConfigs {
        create("release") {
        val storeFilePath = keyProperties["storeFile"] as String? ?: throw GradleException("Missing 'storeFile' in key.properties.")
        val storePass = keyProperties["storePassword"] as String? ?: throw GradleException("Missing 'storePassword' in key.properties.")
        val keyAliasValue = keyProperties["keyAlias"] as String? ?: throw GradleException("Missing 'keyAlias' in key.properties.")
        val keyPass = keyProperties["keyPassword"] as String? ?: throw GradleException("Missing 'keyPassword' in key.properties.")

        storeFile = file(storeFilePath)
        storePassword = storePass
        keyAlias = keyAliasValue
        keyPassword = keyPass
        }
    }

    defaultConfig {
        applicationId = "com.example.app" 
        minSdk = flutter.minSdkVersion 
        targetSdk = 36 
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release") 
            isMinifyEnabled = true
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

flutter {
    source = "../.."
}
