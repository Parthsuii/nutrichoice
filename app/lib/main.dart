import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:hive_flutter/hive_flutter.dart';
// Make sure this points to your Dashboard file
import 'onboarding_screen.dart';
void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 1. Start Local Database (Fast & Free)
  await Hive.initFlutter();
  await Hive.openBox('settings');
  await Hive.openBox('meals');
  await Hive.openBox('roster'); 
  // (You can open more boxes as needed)

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
    return MaterialApp(
      title: 'BioSync OS',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        primaryColor: Colors.teal,
        scaffoldBackgroundColor: Colors.black,
      ),
      home: const OnboardingScreen(),
    );
  }
}