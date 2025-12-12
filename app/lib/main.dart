import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:hive/hive.dart'; // Explicitly importing Hive
// Make sure this points to your Dashboard file

// Assuming you have these files:
import 'onboarding_screen.dart';
import 'dashboard.dart'; // <--- NEW: Assuming you have a Dashboard screen

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 1. Start Local Database (Fast & Free)
  await Hive.initFlutter();
  
  // NOTE: Only open the 'settings' box now, as it's critical for the ternary check.
  // Other boxes (meals, roster) will be opened lazily when their screens load.
  await Hive.openBox('settings');
  
  // 2. Start Firebase (Analytics & Crash Tracking)
  try {
    await Firebase.initializeApp();
    // Pass all uncaught "fatal" errors from the framework to Crashlytics
    FlutterError.onError = FirebaseCrashlytics.instance.recordFlutterError;
  } catch (e) {
    print("⚠️ Firebase Warning: $e");
  }

  runApp(const BioSyncApp());
}

class BioSyncApp extends StatelessWidget {
  const BioSyncApp({super.key});

  @override
  Widget build(BuildContext context) {
    // Check the Hive box for the onboarding status
    final settingsBox = Hive.box('settings');
    final bool onboardingComplete = settingsBox.get('onboarding_complete', defaultValue: false);

    return MaterialApp(
      title: 'BioSync OS',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        primaryColor: Colors.teal,
        scaffoldBackgroundColor: Colors.black,
      ),
      
      // --- TERNARY CONDITION FOR INITIAL SCREEN ---
      home: onboardingComplete 
          ? const DashboardScreen() // Go straight to Dashboard if complete
          : const OnboardingScreen(), // Show Onboarding if first launch
    );
  }
}

// NOTE: You must now update your OnboardingScreen to save 'onboarding_complete': true
// For example, in the OnboardingScreen's final step:
/*
  void completeOnboarding() {
    final settingsBox = Hive.box('settings');
    settingsBox.put('onboarding_complete', true);
    // Navigate to DashboardScreen
  }
*/