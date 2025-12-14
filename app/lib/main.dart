import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:hive/hive.dart';

import 'onboarding_screen.dart';
import 'dashboard.dart'; 

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 1. Start Local Database
  await Hive.initFlutter();
  
  // Open the settings box
  var box = await Hive.openBox('settings');

  // --- 🛠️ TEMPORARY FIX: UNCOMMENT THIS LINE, RUN APP ONCE, THEN DELETE IT ---
        await box.put('onboarding_complete', true); 
  // --------------------------------------------------------------------------
  
  // 2. Start Firebase
  try {
    await Firebase.initializeApp();
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
    final settingsBox = Hive.box('settings');
    // Reads the flag. If it was saved as true (by the fix above), it returns true.
    final bool onboardingComplete = settingsBox.get('onboarding_complete', defaultValue: false);

    return MaterialApp(
      title: 'BioSync OS',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        primaryColor: Colors.teal,
        scaffoldBackgroundColor: Colors.black,
      ),
      home: onboardingComplete 
          ? const DashboardScreen() 
          : const OnboardingScreen(),
    );
  }
}