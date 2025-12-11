import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class BioCheckinScreen extends StatefulWidget {
  const BioCheckinScreen({super.key});

  @override
  State<BioCheckinScreen> createState() => _BioCheckinScreenState();
}

class _BioCheckinScreenState extends State<BioCheckinScreen> {
  // Inputs
  double _sleepHours = 7.0;
  int _moodRating = 5; // 1-10
  
  // Reflex Game State
  String _gameState = "IDLE"; // IDLE, WAITING, READY, FINISHED
  int _reflexScore = 0;
  DateTime? _startTime;
  Timer? _timer;
  Color _gameColor = Colors.grey.shade800;
  String _gameMessage = "Tap to Start Reflex Test";

  @override
  void initState() {
    super.initState();
    _loadPreviousData();
  }

  Future<void> _loadPreviousData() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _sleepHours = prefs.getDouble('last_sleep_hours') ?? 7.0;
      _reflexScore = prefs.getInt('last_reflex_score') ?? 0;
    });
  }

  // --- REFLEX GAME LOGIC ---
  void _startGame() {
    setState(() {
      _gameState = "WAITING";
      _gameColor = Colors.red.shade900;
      _gameMessage = "Wait for GREEN...";
    });

    // Random delay between 2-5 seconds
    int delay = Random().nextInt(3000) + 2000;
    _timer = Timer(Duration(milliseconds: delay), () {
      if (!mounted) return;
      setState(() {
        _gameState = "READY";
        _gameColor = Colors.green.shade600;
        _gameMessage = "TAP NOW!";
        _startTime = DateTime.now();
      });
    });
  }

  void _handleGameTap() {
    if (_gameState == "WAITING") {
      // Too early!
      _timer?.cancel();
      setState(() {
        _gameState = "IDLE";
        _gameColor = Colors.orange.shade900;
        _gameMessage = "Too early! Tap to retry.";
      });
    } else if (_gameState == "READY") {
      // Valid tap
      final endTime = DateTime.now();
      final diff = endTime.difference(_startTime!).inMilliseconds;
      setState(() {
        _reflexScore = diff;
        _gameState = "FINISHED";
        _gameColor = Colors.blue.shade900;
        _gameMessage = "${diff}ms\n(Tap to retry)";
      });
    } else {
      // Restart
      _startGame();
    }
  }

  // --- SAVE DATA ---
  Future<void> _saveAndContinue() async {
    final prefs = await SharedPreferences.getInstance();
    
    await prefs.setDouble('last_sleep_hours', _sleepHours);
    await prefs.setInt('last_reflex_score', _reflexScore);
    await prefs.setInt('last_mood_rating', _moodRating);

    // Calculate detected context roughly for user feedback
    String detected = "Standard Day";
    if (_sleepHours < 6.0 || (_reflexScore > 400 && _reflexScore > 0)) {
      detected = "Rest / Recovery";
    } else if (_reflexScore < 250 && _reflexScore > 0) {
      detected = "Prime Performance";
    }

    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text("Bio-Data Synced! Detected: $detected"),
        backgroundColor: Colors.green,
      ),
    );

    // Typically navigate to Meal Planner here
    // Navigator.pushReplacement(context, MaterialPageRoute(...));
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
                    value:_sleepHours.clamp(3.0,12.0),
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
              child: Container(
                height: 200,
                width: double.infinity,
                decoration: BoxDecoration(
                  color: _gameColor,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: Colors.white24, width: 1),
                  boxShadow: [
                    if (_gameState == "READY")
                      BoxShadow(color: Colors.green.withOpacity(0.5), blurRadius: 20, spreadRadius: 5)
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
                  child: Container(
                    padding: const EdgeInsets.all(15),
                    decoration: BoxDecoration(
                      color: isSelected ? Colors.deepPurple : Colors.grey.shade900,
                      shape: BoxShape.circle,
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
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}