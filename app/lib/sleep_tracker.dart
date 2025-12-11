import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart'; // REQUIRED: For saving data

class SleepTracker extends StatefulWidget {
  const SleepTracker({super.key});

  @override
  State<SleepTracker> createState() => _SleepTrackerState();
}

class _SleepTrackerState extends State<SleepTracker> {
  TimeOfDay _bedTime = const TimeOfDay(hour: 23, minute: 0);
  TimeOfDay _wakeTime = const TimeOfDay(hour: 7, minute: 0);
  bool _watchedTV = false; // The Honesty Buffer
  String _result = "";

  @override
  void initState() {
    super.initState();
    _loadSavedData(); // Load previous settings when screen opens
  }

  // Load last saved buffer preference
  Future<void> _loadSavedData() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _watchedTV = prefs.getBool('honesty_buffer') ?? false;
    });
  }

  Future<void> _calculateAndSave() async {
    // 1. Calculate Raw Sleep Duration
    double start = _bedTime.hour + _bedTime.minute / 60.0;
    double end = _wakeTime.hour + _wakeTime.minute / 60.0;

    // Handle overnight calculation (e.g. 11 PM to 7 AM)
    if (end < start) end += 24;

    double rawSleep = end - start;
    double recoveryCredit = rawSleep;

    // 2. Apply Honesty Buffer (Engine 1 Logic)
    if (_watchedTV) {
      recoveryCredit -= 1.5; // Penalty: -90 mins for blue light
    }

    // 3. Save Data for Reflex Game (Engine 1 Integration)
    final prefs = await SharedPreferences.getInstance();
    await prefs.setDouble('last_sleep_hours', recoveryCredit);
    await prefs.setBool('honesty_buffer', _watchedTV);

    // 4. Show Result
    setState(() {
      _result =
          "Raw Sleep: ${rawSleep.toStringAsFixed(1)} hrs\n"
          "Honesty Penalty: ${_watchedTV ? '-1.5 hrs' : 'None'}\n"
          "BioSync Credit: ${recoveryCredit.toStringAsFixed(1)} hrs";
    });

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text("Recovery Data Synced with BioSync Core"),
          backgroundColor: Colors.teal,
          duration: Duration(seconds: 2),
        ),
      );
    }
  }

  Future<void> _pickTime(bool isBedTime) async {
    final TimeOfDay? picked = await showTimePicker(
      context: context,
      initialTime: isBedTime ? _bedTime : _wakeTime,
    );
    if (picked != null) {
      setState(() {
        if (isBedTime) {
          _bedTime = picked;
        } else {
          _wakeTime = picked;
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("Recovery Triangulation"),
        backgroundColor: Colors.teal.shade900,
      ),
      body: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              "Logic: Phone Lock Duration",
              style: TextStyle(color: Colors.grey, fontStyle: FontStyle.italic),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),

            _buildTimeCard("Bed Time", _bedTime, true),
            const SizedBox(height: 10),
            _buildTimeCard("Wake Time", _wakeTime, false),
            const SizedBox(height: 20),

            // The Honesty Buffer Toggle
            Container(
              decoration: BoxDecoration(
                color: Colors.red.shade900.withOpacity(0.2),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.red.shade900),
              ),
              child: SwitchListTile(
                title: Text(
                  "Honesty Buffer",
                  style: GoogleFonts.roboto(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                subtitle: const Text(
                  "Did you use phone/TV in bed?",
                  style: TextStyle(color: Colors.white70),
                ),
                value: _watchedTV,
                activeThumbColor: Colors.redAccent,
                onChanged: (val) => setState(() => _watchedTV = val),
              ),
            ),

            const Spacer(),

            // Result Box
            if (_result.isNotEmpty)
              Container(
                padding: const EdgeInsets.all(15),
                margin: const EdgeInsets.only(bottom: 20),
                decoration: BoxDecoration(
                  color: Colors.grey.shade900,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  _result,
                  textAlign: TextAlign.center,
                  style: GoogleFonts.robotoMono(
                    color: Colors.tealAccent,
                    fontSize: 16,
                  ),
                ),
              ),

            ElevatedButton(
              onPressed: _calculateAndSave,
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.teal,
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              child: const Text(
                "Calculate & Sync",
                style: TextStyle(fontSize: 18, color: Colors.white),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTimeCard(String label, TimeOfDay time, bool isBed) {
    return InkWell(
      onTap: () => _pickTime(isBed),
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              label,
              style: const TextStyle(color: Colors.grey, fontSize: 16),
            ),
            Text(
              time.format(context),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 24,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
