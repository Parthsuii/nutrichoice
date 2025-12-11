import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:table_calendar/table_calendar.dart';

class StatsScreen extends StatefulWidget {
  const StatsScreen({super.key});

  @override
  State<StatsScreen> createState() => _StatsScreenState();
}

class _StatsScreenState extends State<StatsScreen> {
  // Data Containers
  Map<DateTime, List<dynamic>> _events = {};
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
    
    // Temp variables to hold processed data
    Map<DateTime, List<dynamic>> events = {};
    List<FlSpot> sleepData = [];
    List<FlSpot> reflexData = [];
    List<DateTime> dates = [];

    // Parse History List
    for (int i = 0; i < historyRaw.length; i++) {
      var entry = jsonDecode(historyRaw[i]);
      DateTime date = DateTime.parse(entry['date']);
      
      // 1. Setup Calendar Event (normalize to midnight to match calendar logic)
      DateTime cleanDate = DateTime(date.year, date.month, date.day);
      if (events[cleanDate] == null) events[cleanDate] = [];
      events[cleanDate]!.add(entry);
      dates.add(cleanDate);

      // 2. Setup Graphs (Using Index as X-Axis for simple trend view)
      // Only graph last 7 entries to keep it readable
      if (i >= historyRaw.length - 7) {
        double xIndex = i.toDouble();
        sleepData.add(FlSpot(xIndex, (entry['sleep'] as num).toDouble()));
        reflexData.add(FlSpot(xIndex, (entry['reflex'] as num).toDouble()));
      }
    }

    // 3. Calculate Streak (Consecutive days backwards from today)
    int streak = 0;
    if (dates.isNotEmpty) {
      // Sort dates newest to oldest
      dates.sort((a, b) => b.compareTo(a)); 
      
      DateTime today = DateTime.now();
      DateTime checkDate = DateTime(today.year, today.month, today.day);
      
      // Check if we logged today
      bool streakAlive = dates.any((d) => isSameDay(d, checkDate));
      
      // If not logged today, check yesterday (streak acts as "frozen" for 24h)
      if (!streakAlive) {
        checkDate = checkDate.subtract(const Duration(days: 1));
        streakAlive = dates.any((d) => isSameDay(d, checkDate));
      }

      if (streakAlive) {
        streak++; // Count the first day found
        // Check previous days
        while (true) {
          checkDate = checkDate.subtract(const Duration(days: 1));
          if (dates.any((d) => isSameDay(d, checkDate))) {
            streak++;
          } else {
            break; // Streak broken
          }
        }
      }
    }

    setState(() {
      _events = events;
      _sleepSpots = sleepData;
      _reflexSpots = reflexData;
      _currentStreak = streak;
    });
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
      padding: const EdgeInsets.fromLTRB(10, 25, 20, 10), // Padding for labels
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