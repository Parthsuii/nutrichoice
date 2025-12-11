import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ReflexGame extends StatefulWidget {
  const ReflexGame({super.key});

  @override
  State<ReflexGame> createState() => _ReflexGameState();
}

class _ReflexGameState extends State<ReflexGame> {
  int gameState = 0; // 0=Idle, 1=Waiting, 2=Reaction, 3=Result, 4=Loading
  String message = "Tap to Start";
  String serverAdvice = "";
  Color screenColor = Colors.grey.shade900;

  Stopwatch stopwatch = Stopwatch();
  Timer? timer;
  int score = 0;

  // --- INPUT VARIABLES ---
  double moodRating = 5.0;

  Future<void> sendScoreToBackend(int reflexMs) async {
    setState(() {
      gameState = 4;
      message = "Triangulating Recovery...";
    });

    final prefs = await SharedPreferences.getInstance();
    double sleepHours = prefs.getDouble('last_sleep_hours') ?? 7.0;
    bool honestyBuffer = prefs.getBool('honesty_buffer') ?? false;

    try {
      final Map<String, dynamic> data = {
        "reflex_ms": reflexMs,
        "sleep_hours": sleepHours,
        "mood_rating": moodRating.round(),
        "did_watch_tv": honestyBuffer,
      };

      final response = await http
          .post(
            Uri.parse('https://nutrichoice-xvpf.onrender.com/calculate-score'),
            headers: {"Content-Type": "application/json"},
            body: jsonEncode(data),
          )
          .timeout(const Duration(seconds: 2));

      if (response.statusCode == 200) {
        final result = jsonDecode(response.body);
        _showResult(reflexMs, result['score'], result['advice']);
      } else {
        throw Exception("Server Error");
      }
    } catch (e) {
      // Local Fallback Calculation
      int localScore = 100 - (reflexMs ~/ 10);
      if (localScore < 0) localScore = 0; // Prevent negative scores

      String localAdvice = reflexMs < 250
          ? "⚡ CNS Primed. Ready to lift heavy."
          : "⚠️ CNS Slow. Consider active recovery.";

      _showResult(reflexMs, localScore, localAdvice);
    }
  }

  // --- THE UPDATE: Saving Score Locally ---
  Future<void> _showResult(int ms, int score, String advice) async {
    // 1. SAVE TO STORAGE (So Dashboard can read it)
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('last_reflex_score', score);
    await prefs.setString('last_reflex_advice', advice);

    setState(() {
      gameState = 3;
      serverAdvice = advice;
      message = "${ms}ms\n\nBioScore: $score\n\n$advice";

      if (score < 40) {
        screenColor = Colors.red.shade900;
      } else if (score < 70)
        screenColor = Colors.orange.shade800;
      else
        screenColor = Colors.green.shade800;
    });
  }

  void startGame() {
    setState(() {
      gameState = 1;
      message = "Wait for Green...";
      serverAdvice = "";
      screenColor = Colors.red.shade800;
    });
    int delay = Random().nextInt(3000) + 2000;
    timer = Timer(Duration(milliseconds: delay), showGreenLight);
  }

  void showGreenLight() {
    if (gameState == 1) {
      stopwatch.reset();
      stopwatch.start();
      setState(() {
        gameState = 2;
        message = "TAP NOW!";
        screenColor = Colors.green.shade600;
      });
    }
  }

  void handleTap() {
    if (gameState == 0 || gameState == 3) {
      startGame();
    } else if (gameState == 1) {
      timer?.cancel();
      setState(() {
        gameState = 3;
        message = "Too Early! Penalty.";
        screenColor = Colors.orange;
      });
    } else if (gameState == 2) {
      stopwatch.stop();
      score = stopwatch.elapsedMilliseconds;
      sendScoreToBackend(score);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: screenColor,
      body: Stack(
        children: [
          InkWell(
            onTap: handleTap,
            child: Center(
              child: gameState == 4
                  ? const CircularProgressIndicator(color: Colors.white)
                  : Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 20),
                      child: Text(
                        message,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          fontSize: 28,
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
            ),
          ),
          if (gameState == 0)
            Positioned(
              bottom: 50,
              left: 20,
              right: 20,
              child: Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: Colors.black54,
                  borderRadius: BorderRadius.circular(15),
                ),
                child: Column(
                  children: [
                    const Text(
                      "Morning Check-in",
                      style: TextStyle(color: Colors.white, fontSize: 18),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      "How do you feel? ${moodRating.round()}/10",
                      style: const TextStyle(color: Colors.tealAccent),
                    ),
                    Slider(
                      value: moodRating,
                      min: 0,
                      max: 10,
                      divisions: 10,
                      activeColor: Colors.teal,
                      onChanged: (val) => setState(() => moodRating = val),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
