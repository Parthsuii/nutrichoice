# Keep androidx.window classes
-keep class androidx.window.extensions.** { *; }
-keep class androidx.window.sidecar.** { *; }

# Keep Google Play Core classes
-keep class com.google.android.play.core.** { *; }

# Keep Google ML Kit classes
-keep class com.google.mlkit.vision.text.** { *; }

# Keep Flutter classes
-keep class io.flutter.** { *; }

# Keep your app classes
-keep class com.example.app.** { *; }

# Don't warn about missing classes
-dontwarn androidx.window.**
-dontwarn com.google.android.play.core.**
-dontwarn com.google.mlkit.vision.text.chinese.**
-dontwarn com.google.mlkit.vision.text.devanagari.**
-dontwarn com.google.mlkit.vision.text.japanese.**
-dontwarn com.google.mlkit.vision.text.korean.**
-dontwarn io.flutter.embedding.engine.deferredcomponents.PlayStoreDeferredComponentManager