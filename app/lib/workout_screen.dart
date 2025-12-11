import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:intl/intl.dart'; 

class WorkoutScreen extends StatefulWidget {
  const WorkoutScreen({super.key});

  @override
  State<WorkoutScreen> createState() => _WorkoutScreenState();
}

class _WorkoutScreenState extends State<WorkoutScreen> {
  // Configuration
  double _timeAvailable = 45;
  String _intensity = "High (Performance)";
  String _userGoal = "Maintain"; 
  
  // Smart Suggestions
  String _suggestedTime = "Anytime";
  String _workoutType = "Strength";
  String _scheduleContext = ""; 

  // Data
  bool _isLoading = false;
  List<dynamic> _workoutPlan = [];
  String _aiAdvice = "Analyzing schedule & bio-data...";
  
  // Progress Tracking
  final Set<int> _completedIndices = {}; 

  @override
  void initState() {
    super.initState();
    _loadSmartData(); 
  }

  // --- 1. SMART ANALYSIS (Bio + Schedule) ---
  Future<void> _loadSmartData() async {
    final prefs = await SharedPreferences.getInstance();
    _userGoal = prefs.getString('user_goal') ?? "Maintain";
    
    // A. BIO-DATA CHECK
    int reflex = prefs.getInt('last_reflex_score') ?? 0;
    double sleep = prefs.getDouble('last_sleep_hours') ?? 7.0;
    List<String> soreMuscles = prefs.getStringList('sore_muscles') ?? [];

    // B. SCHEDULE CHECK (Safe Load)
    String todayName = DateFormat('EEEE').format(DateTime.now());
    String? scheduleJson = prefs.getString('weekly_schedule');
    List<dynamic> todayEvents = [];
    
    if (scheduleJson != null) {
      try {
        Map<String, dynamic> schedule = jsonDecode(scheduleJson);
        if (schedule[todayName] is List) {
          todayEvents = schedule[todayName];
        }
      } catch (e) {
        print("Schedule Load Error: $e");
      }
    }

    // C. LOGIC ENGINE
    if (!mounted) return;
    setState(() {
      bool isFatigued = (reflex > 350 && reflex > 0) || sleep < 5.5;
      bool isCardioDay = (todayName == "Wednesday" || todayName == "Saturday") || isFatigued;

      if (isFatigued) {
        _intensity = "Low (Recovery)";
        _workoutType = "Active Recovery / Yoga";
        _timeAvailable = 30;
      } else if (isCardioDay) {
        _intensity = "Medium (Endurance)";
        _workoutType = "Cardio / HIIT";
        _timeAvailable = 45;
      } else {
        _intensity = "High (Performance)";
        _workoutType = "Strength / Hypertrophy";
        _timeAvailable = 60;
      }

      if (todayEvents.isEmpty) {
        _suggestedTime = "Free Day! Go anytime.";
        _scheduleContext = "No events found.";
      } else {
        if (todayEvents.length > 4) {
          _suggestedTime = "Busy day. Aim for early morning (6-7 AM).";
          _timeAvailable = 30;
          _scheduleContext = "Heavy schedule detected.";
        } else {
          _suggestedTime = "Evening (5-7 PM) looks clear.";
          _scheduleContext = "Light schedule detected.";
        }
      }
      
      _aiAdvice = "Plan: $_workoutType. $_suggestedTime";
    });
    
    _loadSavedWorkout();
  }

  Future<void> _loadSavedWorkout() async {
    final prefs = await SharedPreferences.getInstance();
    String? savedJson = prefs.getString('current_workout_plan');
    if (savedJson != null) {
      try {
        final data = jsonDecode(savedJson);
        setState(() {
          _workoutPlan = data['exercises'];
          _aiAdvice = data['advice'] ?? _aiAdvice;
          _timeAvailable = (data['time'] as num).toDouble();
          _intensity = data['intensity'] ?? _intensity; // Load saved intensity too
          
          try {
            List<String> done = prefs.getStringList('workout_completed_indices') ?? [];
            _completedIndices.addAll(done.map((e) => int.parse(e)));
          } catch (e) {
            prefs.remove('workout_completed_indices');
          }
        });
      } catch (e) {
        print("Workout Data Corrupt: $e");
      }
    }
  }

  Future<void> _saveWorkoutState() async {
    final prefs = await SharedPreferences.getInstance();
    Map<String, dynamic> sessionData = {
      'exercises': _workoutPlan,
      'advice': _aiAdvice,
      'time': _timeAvailable,
      'intensity': _intensity
    };
    await prefs.setString('current_workout_plan', jsonEncode(sessionData));
    
    List<String> doneList = _completedIndices.map((e) => e.toString()).toList();
    await prefs.setStringList('workout_completed_indices', doneList);
  }

  // --- 2. MANUAL TIME EDIT ---
  void _editTimeManually() {
    TextEditingController timeController = TextEditingController(text: _timeAvailable.round().toString());
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.grey.shade900,
        title: const Text("Custom Duration", style: TextStyle(color: Colors.white)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text("Enter minutes:", style: TextStyle(color: Colors.grey)),
            const SizedBox(height: 10),
            TextField(
              controller: timeController,
              keyboardType: TextInputType.number,
              autofocus: true,
              style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold),
              textAlign: TextAlign.center,
              decoration: InputDecoration(
                filled: true,
                fillColor: Colors.black,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10))
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Cancel")),
          ElevatedButton(
            onPressed: () {
              double? val = double.tryParse(timeController.text);
              if (val != null && val > 0) {
                setState(() {
                  _timeAvailable = val;
                  // If plan exists, clear it because time changed
                  if (_workoutPlan.isNotEmpty) {
                    _workoutPlan = [];
                    _completedIndices.clear();
                    _aiAdvice = "Duration updated. Tap Generate to update plan.";
                  }
                });
              }
              Navigator.pop(ctx);
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.indigoAccent),
            child: const Text("Set Time", style: TextStyle(color: Colors.white)),
          )
        ],
      ),
    );
  }

  // --- 3. AI GENERATION ---
  Future<void> _generateWorkout() async {
    setState(() {
      _isLoading = true;
      _completedIndices.clear();
    });

    final prefs = await SharedPreferences.getInstance();
    List<String> soreMuscles = prefs.getStringList('sore_muscles') ?? [];

    String promptContext = """
    Goal: $_userGoal. 
    Time Available: ${_timeAvailable.round()} mins. 
    Intensity: $_intensity.
    Focus Type: $_workoutType.
    Schedule Context: $_scheduleContext (Suggest a workout that fits this energy level).
    """;
    
    if (soreMuscles.isNotEmpty) {
      promptContext += " AVOID using: ${soreMuscles.join(', ')}.";
    }

    try {
      final response = await http.post(
        Uri.parse('http://10.0.2.2:8000/generate-workout'),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"context": promptContext}),
      );

      if (!mounted) return;

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        setState(() {
          _workoutPlan = data['exercises'];
          _aiAdvice = data['advice'];
          _isLoading = false;
        });
        _saveWorkoutState(); 
      } else {
        _showError("Server Error: ${response.statusCode}");
      }
    } catch (e) {
      _showError("Connection Failed. Using Offline Backup.");
      setState(() => _isLoading = false);
    }
  }

  void _toggleExercise(int index) {
    setState(() {
      if (_completedIndices.contains(index)) {
        _completedIndices.remove(index);
      } else {
        _completedIndices.add(index);
      }
    });
    _saveWorkoutState();
  }

  void _clearSession() async {
    setState(() {
      _workoutPlan = [];
      _completedIndices.clear();
      _aiAdvice = "Session Cleared. Re-analyzing...";
    });
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('current_workout_plan');
    await prefs.remove('workout_completed_indices');
    _loadSmartData(); 
  }

  void _showError(String msg) {
    if (!mounted) return;
    setState(() => _isLoading = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), backgroundColor: Colors.red));
  }

  @override
  Widget build(BuildContext context) {
    double progress = _workoutPlan.isEmpty ? 0 : _completedIndices.length / _workoutPlan.length;

    // Safety check for slider visual
    double sliderValue = _timeAvailable;
    if (sliderValue < 10) sliderValue = 10;
    if (sliderValue > 120) sliderValue = 120; 

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("Smart Trainer"),
        backgroundColor: Colors.indigo.shade900,
        actions: [
          IconButton(
            icon: const Icon(Icons.delete_outline),
            tooltip: "Clear Session",
            onPressed: _clearSession,
          )
        ],
      ),
      body: Column(
        children: [
          // --- 1. CONFIGURATION DASHBOARD (ALWAYS VISIBLE) ---
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.grey.shade900,
              border: Border(bottom: BorderSide(color: Colors.indigo.withOpacity(0.5)))
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text("TODAY'S FOCUS", style: TextStyle(color: Colors.grey[400], fontSize: 10, fontWeight: FontWeight.bold)),
                          Text(
                            _workoutType, 
                            style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                            overflow: TextOverflow.ellipsis,
                            maxLines: 1,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 10),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text("SUGGESTED", style: TextStyle(color: Colors.grey[400], fontSize: 10, fontWeight: FontWeight.bold)),
                        Text(_suggestedTime, style: const TextStyle(color: Colors.greenAccent, fontSize: 14, fontWeight: FontWeight.bold)),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: 15),
                
                // CONTROLS (Always Visible)
                Row(
                  children: [
                    const Icon(Icons.timer, color: Colors.indigoAccent, size: 20),
                    const SizedBox(width: 10),
                    // Manual Time Edit
                    InkWell(
                      onTap: _editTimeManually,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          border: Border.all(color: Colors.white24),
                          borderRadius: BorderRadius.circular(5)
                        ),
                        child: Text(
                          "${_timeAvailable.round()} min ✎", 
                          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Slider(
                        value: sliderValue,
                        min: 10, max: 120, 
                        activeColor: Colors.indigoAccent,
                        onChanged: (val) {
                          setState(() {
                            _timeAvailable = val;
                            // Optional: Clear plan if dragging slider? Or just let user hit Regenerate.
                          });
                        },
                      ),
                    ),
                  ],
                ),
                
                // Intensity Dropdown
                Row(
                  children: [
                    const Icon(Icons.speed, color: Colors.indigoAccent, size: 20),
                    const SizedBox(width: 10),
                    Expanded(
                      child: DropdownButtonHideUnderline(
                        child: DropdownButton<String>(
                          value: _intensity,
                          dropdownColor: Colors.grey.shade900,
                          isDense: true,
                          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                          items: ["Low (Recovery)", "Medium (Endurance)", "High (Performance)"]
                              .map((e) => DropdownMenuItem(value: e, child: Text(e))).toList(),
                          onChanged: (val) => setState(() => _intensity = val!),
                        ),
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 10),
                
                // Generate/Regenerate Button
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _generateWorkout,
                    icon: Icon(_workoutPlan.isEmpty ? Icons.bolt : Icons.refresh),
                    label: Text(_workoutPlan.isEmpty ? "GENERATE WORKOUT" : "REGENERATE PLAN"),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.indigoAccent,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                    ),
                  ),
                ),
              ],
            ),
          ),

          // --- 2. PROGRESS ---
          if (_workoutPlan.isNotEmpty)
            LinearProgressIndicator(
              value: progress,
              backgroundColor: Colors.black,
              valueColor: AlwaysStoppedAnimation<Color>(
                progress == 1.0 ? Colors.greenAccent : Colors.indigo
              ),
              minHeight: 4,
            ),

          // --- 3. EXERCISE LIST ---
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator(color: Colors.indigoAccent))
                : _workoutPlan.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.fitness_center, size: 60, color: Colors.white10),
                            const SizedBox(height: 10),
                            const Text("Configure & Generate", style: TextStyle(color: Colors.white24)),
                          ],
                        ),
                      )
                    : ListView(
                        padding: const EdgeInsets.all(16),
                        children: [
                          // Advice
                          Container(
                            padding: const EdgeInsets.all(15),
                            margin: const EdgeInsets.only(bottom: 20),
                            decoration: BoxDecoration(
                              color: Colors.indigo.withOpacity(0.15),
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(color: Colors.indigo.withOpacity(0.3))
                            ),
                            child: Row(
                              children: [
                                const Icon(Icons.psychology, color: Colors.indigoAccent, size: 20),
                                const SizedBox(width: 12),
                                Expanded(child: Text(_aiAdvice, style: const TextStyle(color: Colors.white70, fontSize: 13))),
                              ],
                            ),
                          ),

                          const Text("ROUTINE", style: TextStyle(color: Colors.grey, fontSize: 11, fontWeight: FontWeight.bold)),
                          const SizedBox(height: 10),

                          // List
                          ..._workoutPlan.asMap().entries.map((entry) {
                            int index = entry.key;
                            var ex = entry.value;
                            bool isDone = _completedIndices.contains(index);

                            return AnimatedContainer(
                              duration: const Duration(milliseconds: 300),
                              margin: const EdgeInsets.only(bottom: 10),
                              decoration: BoxDecoration(
                                color: isDone ? Colors.green.withOpacity(0.05) : Colors.grey.shade900,
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(
                                  color: isDone ? Colors.green.withOpacity(0.3) : Colors.transparent
                                )
                              ),
                              child: ListTile(
                                onTap: () => _toggleExercise(index),
                                leading: CircleAvatar(
                                  radius: 14,
                                  backgroundColor: isDone ? Colors.green : Colors.grey.shade800,
                                  child: isDone 
                                    ? const Icon(Icons.check, size: 16, color: Colors.white)
                                    : Text("${index + 1}", style: const TextStyle(color: Colors.white70, fontSize: 12)),
                                ),
                                title: Text(
                                  ex['name'],
                                  style: TextStyle(
                                    color: isDone ? Colors.white38 : Colors.white,
                                    fontWeight: isDone ? FontWeight.normal : FontWeight.w600,
                                    decoration: isDone ? TextDecoration.lineThrough : null,
                                  ),
                                ),
                                subtitle: Text(
                                  "${ex['sets']} Sets  •  ${ex['reps']}",
                                  style: TextStyle(color: isDone ? Colors.white24 : Colors.indigoAccent),
                                ),
                                trailing: Checkbox(
                                  value: isDone,
                                  activeColor: Colors.green,
                                  checkColor: Colors.black,
                                  side: BorderSide(color: Colors.grey.shade700),
                                  onChanged: (val) => _toggleExercise(index),
                                ),
                              ),
                            );
                          }),
                        ],
                      ),
          ),
        ],
      ),
    );
  }
}