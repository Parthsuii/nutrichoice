// In android/build.gradle.kts (Root Project)

// 1. FIREBASE CLASSPATH BLOCK (MUST BE AT THE TOP)
buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        // This is the CLASSPATH to DOWNLOAD the plugin.
        classpath("com.google.gms:google-services:4.4.2") 
        
        // Ensure you have the Android Gradle Plugin here (usually standard)
        // classpath("com.android.tools.build:gradle:8.1.0") // Example/Fallback AGP version
    }
}

// -------------------------------------------------------------------------
// REMOVED ALL AMBIGUOUS 'import org.gradle.api.tasks.compile.JavaCompile' LINES
// -------------------------------------------------------------------------

// 2. Your Original Configurations
allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

subprojects {
    plugins.withId("org.jetbrains.kotlin.android") {
        configure<org.jetbrains.kotlin.gradle.dsl.KotlinAndroidProjectExtension> {
            jvmToolchain(17)
        }
    }

    project.evaluationDependsOn(":app")
}

// 3. Build Directory Logic 
val newBuildDir: org.gradle.api.file.Directory = 
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: org.gradle.api.file.Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}