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

// --- CENTRALIZED CONSTANTS ---
class AppKeys {
  static const String lastActive = 'last_active_timestamp';
  static const String sleepHours = 'last_sleep_hours';
  static const String reflexScore = 'last_reflex_score';
  static const String soreMuscles = 'sore_muscles';
  static const String mealLogs = 'meal_logs';
  static const String bioHistory = 'daily_bio_history';
  static const String calorieTarget = 'daily_calorie_target';
  static const String dynamicTarget = 'dynamic_calorie_target';
}

class BioThresholds {
  static const int reflexFatigue = 350;
  static const double sleepFatigue = 5.5;
  static const int stepBaseline = 3000;
}

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> with WidgetsBindingObserver {
  late SharedPreferences _prefs;
  bool _prefsLoaded = false;

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
  String _sorenessStatus = "None";

  // STEP TRACKING
  late Stream<StepCount> _stepCountStream;
  int _steps = 0;
  int _initialSteps = -1;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initApp();
  }

  Future<void> _initApp() async {
    _prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() => _prefsLoaded = true);
    
    await Future.wait([
      _checkAutoSleep(),
      _syncAllData(),
    ]);
    
    _initPedometer();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!_prefsLoaded) return;
    if (state == AppLifecycleState.paused) {
      _prefs.setInt(AppKeys.lastActive, DateTime.now().millisecondsSinceEpoch);
    } else if (state == AppLifecycleState.resumed) {
      _checkAutoSleep();
    }
  }

  Future<void> _checkAutoSleep() async {
    if (!_prefsLoaded) return;
    int? lastActive = _prefs.getInt(AppKeys.lastActive);

    if (lastActive != null) {
      DateTime lastTime = DateTime.fromMillisecondsSinceEpoch(lastActive);
      DateTime now = DateTime.now();
      double hoursAway = now.difference(lastTime).inMinutes / 60.0;

      double currentSleep = _prefs.getDouble(AppKeys.sleepHours) ?? 0.0;
      
      // LOGIC: Only detect if between 6h and 16h (Avoids "Coma Bug")
      if (hoursAway > 6.0 && hoursAway < 16.0 && currentSleep == 0.0) { 
        await _prefs.setDouble(AppKeys.sleepHours, hoursAway);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("😴 Detected ${hoursAway.toStringAsFixed(1)}h sleep."), backgroundColor: Colors.indigo)
        );
        _syncAllData();
      }
    }
  }

  Future<void> _syncAllData() async {
    if (!_prefsLoaded) return;
    _syncProfile();
    _syncBioMetrics();
    _syncNutrition();
  }

  void _syncProfile() {
    _userName = _prefs.getString('user_name') ?? "User";
    _userGoal = _prefs.getString('user_goal') ?? "Maintain";
    _baseDailyTarget = _prefs.getInt(AppKeys.calorieTarget) ?? 2000;
    _dynamicDailyTarget = _prefs.getInt(AppKeys.dynamicTarget) ?? _baseDailyTarget;
    _recalcDynamicTarget();
  }

  void _syncBioMetrics() {
    int reflex = _prefs.getInt(AppKeys.reflexScore) ?? 0;
    double sleep = _prefs.getDouble(AppKeys.sleepHours) ?? 7.0;
    List<String> soreMuscles = _prefs.getStringList(AppKeys.soreMuscles) ?? [];

    _saveDailyStatsHistory(reflex, sleep);

    setState(() {
      _reflexScore = reflex;
      _sleepHours = sleep;
      _sorenessStatus = soreMuscles.isEmpty ? "None" : soreMuscles.length > 2 ? "${soreMuscles.length} Areas" : soreMuscles.join(", ");
      
      bool reflexFatigue = _reflexScore > BioThresholds.reflexFatigue && _reflexScore > 0;
      bool sleepFatigue = _sleepHours < BioThresholds.sleepFatigue;
      
      if (reflexFatigue) {
        _isGhostMode = true;
        _statusReason = "CNS Fatigue";
      } else if (sleepFatigue) {
        _isGhostMode = true;
        _statusReason = "Sleep Debt";
      } else {
        _isGhostMode = false;
        _statusReason = "Peak State";
      }
    });
  }

  void _syncNutrition() {
    final String? logsString = _prefs.getString(AppKeys.mealLogs);
    if (logsString != null) {
      List<dynamic> logs = jsonDecode(logsString);
      int totalCals = 0;
      double p = 0, c = 0, f = 0;
      String today = DateTime.now().toString().split(' ')[0];

      for (var log in logs) {
        if (log['time'] != null && log['time'].toString().startsWith(today)) {
          totalCals += (log['calories'] as num).toInt();
          if (log['macros'] != null) {
            p += _safeParse(log['macros']['protein']);
            c += _safeParse(log['macros']['carbs']);
            f += _safeParse(log['macros']['fat']);
          }
        }
      }
      setState(() {
        _caloriesConsumed = totalCals;
        _proteinConsumed = p;
        _carbsConsumed = c;
        _fatConsumed = f;
      });
    }
  }

  void _initPedometer() async {
    if (await Permission.activityRecognition.request().isGranted) {
      _stepCountStream = Pedometer.stepCountStream;
      _stepCountStream.listen(_onStepCount).onError((e) => print("Step Error: $e"));
    }
  }

  void _onStepCount(StepCount event) {
    if (!mounted) return;
    setState(() {
      if (_initialSteps == -1) _initialSteps = event.steps;
      _steps = (event.steps - _initialSteps);
      if (_steps < 0) _steps = 0;
      _recalcDynamicTarget();
    });
  }

  Future<void> _recalcDynamicTarget() async {
    if (!_prefsLoaded) return;
    int activeSteps = _steps - BioThresholds.stepBaseline;
    if (activeSteps < 0) activeSteps = 0;
    
    int extraBurn = (activeSteps / 1000 * 40).round();
    
    int newTarget = _baseDailyTarget + extraBurn;
    if (newTarget != _dynamicDailyTarget) {
      setState(() => _dynamicDailyTarget = newTarget);
      await _prefs.setInt(AppKeys.dynamicTarget, _dynamicDailyTarget);
    }
  }

  Future<void> _saveDailyStatsHistory(int reflex, double sleep) async {
    if (!_prefsLoaded) return;
    List<String> history = _prefs.getStringList(AppKeys.bioHistory) ?? [];
    String today = DateTime.now().toString().split(' ')[0]; 

    history.removeWhere((e) => jsonDecode(e)['date'] == today);
    
    var newEntry = {'date': today, 'reflex': reflex, 'sleep': sleep};
    history.add(jsonEncode(newEntry));
    
    await _prefs.setStringList(AppKeys.bioHistory, history);
  }

  double _safeParse(dynamic value) {
    if (value == null) return 0.0;
    if (value is num) return value.toDouble();
    String clean = value.toString().replaceAll(RegExp(r'[^\d.]'), '');
    return double.tryParse(clean) ?? 0.0;
  }

  @override
  Widget build(BuildContext context) {
    if (!_prefsLoaded) return const Scaffold(backgroundColor: Colors.black, body: Center(child: CircularProgressIndicator()));

    Color primaryColor = _isGhostMode ? Colors.deepPurple.shade900 : Colors.teal.shade900;
    Color accentColor = _isGhostMode ? Colors.purpleAccent : Colors.tealAccent;
    IconData statusIcon = _isGhostMode ? Icons.battery_alert : Icons.bolt;

    double progress = _dynamicDailyTarget == 0 ? 0 : _caloriesConsumed / _dynamicDailyTarget;
    if (progress > 1.0) progress = 1.0;

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("BioSync OS"),
        backgroundColor: primaryColor,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.bar_chart),
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (context) => const StatsScreen())),
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _syncAllData,
          )
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // HERO STATUS CARD
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [primaryColor, Colors.black],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: accentColor.withOpacity(0.3)),
                boxShadow: [BoxShadow(color: primaryColor.withOpacity(0.4), blurRadius: 20, offset: const Offset(0, 10))]
              ),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      // Fix: Wrapped in Expanded to prevent text overflow
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(_statusReason.toUpperCase(), style: TextStyle(color: accentColor, fontWeight: FontWeight.bold, letterSpacing: 1.2)),
                            const SizedBox(height: 5),
                            Text("Hello, $_userName", style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.bold), overflow: TextOverflow.ellipsis),
                          ],
                        ),
                      ),
                      const SizedBox(width: 10),
                      Icon(statusIcon, color: accentColor, size: 42),
                    ],
                  ),
                  const SizedBox(height: 25),
                  // DIAGNOSTICS ROW
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Expanded(child: _buildMiniStat(Icons.bed, "${_sleepHours.toStringAsFixed(1)}h Sleep", Colors.blueGrey)),
                      const SizedBox(width: 8), 
                      Expanded(child: _buildMiniStat(Icons.directions_walk, "$_steps Steps", Colors.blue)),
                      const SizedBox(width: 8), 
                      Expanded(child: _buildMiniStat(Icons.accessibility, _sorenessStatus, _sorenessStatus == "None" ? Colors.green : Colors.redAccent)),
                    ],
                  )
                ],
              ),
            ),

            const SizedBox(height: 25),

            // ENERGY BUDGET
            const Text("ENERGY BUDGET", style: TextStyle(color: Colors.grey, fontSize: 12, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(color: Colors.grey.shade900, borderRadius: BorderRadius.circular(20)),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text("$_caloriesConsumed / $_dynamicDailyTarget kcal", style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
                      if (_dynamicDailyTarget > _baseDailyTarget)
                         Text("+${_dynamicDailyTarget - _baseDailyTarget} Active Bonus", style: const TextStyle(color: Colors.greenAccent, fontSize: 12)),
                    ],
                  ),
                  const SizedBox(height: 15),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: LinearProgressIndicator(
                      value: progress,
                      minHeight: 12,
                      backgroundColor: Colors.black,
                      valueColor: AlwaysStoppedAnimation<Color>(progress >= 1.0 ? Colors.redAccent : accentColor),
                    ),
                  ),
                  const SizedBox(height: 15),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      _buildMacro("PRO", _proteinConsumed, Colors.blue),
                      _buildMacro("CARB", _carbsConsumed, Colors.orange),
                      _buildMacro("FAT", _fatConsumed, Colors.red),
                    ],
                  )
                ],
              ),
            ),

            const SizedBox(height: 30),

            // ACTIONS GRID
            const Text("COMMAND CENTER", style: TextStyle(color: Colors.grey, fontSize: 12, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              childAspectRatio: 1.4,
              children: [
                _ActionCard(
                  title: "Bio-Sync", icon: Icons.fingerprint, color: Colors.deepOrange.shade900,
                  onTap: () async { await Navigator.push(context, MaterialPageRoute(builder: (context) => const BioCheckinScreen())); _syncAllData(); },
                ),
                _ActionCard(
                  title: "Log Meal", icon: Icons.add_a_photo, color: Colors.teal.shade800,
                  onTap: () async { await Navigator.push(context, MaterialPageRoute(builder: (context) => const MealLogScreen())); _syncNutrition(); },
                ),
                _ActionCard(
                  title: "Workout", icon: Icons.fitness_center, color: Colors.indigo.shade800,
                  onTap: () => Navigator.push(context, MaterialPageRoute(builder: (context) => const WorkoutScreen())),
                ),
                _ActionCard(
                  title: "Body Map", icon: Icons.accessibility_new, color: Colors.red.shade900,
                  onTap: () async { await Navigator.push(context, MaterialPageRoute(builder: (context) => const BodyMapScreen())); _syncBioMetrics(); },
                ),
                _ActionCard(
                  title: "Chef AI", icon: Icons.restaurant, color: Colors.purple.shade900,
                  onTap: () => Navigator.push(context, MaterialPageRoute(builder: (context) => const SmartMealPlannerScreen())),
                ),
                _ActionCard(
                  title: "Roster", icon: Icons.calendar_month, color: Colors.blue.shade900,
                  onTap: () => Navigator.push(context, MaterialPageRoute(builder: (context) => const RosterScreen())),
                ),
              ],
            ),
            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }

  // --- SAFE LAYOUT BUILDER ---
  Widget _buildMiniStat(IconData icon, String label, Color color) {
    return Row(
      children: [
        Icon(icon, color: color, size: 16),
        const SizedBox(width: 6),
        // FIX: Expanded + maxLines prevents layout explosion
        Expanded(
          child: Text(
            label, 
            style: const TextStyle(color: Colors.white70, fontSize: 12), 
            overflow: TextOverflow.ellipsis,
            maxLines: 1, 
          ),
        ),
      ],
    );
  }

  Widget _buildMacro(String label, double val, Color color) {
    return Column(
      children: [
        Text("${val.round()}g", style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
        Text(label, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.bold)),
      ],
    );
  }
}

class _ActionCard extends StatelessWidget {
  final String title;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;

  const _ActionCard({required this.title, required this.icon, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        decoration: BoxDecoration(
          color: color.withOpacity(0.8),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.white10)
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: Colors.white, size: 32),
            const SizedBox(height: 8),
            Text(title, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ],
        ),
      ),
    );
  }
}