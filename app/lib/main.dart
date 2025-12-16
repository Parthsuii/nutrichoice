import 'dart:async'; // Required for Zone Guarding
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'onboarding_screen.dart';
import 'dashboard.dart';

void main() async {
  // 1. Zone Guard: Catch errors that happen outside Flutter's widget tree (Async/Isolate)
  runZonedGuarded<Future<void>>(() async {
    WidgetsFlutterBinding.ensureInitialized();

    // 2. Start Local Database (Hive)
    await Hive.initFlutter();
    var box = await Hive.openBox('settings');

    // 3. CRITICAL FIX: Robust Null Handling
    // This handles cases where the value might be saved as 'null' in the database.
    // We cast to 'bool?' first, then use '?? false' to guarantee a boolean result.
    bool onboardingComplete = (box.get('onboarding_complete') as bool?) ?? false;

    // 4. Start Firebase with Robust Error Handling
    try {
      await Firebase.initializeApp();
      
      // Pass all uncaught Flutter framework errors to Crashlytics
      FlutterError.onError = FirebaseCrashlytics.instance.recordFlutterError;
    } catch (e, stack) {
      // If Firebase fails, log it locally so you know during dev, but don't crash the app
      debugPrint("⚠️ Firebase Init Failed: $e\n$stack");
    }

    runApp(BioSyncApp(startOnDashboard: onboardingComplete));

  }, (error, stack) {
    // 5. Catch Async Errors (The "Safety Net")
    // This catches errors like failed network calls or background crashes
    FirebaseCrashlytics.instance.recordError(error, stack, fatal: true);
  });
}

class BioSyncApp extends StatelessWidget {
  final bool startOnDashboard; // Injected Dependency

  const BioSyncApp({super.key, required this.startOnDashboard});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BioSync OS',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        primaryColor: Colors.teal,
        scaffoldBackgroundColor: Colors.black,
        // Visual Polish: improved color scheme definition
        colorScheme: const ColorScheme.dark(
          primary: Colors.teal,
          secondary: Colors.deepOrange,
          surface: Color(0xFF121212),
        ),
      ),
      // Logic is now clean and determined before the UI even draws
      home: startOnDashboard 
          ? const DashboardScreen() 
          : const OnboardingScreen(),
    );
  }
}