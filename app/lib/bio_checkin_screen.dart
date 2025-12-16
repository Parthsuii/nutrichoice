import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

// --- 1. ENUM FOR TYPE SAFETY (Fixing "String State" Risk) ---
enum GameState { idle, waiting, ready, finished }

// --- 2. CONSTANTS (Fixing "Magic Strings") ---
class BioKeys {
  static const String sleepHours = 'last_sleep_hours';
  static const String reflexScore = 'last_reflex_score';
  static const String moodRating = 'last_mood_rating';
}

class BioCheckinScreen extends StatefulWidget {
  const BioCheckinScreen({super.key});

  @override
  State<BioCheckinScreen> createState() => _BioCheckinScreenState();
}

class _BioCheckinScreenState extends State<BioCheckinScreen> {
  // Inputs
  double _sleepHours = 7.0;
  int _moodRating = 5; // 2, 4, 6, 8, 10

  // Reflex Game State
  GameState _gameState = GameState.idle;
  int _reflexScore = 0;
  DateTime? _startTime;
  Timer? _timer;
  
  // UI State Helpers
  Color _gameColor = Colors.grey.shade800;
  String _gameMessage = "Tap to Start Reflex Test";

  @override
  void initState() {
    super.initState();
    _loadPreviousData();
  }

  // --- 3. MEMORY LEAK FIX (Crucial) ---
  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _loadPreviousData() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _sleepHours = prefs.getDouble(BioKeys.sleepHours) ?? 7.0;
      _reflexScore = prefs.getInt(BioKeys.reflexScore) ?? 0;
      // Clamp sleep to slider range to avoid errors
      if (_sleepHours < 3.0) _sleepHours = 3.0;
      if (_sleepHours > 12.0) _sleepHours = 12.0;
    });
  }

  // --- REFLEX GAME LOGIC (Refactored for Clarity) ---
  void _startGame() {
    _timer?.cancel(); // Safety cleanup
    
    setState(() {
      _gameState = GameState.waiting;
      _gameColor = Colors.red.shade900;
      _gameMessage = "Wait for GREEN...";
      _reflexScore = 0; // Reset score on new game
    });

    // Random delay between 2-5 seconds
    int delay = Random().nextInt(3000) + 2000;
    
    _timer = Timer(Duration(milliseconds: delay), () {
      if (!mounted) return;
      setState(() {
        _gameState = GameState.ready;
        _gameColor = Colors.green.shade600;
        _gameMessage = "TAP NOW!";
        _startTime = DateTime.now();
      });
    });
  }

  void _handleGameTap() {
    switch (_gameState) {
      case GameState.idle:
      case GameState.finished:
        _startGame(); // Explicit Start/Restart
        break;

      case GameState.waiting:
        // Too early!
        _timer?.cancel();
        setState(() {
          _gameState = GameState.idle;
          _gameColor = Colors.orange.shade900;
          _gameMessage = "Too early! Tap to retry.";
          _reflexScore = 0; // Invalid run
        });
        break;

      case GameState.ready:
        // Valid tap
        final endTime = DateTime.now();
        final diff = endTime.difference(_startTime!).inMilliseconds;
        setState(() {
          _reflexScore = diff;
          _gameState = GameState.finished;
          _gameColor = Colors.blue.shade900;
          _gameMessage = "${diff}ms\n(Tap to retry)";
        });
        break;
    }
  }

  // --- SAVE DATA & LOGIC ---
  Future<void> _saveAndContinue() async {
    final prefs = await SharedPreferences.getInstance();
    
    await prefs.setDouble(BioKeys.sleepHours, _sleepHours);
    await prefs.setInt(BioKeys.reflexScore, _reflexScore);
    await prefs.setInt(BioKeys.moodRating, _moodRating);

    // Domain Logic: Context Detection
    String detected = "Standard Day";
    bool isTired = _sleepHours < 6.0 || (_reflexScore > 400 && _reflexScore > 0);
    bool isPrime = _reflexScore < 250 && _reflexScore > 0;

    if (isTired) {
      detected = "Rest / Recovery";
    } else if (isPrime) {
      detected = "Prime Performance";
    }

    if (!mounted) return;
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text("Bio-Data Synced! Detected: $detected"),
        backgroundColor: isPrime ? Colors.teal : (isTired ? Colors.orange : Colors.green),
        behavior: SnackBarBehavior.floating,
      ),
    );

    // Optional: Navigate to next screen
    // Navigator.pop(context); 
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("Daily Bio-Checkin"),
        backgroundColor: Colors.grey.shade900,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 1. SLEEP INPUT
            const Text("😴 Last Night's Sleep", style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            Row(
              children: [
                Text("${_sleepHours.toStringAsFixed(1)} hrs", style: const TextStyle(color: Colors.tealAccent, fontSize: 24, fontWeight: FontWeight.bold)),
                Expanded(
                  child: Slider(
                    value: _sleepHours,
                    min: 3.0,
                    max: 12.0,
                    divisions: 18,
                    activeColor: Colors.tealAccent,
                    onChanged: (val) => setState(() => _sleepHours = val),
                  ),
                ),
              ],
            ),
            
            const SizedBox(height: 30),

            // 2. REFLEX GAME
            const Text("⚡ CNS Fatigue Test", style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 5),
            const Text("Test your reaction time to gauge recovery.", style: TextStyle(color: Colors.grey)),
            const SizedBox(height: 15),
            
            GestureDetector(
              onTap: _handleGameTap,
              child: AnimatedContainer( // Added Animation for polish
                duration: const Duration(milliseconds: 300),
                height: 200,
                width: double.infinity,
                decoration: BoxDecoration(
                  color: _gameColor,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: Colors.white24, width: 1),
                  boxShadow: [
                    if (_gameState == GameState.ready)
                      BoxShadow(color: Colors.green.withOpacity(0.6), blurRadius: 25, spreadRadius: 2)
                  ]
                ),
                alignment: Alignment.center,
                child: Text(
                  _gameMessage,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold),
                ),
              ),
            ),

            const SizedBox(height: 30),

            // 3. MOOD INPUT
            const Text("🧠 Mental State", style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 15),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: List.generate(5, (index) {
                int rating = (index + 1) * 2; // 2, 4, 6, 8, 10
                bool isSelected = _moodRating == rating;
                return GestureDetector(
                  onTap: () => setState(() => _moodRating = rating),
                  child: AnimatedContainer( // Polish
                    duration: const Duration(milliseconds: 200),
                    padding: const EdgeInsets.all(15),
                    decoration: BoxDecoration(
                      color: isSelected ? Colors.deepPurple : Colors.grey.shade900,
                      shape: BoxShape.circle,
                      border: isSelected ? Border.all(color: Colors.white54, width: 2) : null,
                    ),
                    child: Text(
                      rating.toString(),
                      style: TextStyle(
                        color: Colors.white, 
                        fontWeight: isSelected ? FontWeight.bold : FontWeight.normal
                      ),
                    ),
                  ),
                );
              }),
            ),
            const Center(child: Padding(
              padding: EdgeInsets.only(top: 8.0),
              child: Text("1 = Drained   •   10 = Ready to Go", style: TextStyle(color: Colors.grey)),
            )),

            const SizedBox(height: 40),

            // 4. SUBMIT BUTTON
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: _saveAndContinue,
                icon: const Icon(Icons.check_circle),
                label: const Text("Sync & Open Planner"),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.teal,
                  foregroundColor: Colors.black,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  textStyle: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}