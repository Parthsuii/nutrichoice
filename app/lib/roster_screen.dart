import 'dart:io';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart'; 
import 'package:image_picker/image_picker.dart';
import 'package:http/http.dart' as http;
import 'package:device_calendar/device_calendar.dart';
import 'package:shared_preferences/shared_preferences.dart';

class RosterScreen extends StatefulWidget {
  final String? initialImagePath;
  const RosterScreen({super.key, this.initialImagePath});

  @override
  State<RosterScreen> createState() => _RosterScreenState();
}

class _RosterScreenState extends State<RosterScreen> {
  int _selectedMode = 0; // 0=Manual, 1=Scan, 2=Calendar
  
  Map<String, List<dynamic>> _weeklySchedule = {};
  bool _isScanning = false;
  bool _hasUnsavedChanges = false;
  File? _image;

  final DeviceCalendarPlugin _deviceCalendarPlugin = DeviceCalendarPlugin();

  // Controllers
  final _dayController = TextEditingController(text: "Monday");
  final _timeController = TextEditingController();
  final _eventController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadSavedSchedule();
    if (widget.initialImagePath != null) {
      _uploadImageForAnalysis(File(widget.initialImagePath!));
    }
  }

  // --- HELPER: NORMALIZE WEEK (Fixes "Empty Screen" Bug) ---
  Map<String, List<dynamic>> _normalizeWeek(Map<String, List<dynamic>> input) {
    const days = [
      "Monday",
      "Tuesday",
      "Wednesday",
      "Thursday",
      "Friday",
      "Saturday",
      "Sunday"
    ];

    final normalized = <String, List<dynamic>>{};
    for (final d in days) {
      normalized[d] = input[d] ?? [];
    }
    return normalized;
  }

  // --- STORAGE ---
  Future<void> _loadSavedSchedule() async {
    final prefs = await SharedPreferences.getInstance();
    String? savedData = prefs.getString('weekly_schedule');
    if (savedData != null) {
      setState(() {
        final rawMap = Map<String, List<dynamic>>.from(
          jsonDecode(savedData).map((key, value) => MapEntry(key, List<dynamic>.from(value))),
        );
        _weeklySchedule = _normalizeWeek(rawMap);
        _hasUnsavedChanges = false;
      });
    } else {
        _weeklySchedule = _normalizeWeek({});
    }
  }

  Future<void> _saveSchedule() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('weekly_schedule', jsonEncode(_weeklySchedule));
    
    StringBuffer buffer = StringBuffer();
    _weeklySchedule.forEach((day, events) {
      buffer.write("$day: ");
      for (var e in events) {
        buffer.write("${e['event']} at ${e['time']}, ");
      }
      buffer.write(". ");
    });
    await prefs.setString('saved_schedule_text', buffer.toString());

    setState(() => _hasUnsavedChanges = false);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("✅ Saved & Synced!"), backgroundColor: Colors.green));
  }

  // --- MODE 1: MANUAL ENTRY ---
  void _addManualEntry() {
    if (_timeController.text.isEmpty || _eventController.text.isEmpty) {
      _showError("Please enter Time and Event");
      return;
    }
    String day = _dayController.text;
    setState(() {
      if (_weeklySchedule[day] == null) _weeklySchedule[day] = [];
      _weeklySchedule[day]!.add({"time": _timeController.text, "event": _eventController.text});
      _weeklySchedule[day]!.sort((a, b) => a['time'].compareTo(b['time'])); 
      _hasUnsavedChanges = true;
    });
    _timeController.clear();
    _eventController.clear();
    _showSuccess("Event added to $day");
  }

  // --- MODE 2: SCAN IMAGE ---
  Future<void> _pickImage() async {
    try {
      final picker = ImagePicker();
      final pickedFile = await picker.pickImage(source: ImageSource.gallery);
      
      if (pickedFile != null) {
        setState(() => _image = File(pickedFile.path));
        _uploadImageForAnalysis(_image!);
      }
    } on PlatformException catch (e) {
      if (e.code == 'already_active') {
        print("Gallery already open");
      } else {
        _showError("Gallery Error: ${e.message}");
      }
    } catch (e) {
      _showError("Error picking image: $e");
    }
  }

  // --- UPDATED FUNCTION: CORRECT API URL & SAFE PARSING ---
  Future<void> _uploadImageForAnalysis(File imageFile) async {
    setState(() => _isScanning = true);
    try {
      // ✅ UPDATED URL: Added '/api/' to match your backend route
      var uri = Uri.parse('https://nutrichoice-xvpf.onrender.com/api/analyze-roster/');
      
      var request = http.MultipartRequest('POST', uri);

      request.headers.addAll({
        'User-Agent': 'BioSyncApp/1.0', 
        'Accept': 'application/json',
      });

      request.files.add(await http.MultipartFile.fromPath('file', imageFile.path));
      
      print("Sending clean request to $uri...");
      var response = await http.Response.fromStream(await request.send());

      print("Response: ${response.statusCode}");
      print("Body: ${response.body}");

      if (response.statusCode == 200) {
        final dynamic rawData = jsonDecode(response.body);
        Map<String, dynamic> scheduleData = {};

        if (rawData is Map<String, dynamic>) {
          if (rawData.containsKey('weekly_schedule') && rawData['weekly_schedule'] is Map) {
            scheduleData = rawData['weekly_schedule'];
          } else {
            scheduleData = rawData;
          }
        }

        Map<String, List<dynamic>> parsedSchedule = {};
        scheduleData.forEach((key, value) {
          if (value is List) {
            parsedSchedule[key] = List<dynamic>.from(value);
          }
        });

        if (parsedSchedule.isNotEmpty) {
          setState(() {
            final normalizedData = _normalizeWeek(parsedSchedule);

            if (_weeklySchedule.isEmpty) {
                 _weeklySchedule = _normalizeWeek({});
            }
            _weeklySchedule.addAll(normalizedData);
            
            _selectedMode = 0; 
            _hasUnsavedChanges = true;
          });
          
          await _saveSchedule();
          _showSuccess("Schedule Updated!");
        } else {
          _showError("AI returned empty schedule.");
        }
      } else {
        print("Server Error: ${response.body}");
        _showError("Server Blocked Request (${response.statusCode})");
      }
    } catch (e) {
      _showError("Connection Error: $e");
    } finally {
      setState(() => _isScanning = false);
    }
  }

  // --- MODE 3: CALENDAR ---
  Future<void> _importFromCalendar() async {
    var permissions = await _deviceCalendarPlugin.requestPermissions();
    if (!permissions.isSuccess || !permissions.data!) {
      _showError("Calendar Permission Denied");
      return;
    }
    final calendarsResult = await _deviceCalendarPlugin.retrieveCalendars();
    if (calendarsResult.data == null || calendarsResult.data!.isEmpty) {
      _showError("No calendars found.");
      return;
    }
    if (!mounted) return;
    await showDialog(
      context: context,
      builder: (ctx) => SimpleDialog(
        title: const Text("Select Source Calendar"),
        children: calendarsResult.data!.map((c) {
          return SimpleDialogOption(
            child: Padding(padding: const EdgeInsets.symmetric(vertical: 8.0), child: Text(c.name ?? "Unknown")),
            onPressed: () { Navigator.pop(ctx); _fetchEvents(c.id); },
          );
        }).toList(),
      ),
    );
  }

  Future<void> _fetchEvents(String? calendarId) async {
    if (calendarId == null) return;
    setState(() => _isScanning = true);

    final now = DateTime.now();
    final end = now.add(const Duration(days: 7)); 

    final eventsResult = await _deviceCalendarPlugin.retrieveEvents(
      calendarId,
      RetrieveEventsParams(startDate: now, endDate: end),
    );

    if (eventsResult.data != null && eventsResult.data!.isNotEmpty) {
      Map<String, List<dynamic>> newEvents = {};
      List<String> days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

      for (var event in eventsResult.data!) {
        if (event.start != null) {
          String dayName = days[event.start!.weekday - 1]; 
          String timeString = "${event.start!.hour.toString().padLeft(2, '0')}:${event.start!.minute.toString().padLeft(2, '0')}";
          
          if (newEvents[dayName] == null) newEvents[dayName] = [];
          newEvents[dayName]!.add({ "time": timeString, "event": event.title ?? "Busy" });
        }
      }

      setState(() {
        if (_weeklySchedule.isEmpty) _weeklySchedule = _normalizeWeek({});
        
        newEvents.forEach((key, events) {
            if (_weeklySchedule[key] == null) _weeklySchedule[key] = [];
            _weeklySchedule[key]!.addAll(events);
        });
        
        _selectedMode = 0; 
        _hasUnsavedChanges = true;
      });
      await _saveSchedule(); 
      _showSuccess("Imported ${eventsResult.data!.length} events");
      
    } else {
      _showError("No upcoming events found.");
    }
    setState(() => _isScanning = false);
  }

  // --- EDITING ---
  void _editEvent(String day, int index, String key, String newVal) {
    setState(() {
      _weeklySchedule[day]![index][key] = newVal;
      _hasUnsavedChanges = true;
    });
  }

  void _deleteEvent(String day, int index) {
    setState(() {
      _weeklySchedule[day]?.removeAt(index);
      _hasUnsavedChanges = true;
    });
  }

  void _clearAll() async {
    setState(() {
      _weeklySchedule = _normalizeWeek({});
      _hasUnsavedChanges = false;
    });
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('weekly_schedule');
    await prefs.remove('saved_schedule_text');
    _showSuccess("Schedule cleared.");
  }

  void _showError(String msg) {
    if(!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), backgroundColor: Colors.red));
  }
  
  void _showSuccess(String msg) {
    if(!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), backgroundColor: Colors.green));
  }

  @override
  Widget build(BuildContext context) {
    final daysOrder = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
    
    final keys = _weeklySchedule.keys.toList();
    
    final sortedKeys = keys
      ..sort((a, b) => daysOrder.indexOf(a).compareTo(daysOrder.indexOf(b)));

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("Roster & Schedule"),
        backgroundColor: Colors.teal.shade900,
        actions: [
          IconButton(icon: const Icon(Icons.delete_outline), onPressed: _clearAll, tooltip: "Clear All")
        ],
      ),
      floatingActionButton: _hasUnsavedChanges 
        ? FloatingActionButton.extended(
            onPressed: _saveSchedule,
            backgroundColor: Colors.greenAccent,
            foregroundColor: Colors.black,
            icon: const Icon(Icons.sync),
            label: const Text("Sync Changes"),
          )
        : null,
      
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(vertical: 10),
            color: Colors.grey.shade900,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                _buildModeBtn(0, Icons.edit, "Edit / Add"),
                _buildModeBtn(1, Icons.camera_alt, "Scan Image"),
                _buildModeBtn(2, Icons.calendar_month, "Import Cal"),
              ],
            ),
          ),

          AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            color: Colors.grey.shade900,
            child: Column(
              children: [
                if (_selectedMode == 0) _buildManualInput(),
                if (_selectedMode == 1) _buildScanInput(),
                if (_selectedMode == 2) _buildCalendarInput(),
              ],
            ),
          ),

          if (_hasUnsavedChanges)
            Container(
              width: double.infinity,
              color: Colors.orange.shade900,
              padding: const EdgeInsets.all(8),
              child: const Text("⚠️ Unsaved Changes - Tap Sync button to apply", textAlign: TextAlign.center, style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),

          const Divider(height: 1, color: Colors.grey),

          Expanded(
            child: _weeklySchedule.isEmpty 
              ? const Center(child: Text("Schedule Empty", style: TextStyle(color: Colors.grey)))
              : ListView.builder(
                  padding: const EdgeInsets.only(bottom: 80),
                  itemCount: sortedKeys.length,
                  itemBuilder: (context, index) {
                    String day = sortedKeys[index];
                    List events = _weeklySchedule[day] ?? [];
                    
                    return Card(
                      color: Colors.grey.shade800,
                      margin: const EdgeInsets.only(bottom: 10, left: 10, right: 10, top: 5),
                      child: ExpansionTile(
                        initiallyExpanded: events.isNotEmpty, 
                        title: Text(day, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                        children: events.isEmpty 
                            ? [const Padding(padding: EdgeInsets.all(16.0), child: Text("No classes scheduled", style: TextStyle(color: Colors.white38)))]
                            : events.asMap().entries.map((entry) {
                                int idx = entry.key;
                                Map e = entry.value;
                                return ListTile(
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 10),
                                  leading: const Icon(Icons.event_note, color: Colors.tealAccent, size: 20),
                                  title: TextFormField(
                                    initialValue: e['event'],
                                    style: const TextStyle(color: Colors.white),
                                    decoration: const InputDecoration(border: InputBorder.none, hintText: "Event Name"),
                                    onChanged: (val) => _editEvent(day, idx, 'event', val),
                                  ),
                                  subtitle: TextFormField(
                                    initialValue: e['time'],
                                    style: const TextStyle(color: Colors.white54),
                                    decoration: const InputDecoration(border: InputBorder.none, hintText: "Time"),
                                    onChanged: (val) => _editEvent(day, idx, 'time', val),
                                  ),
                                  trailing: IconButton(
                                    icon: const Icon(Icons.close, color: Colors.redAccent, size: 18),
                                    onPressed: () => _deleteEvent(day, idx),
                                  ),
                                );
                              }).toList(),
                      ),
                    );
                  },
                ),
          ),
        ],
      ),
    );
  }

  Widget _buildModeBtn(int index, IconData icon, String label) {
    bool isSelected = _selectedMode == index;
    return GestureDetector(
      onTap: () => setState(() => _selectedMode = index),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? Colors.teal : Colors.transparent,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: isSelected ? Colors.teal : Colors.white24)
        ),
        child: Row(
          children: [
            Icon(icon, color: Colors.white, size: 16),
            const SizedBox(width: 6),
            Text(label, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ],
        ),
      ),
    );
  }

  Widget _buildManualInput() {
    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text("Add Missing Event:", style: TextStyle(color: Colors.tealAccent, fontSize: 12, fontWeight: FontWeight.bold)),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                flex: 2,
                child: DropdownButtonFormField<String>(
                  value: _dayController.text.isNotEmpty ? _dayController.text : "Monday", 
                  dropdownColor: Colors.grey.shade800,
                  items: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                      .map((d) => DropdownMenuItem(value: d, child: Text(d, style: const TextStyle(color: Colors.white)))).toList(),
                  onChanged: (val) => setState(() => _dayController.text = val!),
                  decoration: const InputDecoration(filled: true, fillColor: Colors.black, isDense: true, contentPadding: EdgeInsets.all(12)),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                flex: 3,
                child: TextField(
                  controller: _timeController,
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(hintText: "Time (e.g. 2 PM)", filled: true, fillColor: Colors.black, isDense: true, contentPadding: EdgeInsets.all(12)),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _eventController,
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(hintText: "Event Name (e.g. Math Class)", filled: true, fillColor: Colors.black, isDense: true, contentPadding: EdgeInsets.all(12)),
                ),
              ),
              const SizedBox(width: 10),
              IconButton.filled(
                onPressed: _addManualEntry, 
                icon: const Icon(Icons.add), 
                style: IconButton.styleFrom(backgroundColor: Colors.teal),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildScanInput() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          if (_image != null) SizedBox(height: 100, child: Image.file(_image!)),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: _isScanning ? null : _pickImage,
              icon: _isScanning 
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2)) 
                  : const Icon(Icons.upload_file),
              label: Text(_isScanning ? "AI is Analyzing..." : "Upload Timetable Image"),
              style: ElevatedButton.styleFrom(backgroundColor: Colors.blue, padding: const EdgeInsets.all(16)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCalendarInput() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: ElevatedButton.icon(
        onPressed: _importFromCalendar,
        icon: const Icon(Icons.download),
        label: const Text("Import Next 7 Days from Calendar"),
        style: ElevatedButton.styleFrom(backgroundColor: Colors.purple, padding: const EdgeInsets.all(16)),
      ),
    );
  }
}