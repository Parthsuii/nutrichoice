import 'dart:convert';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:pedometer/pedometer.dart';
import 'package:permission_handler/permission_handler.dart';

// --- IMPORTS ---
import 'bio_checkin_screen.dart';      
import 'roster_screen.dart';
import 'meal_log_screen.dart';
import 'smart_meal_planner_screen.dart'; 
import 'body_map_screen.dart'; 
import 'shopping_list_screen.dart'; 
import 'workout_screen.dart'; 
import 'stats_screen.dart'; 

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> with WidgetsBindingObserver {
  // PROFILE DATA
  String _userName = "User";
  String _userGoal = "Maintain";
  int _baseDailyTarget = 2000;
  int _dynamicDailyTarget = 2000;

  // LIVE BIO-DATA
  int _caloriesConsumed = 0;
  double _proteinConsumed = 0;
  double _carbsConsumed = 0;
  double _fatConsumed = 0;

  // ENGINE 1 DATA
  int _reflexScore = 0;
  double _sleepHours = 0.0;
  bool _isGhostMode = false;
  String _statusReason = "Ready";
  String _sorenessStatus = "None"; // <--- NEW: Stores sore muscles string

  // STEP TRACKING
  late Stream<StepCount> _stepCountStream;
  int _steps = 0;
  int _initialSteps = -1;
  int _simulatedSteps = 0; 

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _checkAutoSleep();
    _loadBioData();
    _initPedometer();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) {
      _saveLastActiveTime();
    } else if (state == AppLifecycleState.resumed) {
      _checkAutoSleep();
    }
  }

  Future<void> _saveLastActiveTime() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('last_active_timestamp', DateTime.now().millisecondsSinceEpoch);
  }

  Future<void> _checkAutoSleep() async {
    final prefs = await SharedPreferences.getInstance();
    int? lastActive = prefs.getInt('last_active_timestamp');

    if (lastActive != null) {
      DateTime lastTime = DateTime.fromMillisecondsSinceEpoch(lastActive);
      DateTime now = DateTime.now();
      Duration diff = now.difference(lastTime);
      double hoursAway = diff.inMinutes / 60.0;

      if (hoursAway > 6.0) { 
        await prefs.setDouble('last_sleep_hours', hoursAway);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("😴 Detected ${hoursAway.toStringAsFixed(1)}h sleep."), backgroundColor: Colors.indigo)
        );
        _loadBioData();
      }
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _loadBioData();
  }

  void _initPedometer() async {
    if (await Permission.activityRecognition.request().isGranted) {
      _stepCountStream = Pedometer.stepCountStream;
      _stepCountStream.listen(_onStepCount).onError(_onStepError);
    }
  }

  void _onStepCount(StepCount event) {
    setState(() {
      if (_initialSteps == -1) _initialSteps = event.steps;
      _steps = (event.steps - _initialSteps) + _simulatedSteps;
      if (_steps < 0) _steps = 0;
      _recalcDynamicTarget();
    });
  }

  void _onStepError(error) {
    print("Pedometer Error: $error");
  }

  void _simulateWalk() {
    setState(() {
      _simulatedSteps += 500;
      _steps += 500;
      _recalcDynamicTarget();
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text("Debug: Added 500 steps. Total: $_steps"), duration: const Duration(milliseconds: 500)),
    );
  }

  Future<void> _recalcDynamicTarget() async {
    int activeSteps = _steps - 3000;
    if (activeSteps < 0) activeSteps = 0;
    int extraBurn = (activeSteps / 1000 * 40).round();
    
    int newTarget = _baseDailyTarget + extraBurn;
    if (newTarget != _dynamicDailyTarget) {
      setState(() {
        _dynamicDailyTarget = newTarget;
      });
      final prefs = await SharedPreferences.getInstance();
      await prefs.setInt('dynamic_calorie_target', _dynamicDailyTarget);
    }
  }

  // --- BIO LOGIC & HISTORY SAVING ---
  Future<void> _loadBioData() async {
    final prefs = await SharedPreferences.getInstance();
    
    int reflex = prefs.getInt('last_reflex_score') ?? 0;
    double sleep = prefs.getDouble('last_sleep_hours') ?? 7.0;
    
    // [NEW] Load Soreness Data
    List<String> soreMuscles = prefs.getStringList('sore_muscles') ?? [];
    String soreString = soreMuscles.isEmpty ? "None" : soreMuscles.join(", ");

    _saveDailyStats(reflex, sleep);

    setState(() {
      _userName = prefs.getString('user_name') ?? "User";
      _userGoal = prefs.getString('user_goal') ?? "Maintain";
      _baseDailyTarget = prefs.getInt('daily_calorie_target') ?? 2000;
      _dynamicDailyTarget = prefs.getInt('dynamic_calorie_target') ?? _baseDailyTarget;
      _recalcDynamicTarget();

      _reflexScore = reflex;
      _sleepHours = sleep;
      _sorenessStatus = soreString; // Update UI variable
      
      if (_reflexScore > 350 && _reflexScore > 0) {
        _isGhostMode = true;
        _statusReason = "Slow Reflexes";
      } else if (_sleepHours < 5.5) {
        _isGhostMode = true;
        _statusReason = "Low Sleep";
      } else {
        _isGhostMode = false;
        _statusReason = "Peak Condition";
      }
    });

    final String? logsString = prefs.getString('meal_logs');
    if (logsString != null) {
      List<dynamic> logs = jsonDecode(logsString);
      int totalCals = 0;
      double totalProtein = 0;
      double totalCarbs = 0;
      double totalFat = 0;
      String today = DateTime.now().toString().split(' ')[0];

      for (var log in logs) {
        if (log['time'] != null && log['time'].toString().startsWith(today)) {
          totalCals += (log['calories'] as num).toInt();
          if (log['macros'] != null) {
            totalProtein += _safeParse(log['macros']['protein']);
            totalCarbs += _safeParse(log['macros']['carbs']);
            totalFat += _safeParse(log['macros']['fat']);
          }
        }
      }
      setState(() {
        _caloriesConsumed = totalCals;
        _proteinConsumed = totalProtein;
        _carbsConsumed = totalCarbs;
        _fatConsumed = totalFat;
      });
    }
  }

  Future<void> _saveDailyStats(int reflex, double sleep) async {
    final prefs = await SharedPreferences.getInstance();
    List<String> history = prefs.getStringList('daily_bio_history') ?? [];
    String today = DateTime.now().toString().split(' ')[0]; 

    bool foundToday = false;
    for (int i = 0; i < history.length; i++) {
      var entry = jsonDecode(history[i]);
      if (entry['date'] == today) {
        entry['reflex'] = reflex;
        entry['sleep'] = sleep;
        history[i] = jsonEncode(entry);
        foundToday = true;
        break;
      }
    }

    if (!foundToday) {
      var newEntry = {'date': today, 'reflex': reflex, 'sleep': sleep};
      history.add(jsonEncode(newEntry));
    }

    await prefs.setStringList('daily_bio_history', history);
  }

  double _safeParse(dynamic value) {
    if (value == null) return 0.0;
    if (value is num) return value.toDouble();
    String clean = value.toString().replaceAll(RegExp(r'[^\d.]'), '');
    return double.tryParse(clean) ?? 0.0;
  }

  @override
  Widget build(BuildContext context) {
    Color primaryColor = _isGhostMode ? Colors.deepPurple.shade900 : Colors.teal.shade900;
    Color accentColor = _isGhostMode ? Colors.purpleAccent : Colors.tealAccent;
    String statusMessage = _isGhostMode 
        ? "⚠️ Recovery Mode ($_statusReason)" 
        : "⚡ $_statusReason. Ready to Go.";

    double progress = _caloriesConsumed / _dynamicDailyTarget;
    if (progress > 1.0) progress = 1.0;
    Color progressBarColor = accentColor;
    if (progress >= 1.0) progressBarColor = Colors.redAccent;

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("BioSync v2.2"),
        backgroundColor: primaryColor,
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.bar_chart),
            tooltip: "Stats & Streak",
            onPressed: () {
              Navigator.push(context, MaterialPageRoute(builder: (context) => const StatsScreen()));
            },
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              _loadBioData();
              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Syncing Data...")));
            },
          )
        ],
      ),
      body: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(20.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // --- READINESS & STEPS ---
              Row(
                children: [
                  Expanded(
                    flex: 3,
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 500),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: _isGhostMode ? Colors.purple.withOpacity(0.2) : Colors.green.withOpacity(0.2),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: _isGhostMode ? Colors.purple : Colors.green),
                      ),
                      child: Row(
                        children: [
                          Icon(_isGhostMode ? Icons.nights_stay : Icons.bolt, size: 18, color: _isGhostMode ? Colors.purpleAccent : Colors.greenAccent),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(statusMessage, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold), overflow: TextOverflow.ellipsis),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    flex: 2,
                    child: GestureDetector(
                      onTap: _simulateWalk,
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(color: Colors.grey.shade900, borderRadius: BorderRadius.circular(10), border: Border.all(color: Colors.white24)),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.directions_walk, size: 18, color: Colors.blueAccent),
                            const SizedBox(width: 5),
                            Text("$_steps", style: const TextStyle(color: Colors.blueAccent, fontWeight: FontWeight.bold)),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 15),

              // --- MISSION CONTROL ---
              AnimatedContainer(
                duration: const Duration(milliseconds: 500),
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [primaryColor.withOpacity(0.8), Colors.black],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: primaryColor.withOpacity(0.5)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text("Welcome, $_userName.", style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold)),
                            Text("Mission: $_userGoal", style: TextStyle(color: accentColor, fontSize: 14)),
                          ],
                        ),
                        const Icon(Icons.fingerprint, color: Colors.white24, size: 40),
                      ],
                    ),
                    const SizedBox(height: 20),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text("Dynamic Budget", style: TextStyle(color: Colors.grey)),
                        Text("$_caloriesConsumed / $_dynamicDailyTarget kcal", style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                      ],
                    ),
                    const SizedBox(height: 8),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: LinearProgressIndicator(
                        value: progress,
                        minHeight: 10,
                        backgroundColor: Colors.grey.shade800,
                        valueColor: AlwaysStoppedAnimation<Color>(progressBarColor),
                      ),
                    ),
                    if (_dynamicDailyTarget > _baseDailyTarget)
                      Padding(
                        padding: const EdgeInsets.only(top: 8.0),
                        child: Text("⚡ Activity Bonus: +${_dynamicDailyTarget - _baseDailyTarget} kcal earned", style: const TextStyle(color: Colors.blueAccent, fontSize: 12, fontStyle: FontStyle.italic)),
                      ),
                    const SizedBox(height: 20),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        _buildMacroStat("Protein", "${_proteinConsumed.round()}g", Colors.blue),
                        _buildMacroStat("Carbs", "${_carbsConsumed.round()}g", Colors.orange),
                        _buildMacroStat("Fat", "${_fatConsumed.round()}g", Colors.red),
                      ],
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 25),

              // --- ENGINE 1 ---
              Text("Engine 1: The Body", style: TextStyle(color: accentColor, fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 15),
              _MenuCard(
                title: "Daily Bio-Sync",
                subtitle: _reflexScore > 0 ? "Readiness Recorded" : "Measure Sleep & Reflexes",
                icon: Icons.bolt,
                color: _isGhostMode ? Colors.purple.shade800 : Colors.deepOrange.shade800,
                onTap: () async {
                  await Navigator.push(context, MaterialPageRoute(builder: (context) => const BioCheckinScreen()));
                  _loadBioData();
                },
              ),
              
              // --- DIAGNOSTICS ROW (NOW WITH SORENESS) ---
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text("Sleep: ${_sleepHours}h", style: const TextStyle(color: Colors.grey, fontSize: 12)),
                    // [NEW] Visual confirmation of Soreness Sync
                    Flexible(child: Text("Soreness: $_sorenessStatus", style: const TextStyle(color: Colors.redAccent, fontSize: 12), overflow: TextOverflow.ellipsis)),
                  ],
                ),
              ),

              const SizedBox(height: 15),
              _MenuCard(
                title: "Smart Soreness",
                subtitle: "Log pain points & adapt diet",
                icon: Icons.accessibility_new,
                color: Colors.red.shade900,
                onTap: () async {
                  await Navigator.push(context, MaterialPageRoute(builder: (context) => const BodyMapScreen()));
                  _loadBioData();
                }
              ),

              const SizedBox(height: 25),

              // --- ENGINE 2 & 3 ---
              Text("Engine 2 & 3: Logistics & Fuel", style: TextStyle(color: accentColor, fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 15),
              
              _MenuCard(
                title: "Adaptive Flow",
                subtitle: "Time-crunched? Custom Workout.",
                icon: Icons.timer,
                color: Colors.indigo.shade800,
                onTap: () => Navigator.push(context, MaterialPageRoute(builder: (context) => const WorkoutScreen())),
              ),
              
              const SizedBox(height: 15),
              _MenuCard(
                title: "Calorie Tracker",
                subtitle: "Snap meals & track progress",
                icon: Icons.local_fire_department,
                color: Colors.teal.shade800,
                onTap: () async {
                  await Navigator.push(context, MaterialPageRoute(builder: (context) => const MealLogScreen()));
                  _loadBioData();
                },
              ),
              const SizedBox(height: 15),
              _MenuCard(
                title: "Context Chef",
                subtitle: "Smart Meal Plan & Shopping",
                icon: Icons.restaurant_menu,
                color: Colors.purple.shade900,
                onTap: () async {
                  await Navigator.push(context, MaterialPageRoute(builder: (context) => const SmartMealPlannerScreen()));
                  _loadBioData();
                },
              ),
              const SizedBox(height: 15),
              _MenuCard(
                title: "Smart Groceries",
                subtitle: "Auto-generated list",
                icon: Icons.shopping_basket,
                color: Colors.green.shade800,
                onTap: () => Navigator.push(context, MaterialPageRoute(builder: (context) => const ShoppingListScreen())),
              ),
              const SizedBox(height: 15),
              _MenuCard(
                title: "Import Roster",
                subtitle: "Scan WhatsApp Timetable",
                icon: Icons.document_scanner,
                color: Colors.blue.shade800,
                onTap: () => Navigator.push(context, MaterialPageRoute(builder: (context) => const RosterScreen())),
              ),
              const SizedBox(height: 50),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildMacroStat(String label, String value, Color color) {
    return Column(children: [Text(value, style: TextStyle(color: color, fontSize: 18, fontWeight: FontWeight.bold)), Text(label, style: const TextStyle(color: Colors.grey, fontSize: 12))]);
  }
}

class _MenuCard extends StatelessWidget {
  final String title, subtitle;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;

  const _MenuCard({required this.title, required this.subtitle, required this.icon, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(15)),
        child: Row(children: [
          Icon(icon, size: 40, color: Colors.white),
          const SizedBox(width: 20),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
            Text(subtitle, style: const TextStyle(color: Colors.white70)),
          ])),
          const Icon(Icons.arrow_forward_ios, color: Colors.white30, size: 16),
        ]),
      ),
    );
  }
}