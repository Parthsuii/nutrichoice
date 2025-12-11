import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class BodyMapScreen extends StatefulWidget {
  const BodyMapScreen({super.key});

  @override
  State<BodyMapScreen> createState() => _BodyMapScreenState();
}

class _BodyMapScreenState extends State<BodyMapScreen> {
  // Muscle Groups available for selection
  final List<String> _muscles = [
    "Shoulders", "Chest", "Back",
    "Biceps", "Triceps", "Core",
    "Quads", "Hamstrings", "Calves"
  ];

  // Track which muscles are currently sore
  List<String> _soreMuscles = [];

  @override
  void initState() {
    super.initState();
    _loadSoreness();
  }

  // Load saved soreness state from disk
  Future<void> _loadSoreness() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _soreMuscles = prefs.getStringList('sore_muscles') ?? [];
    });
  }

  // Toggle soreness on/off and save immediately
  Future<void> _toggleMuscle(String muscle) async {
    setState(() {
      if (_soreMuscles.contains(muscle)) {
        _soreMuscles.remove(muscle); // Healed
      } else {
        _soreMuscles.add(muscle); // Sore
      }
    });

    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList('sore_muscles', _soreMuscles);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("Smart Soreness Map"),
        backgroundColor: Colors.red.shade900,
        centerTitle: true,
      ),
      body: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              "Where does it hurt?",
              style: TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold),
            ),
            const Text(
              "Tap to mark soreness. The Chef will adapt.",
              style: TextStyle(color: Colors.grey, fontSize: 14),
            ),
            const SizedBox(height: 20),

            // VISUAL MUSCLE GRID
            Expanded(
              child: GridView.builder(
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 3,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                  childAspectRatio: 1.0,
                ),
                itemCount: _muscles.length,
                itemBuilder: (context, index) {
                  final muscle = _muscles[index];
                  final isSore = _soreMuscles.contains(muscle);

                  return GestureDetector(
                    onTap: () => _toggleMuscle(muscle),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 300),
                      decoration: BoxDecoration(
                        // Sore = Red, Normal = Grey
                        color: isSore ? Colors.red.shade900 : Colors.grey.shade900,
                        borderRadius: BorderRadius.circular(15),
                        border: Border.all(
                          color: isSore ? Colors.redAccent : Colors.transparent,
                          width: 2,
                        ),
                        boxShadow: [
                          if (isSore)
                            BoxShadow(color: Colors.red.withOpacity(0.4), blurRadius: 12)
                        ],
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            isSore ? Icons.healing : Icons.fitness_center,
                            color: isSore ? Colors.white : Colors.white24,
                            size: 32,
                          ),
                          const SizedBox(height: 8),
                          Text(
                            muscle,
                            style: TextStyle(
                              color: isSore ? Colors.white : Colors.white54,
                              fontWeight: FontWeight.bold,
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),

            // STATUS FOOTER
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.grey.shade900,
                borderRadius: BorderRadius.circular(15),
                border: Border.all(color: Colors.white10),
              ),
              child: Row(
                children: [
                  const Icon(Icons.info_outline, color: Colors.blueAccent),
                  const SizedBox(width: 15),
                  Expanded(
                    child: Text(
                      _soreMuscles.isEmpty
                          ? "Status: Fully Recovered."
                          : "Detected: ${_soreMuscles.join(', ')} soreness.\nDiet adapted for inflammation.",
                      style: const TextStyle(color: Colors.white70, fontSize: 13),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}