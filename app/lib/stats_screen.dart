import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:table_calendar/table_calendar.dart';

// --- 1. STRONG DATA MODEL (Fixes "dynamic" risk) ---
class DailyBioEntry implements Comparable<DailyBioEntry> {
  final DateTime date;
  final double sleep;
  final int reflex;

  DailyBioEntry({required this.date, required this.sleep, required this.reflex});

  // Factory to safely parse JSON
  factory DailyBioEntry.fromJson(Map<String, dynamic> json) {
    return DailyBioEntry(
      date: DateTime.parse(json['date']),
      // Handle potential type mismatches safely
      sleep: (json['sleep'] as num).toDouble(),
      reflex: (json['reflex'] as num).toInt(),
    );
  }

  // Helper for calendar normalization
  DateTime get normalizedDate => DateTime(date.year, date.month, date.day);

  @override
  int compareTo(DailyBioEntry other) => date.compareTo(other.date);
}

class StatsScreen extends StatefulWidget {
  const StatsScreen({super.key});

  @override
  State<StatsScreen> createState() => _StatsScreenState();
}

class _StatsScreenState extends State<StatsScreen> {
  // Data Containers
  Map<DateTime, List<DailyBioEntry>> _events = {}; // Typed List
  List<FlSpot> _sleepSpots = [];
  List<FlSpot> _reflexSpots = [];
  int _currentStreak = 0;
  
  // Calendar Settings
  CalendarFormat _calendarFormat = CalendarFormat.twoWeeks;
  DateTime _focusedDay = DateTime.now();
  DateTime? _selectedDay;

  @override
  void initState() {
    super.initState();
    _loadHistoryData();
  }

  Future<void> _loadHistoryData() async {
    final prefs = await SharedPreferences.getInstance();
    List<String> historyRaw = prefs.getStringList('daily_bio_history') ?? [];
    
    // 1. Parse & Sort Data (Crucial Fix)
    List<DailyBioEntry> allEntries = historyRaw.map((raw) {
      return DailyBioEntry.fromJson(jsonDecode(raw));
    }).toList();

    // Sort oldest to newest ensures Graphs and Streaks work correctly
    allEntries.sort(); 

    // Temp variables
    Map<DateTime, List<DailyBioEntry>> events = {};
    List<FlSpot> sleepData = [];
    List<FlSpot> reflexData = [];
    
    // 2. Populate Data Structures
    for (int i = 0; i < allEntries.length; i++) {
      var entry = allEntries[i];
      
      // Calendar Mapping
      if (events[entry.normalizedDate] == null) events[entry.normalizedDate] = [];
      events[entry.normalizedDate]!.add(entry);

      // Graphing (Last 7 days only)
      if (i >= allEntries.length - 7) {
        // We use a simple index 0..6 for the visual trend
        // (Since we sorted above, this line will be correct)
        double relativeX = (i - (allEntries.length - 7)).toDouble(); 
        if (relativeX >= 0) {
           sleepData.add(FlSpot(relativeX, entry.sleep));
           reflexData.add(FlSpot(relativeX, entry.reflex.toDouble()));
        }
      }
    }

    // 3. Robust Streak Calculation
    int streak = _calculateStreak(allEntries);

    if (!mounted) return;
    setState(() {
      _events = events;
      _sleepSpots = sleepData;
      _reflexSpots = reflexData;
      _currentStreak = streak;
    });
  }

  int _calculateStreak(List<DailyBioEntry> sortedEntries) {
    if (sortedEntries.isEmpty) return 0;

    // Get unique dates sorted Newest -> Oldest
    Set<DateTime> uniqueDates = sortedEntries.map((e) => e.normalizedDate).toSet();
    List<DateTime> sortedDates = uniqueDates.toList()..sort((a, b) => b.compareTo(a));

    DateTime today = DateTime.now();
    DateTime checkDate = DateTime(today.year, today.month, today.day);

    // Check if streak is active (logged Today OR Yesterday)
    bool streakActive = sortedDates.contains(checkDate);
    if (!streakActive) {
       checkDate = checkDate.subtract(const Duration(days: 1)); // Check yesterday
       streakActive = sortedDates.contains(checkDate);
    }

    if (!streakActive) return 0; // Streak broken

    int count = 0;
    // Walk backwards day by day
    while (sortedDates.contains(checkDate)) {
      count++;
      checkDate = checkDate.subtract(const Duration(days: 1));
    }
    return count;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("Performance Analytics"),
        backgroundColor: Colors.indigo.shade900,
      ),
      body: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // --- STREAK BANNER ---
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  gradient: LinearGradient(colors: [Colors.orange.shade900, Colors.deepOrange]),
                  borderRadius: BorderRadius.circular(15),
                  boxShadow: [BoxShadow(color: Colors.orange.withOpacity(0.3), blurRadius: 10)]
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.local_fire_department, color: Colors.white, size: 40),
                    const SizedBox(width: 15),
                    Column(
                      children: [
                        Text("$_currentStreak DAY STREAK", style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold)),
                        const Text("Consistency is key.", style: TextStyle(color: Colors.white70, fontSize: 12)),
                      ],
                    )
                  ],
                ),
              ),
              const SizedBox(height: 25),

              // --- CALENDAR ---
              const Text("History Log", style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 10),
              Card(
                color: Colors.grey.shade900,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15)),
                child: Padding(
                  padding: const EdgeInsets.all(8.0),
                  child: TableCalendar(
                    firstDay: DateTime.utc(2024, 1, 1),
                    lastDay: DateTime.utc(2030, 12, 31),
                    focusedDay: _focusedDay,
                    calendarFormat: _calendarFormat,
                    
                    // Styles
                    headerStyle: const HeaderStyle(
                      titleCentered: true, 
                      formatButtonVisible: false,
                      titleTextStyle: TextStyle(color: Colors.white, fontSize: 16),
                      leftChevronIcon: Icon(Icons.chevron_left, color: Colors.white),
                      rightChevronIcon: Icon(Icons.chevron_right, color: Colors.white),
                    ),
                    calendarStyle: CalendarStyle(
                      defaultTextStyle: const TextStyle(color: Colors.white),
                      weekendTextStyle: const TextStyle(color: Colors.white60),
                      outsideTextStyle: const TextStyle(color: Colors.white24),
                      todayDecoration: BoxDecoration(color: Colors.indigo.withOpacity(0.5), shape: BoxShape.circle),
                      selectedDecoration: const BoxDecoration(color: Colors.indigo, shape: BoxShape.circle),
                      markerDecoration: const BoxDecoration(color: Colors.greenAccent, shape: BoxShape.circle),
                    ),
                    
                    // Logic
                    selectedDayPredicate: (day) => isSameDay(_selectedDay, day),
                    onDaySelected: (selectedDay, focusedDay) {
                      setState(() {
                        _selectedDay = selectedDay;
                        _focusedDay = focusedDay;
                      });
                      // Optional: Show details for selected day here
                    },
                    onFormatChanged: (format) => setState(() => _calendarFormat = format),
                    eventLoader: (day) {
                      DateTime clean = DateTime(day.year, day.month, day.day);
                      return _events[clean] ?? [];
                    },
                  ),
                ),
              ),

              const SizedBox(height: 25),

              // --- GRAPH 1: SLEEP ---
              const Text("Sleep Trends (Hours)", style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 15),
              _buildGraphContainer(
                _sleepSpots, 
                Colors.purpleAccent, 
                "No sleep data recorded yet."
              ),
              
              const SizedBox(height: 25),
              
              // --- GRAPH 2: REFLEX ---
              const Text("CNS Readiness (Reflex ms)", style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 15),
              _buildGraphContainer(
                _reflexSpots, 
                Colors.tealAccent, 
                "Play the Reflex Game to track this."
              ),
              
              const SizedBox(height: 50),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildGraphContainer(List<FlSpot> spots, Color color, String emptyMsg) {
    return Container(
      height: 220,
      padding: const EdgeInsets.fromLTRB(10, 25, 20, 10), 
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: color.withOpacity(0.3))
      ),
      child: spots.isEmpty 
        ? Center(child: Text(emptyMsg, style: const TextStyle(color: Colors.grey)))
        : LineChart(
            LineChartData(
              gridData: const FlGridData(show: false),
              titlesData: FlTitlesData(
                show: true,
                rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                bottomTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                leftTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true, 
                    getTitlesWidget: (val, meta) => Text(val.toInt().toString(), style: const TextStyle(color: Colors.grey, fontSize: 10)),
                    reservedSize: 30
                  )
                ),
              ),
              borderData: FlBorderData(show: false),
              minY: 0,
              lineBarsData: [
                LineChartBarData(
                  spots: spots,
                  isCurved: true,
                  color: color,
                  barWidth: 4,
                  isStrokeCapRound: true,
                  dotData: const FlDotData(show: true),
                  belowBarData: BarAreaData(show: true, color: color.withOpacity(0.15)),
                ),
              ],
            ),
          ),
    );
  }
}