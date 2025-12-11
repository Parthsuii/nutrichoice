import 'dart:io';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class MealLogScreen extends StatefulWidget {
  const MealLogScreen({super.key});

  @override
  State<MealLogScreen> createState() => _MealLogScreenState();
}

class _MealLogScreenState extends State<MealLogScreen> {
  final TextEditingController _textController = TextEditingController();
  List<Map<String, dynamic>> _mealHistory = [];
  bool _isAnalyzing = false;
  
  // Daily Totals
  int _totalCalories = 0;
  double _totalProtein = 0;
  double _totalCarbs = 0;
  double _totalFat = 0;

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  // --- DATA MANAGEMENT ---
  Future<void> _loadHistory() async {
    final prefs = await SharedPreferences.getInstance();
    String? logs = prefs.getString('meal_logs');
    if (logs != null) {
      try {
        List<dynamic> decoded = jsonDecode(logs);
        setState(() {
          _mealHistory = List<Map<String, dynamic>>.from(decoded);
          _calculateTotals();
        });
      } catch (e) {
        print("Error loading history: $e");
      }
    }
  }

  void _calculateTotals() {
    int cals = 0;
    double p = 0, c = 0, f = 0;
    for (var log in _mealHistory) {
      cals += (log['calories'] as num).toInt();
      if (log['macros'] != null) {
        p += _safeParse(log['macros']['protein']);
        c += _safeParse(log['macros']['carbs']);
        f += _safeParse(log['macros']['fat']);
      }
    }
    setState(() {
      _totalCalories = cals;
      _totalProtein = p;
      _totalCarbs = c;
      _totalFat = f;
    });
  }

  double _safeParse(dynamic value) {
    if (value == null) return 0.0;
    String clean = value.toString().replaceAll(RegExp(r'[^\d.]'), '');
    return double.tryParse(clean) ?? 0.0;
  }

  Future<void> _saveHistory() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('meal_logs', jsonEncode(_mealHistory));
    _calculateTotals();
  }

  // --- ACTIONS ---
  Future<void> _logTextMeal() async {
    if (_textController.text.isEmpty) return;
    setState(() => _isAnalyzing = true);

    try {
      final response = await http.post(
        Uri.parse('http://10.0.2.2:8000/log-meal'),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "meal_description": _textController.text,
          "time": DateTime.now().toString()
        }),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _addMealToHistory(data, _textController.text);
        _textController.clear();
      } else {
        throw Exception("Server Error");
      }
    } catch (e) {
      setState(() => _isAnalyzing = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Logging Failed: $e")));
    }
  }

  Future<void> _pickImage(ImageSource source) async {
    final picker = ImagePicker();
    final pickedFile = await picker.pickImage(source: source);
    if (pickedFile != null) {
      setState(() => _isAnalyzing = true);
      _analyzeFoodImage(File(pickedFile.path));
    }
  }

  Future<void> _analyzeFoodImage(File image) async {
    try {
      var request = http.MultipartRequest('POST', Uri.parse('http://10.0.2.2:8000/snap-meal'));
      request.files.add(await http.MultipartFile.fromPath('file', image.path));
      request.fields['user_goal'] = "Maintain";

      var response = await http.Response.fromStream(await request.send());

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _addMealToHistory(data, "Scanned Meal");
      } else {
        throw Exception("Server Error: ${response.statusCode}");
      }
    } catch (e) {
      setState(() => _isAnalyzing = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Scan Failed: $e")));
    }
  }

  void _addMealToHistory(Map<String, dynamic> data, String defaultTitle) {
    // Smart Title
    List<dynamic> ingredients = (data['ingredients'] as List?) ?? [];
    String displayTitle = defaultTitle;
    
    // If we have ingredients, use them as the title (e.g. "Chicken & Rice")
    if (ingredients.isNotEmpty && ingredients[0] != "List" && ingredients[0] != "all") {
      displayTitle = ingredients.take(2).join(" & ");
      if (displayTitle.length > 25) displayTitle = "${displayTitle.substring(0, 25)}...";
      displayTitle = displayTitle[0].toUpperCase() + displayTitle.substring(1);
    }

    Map<String, dynamic> newLog = {
      "time": DateTime.now().toString(),
      "description": displayTitle,
      "calories": data['estimated_calories'] ?? 0,
      "macros": data['macros'] ?? {"protein": "0g", "carbs": "0g", "fat": "0g"},
      "ingredients": ingredients,
      "advice": data['advice'] ?? "",
      "diet_fit": data['diet_fit'] ?? "Unknown" // [NEW] Capture Diet Fit status
    };

    setState(() {
      _mealHistory.insert(0, newLog);
      _isAnalyzing = false;
    });
    _saveHistory();
  }

  void _deleteLog(int index) {
    setState(() => _mealHistory.removeAt(index));
    _saveHistory();
  }

  void _showImageSourceSheet() {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.grey.shade900,
      builder: (ctx) => Wrap(
        children: [
          ListTile(
            leading: const Icon(Icons.camera_alt, color: Colors.tealAccent),
            title: const Text("Take Photo", style: TextStyle(color: Colors.white)),
            onTap: () { Navigator.pop(ctx); _pickImage(ImageSource.camera); },
          ),
          ListTile(
            leading: const Icon(Icons.image, color: Colors.blueAccent),
            title: const Text("Upload from Gallery", style: TextStyle(color: Colors.white)),
            onTap: () { Navigator.pop(ctx); _pickImage(ImageSource.gallery); },
          ),
        ],
      ),
    );
  }

  // --- UI BUILDER ---
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("Calorie Tracker"),
        backgroundColor: Colors.teal.shade900,
        actions: [
          IconButton(
            icon: const Icon(Icons.add_a_photo),
            onPressed: () => _showImageSourceSheet(),
          ),
          IconButton(
            icon: const Icon(Icons.delete_outline),
            onPressed: () {
              setState(() => _mealHistory.clear());
              _saveHistory();
            },
          )
        ],
      ),
      body: Column(
        children: [
          // 1. SUMMARY
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(color: Colors.grey.shade900, border: Border(bottom: BorderSide(color: Colors.teal.withOpacity(0.3)))),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text("Today's Fuel", style: TextStyle(color: Colors.white, fontSize: 16)),
                    Text("$_totalCalories kcal", style: const TextStyle(color: Colors.tealAccent, fontSize: 24, fontWeight: FontWeight.bold)),
                  ],
                ),
                const SizedBox(height: 15),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    _buildMacroStat("PRO", "${_totalProtein.round()}g", Colors.blue),
                    _buildMacroStat("CARB", "${_totalCarbs.round()}g", Colors.orange),
                    _buildMacroStat("FAT", "${_totalFat.round()}g", Colors.red),
                  ],
                )
              ],
            ),
          ),

          // 2. INPUT
          Container(
            padding: const EdgeInsets.all(16),
            color: Colors.black,
            child: Row(
              children: [
                Expanded(
                  child: Container(
                    decoration: BoxDecoration(color: Colors.grey.shade900, borderRadius: BorderRadius.circular(30)),
                    child: TextField(
                      controller: _textController,
                      style: const TextStyle(color: Colors.white),
                      decoration: const InputDecoration(
                        hintText: "Add meal (e.g. 2 Eggs)...",
                        hintStyle: TextStyle(color: Colors.grey),
                        border: InputBorder.none,
                        contentPadding: EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                      ),
                      onSubmitted: (_) => _logTextMeal(),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                _isAnalyzing
                    ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.teal))
                    : IconButton(icon: const Icon(Icons.camera_alt, color: Colors.tealAccent), onPressed: () => _showImageSourceSheet()),
                const SizedBox(width: 5),
                IconButton.filled(onPressed: _logTextMeal, icon: const Icon(Icons.arrow_upward), style: IconButton.styleFrom(backgroundColor: Colors.teal))
              ],
            ),
          ),

          // 3. LIST
          Expanded(
            child: _mealHistory.isEmpty
                ? Center(child: Text("No meals logged yet.", style: TextStyle(color: Colors.grey)))
                : ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _mealHistory.length,
                    itemBuilder: (context, index) {
                      final log = _mealHistory[index];
                      final calories = log['calories'] ?? 0;
                      final macros = log['macros'] ?? {"protein": "?", "carbs": "?", "fat": "?"};
                      final List<dynamic> rawIng = (log['ingredients'] is List) ? log['ingredients'] : [];
                      final String ingString = rawIng.join(", ");
                      final String advice = log['advice'] ?? "";
                      final String dietFit = log['diet_fit'] ?? "";

                      // Decide color based on diet fit
                      bool isGoodFit = dietFit.toLowerCase().contains("fits");
                      Color fitColor = isGoodFit ? Colors.greenAccent : Colors.orangeAccent;

                      return Dismissible(
                        key: Key(log['time'] ?? index.toString()),
                        direction: DismissDirection.endToStart,
                        background: Container(color: Colors.red, alignment: Alignment.centerRight, padding: const EdgeInsets.only(right: 20), child: const Icon(Icons.delete, color: Colors.white)),
                        onDismissed: (_) => _deleteLog(index),
                        child: Card(
                          color: Colors.grey.shade900,
                          margin: const EdgeInsets.only(bottom: 12),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15)),
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        log['description'] ?? "Meal",
                                        style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    
                                    // [NEW] DIET FIT BADGE
                                    if (dietFit.isNotEmpty && dietFit != "Unknown") ...[
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                        decoration: BoxDecoration(color: fitColor.withOpacity(0.2), borderRadius: BorderRadius.circular(4)),
                                        child: Text(isGoodFit ? "Fits ✅" : "Avoid ⚠️", style: TextStyle(color: fitColor, fontSize: 10, fontWeight: FontWeight.bold)),
                                      ),
                                      const SizedBox(width: 8),
                                    ],

                                    Text("$calories kcal", style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                                    const SizedBox(width: 10),
                                    InkWell(onTap: () => _deleteLog(index), child: const Icon(Icons.close, color: Colors.redAccent, size: 20)),
                                  ],
                                ),
                                const SizedBox(height: 10),
                                Row(
                                  children: [
                                    _buildSmallBadge("PRO ${macros['protein']}", Colors.blue),
                                    const SizedBox(width: 8),
                                    _buildSmallBadge("CARB ${macros['carbs']}", Colors.orange),
                                    const SizedBox(width: 8),
                                    _buildSmallBadge("FAT ${macros['fat']}", Colors.red),
                                  ],
                                ),
                                
                                // INGREDIENTS
                                if (ingString.isNotEmpty && ingString != "List, all, visible, ingredients") ...[
                                  const SizedBox(height: 10),
                                  Text("Includes: $ingString", style: const TextStyle(color: Colors.white70, fontSize: 13), maxLines: 2, overflow: TextOverflow.ellipsis),
                                ],

                                // ADVICE
                                if (advice.isNotEmpty) ...[
                                  const SizedBox(height: 8),
                                  Container(
                                    width: double.infinity,
                                    padding: const EdgeInsets.all(8),
                                    decoration: BoxDecoration(color: Colors.teal.withOpacity(0.15), borderRadius: BorderRadius.circular(8)),
                                    child: Row(
                                      children: [
                                        const Icon(Icons.auto_awesome, size: 14, color: Colors.tealAccent),
                                        const SizedBox(width: 6),
                                        Expanded(child: Text(advice, style: const TextStyle(color: Colors.tealAccent, fontSize: 12, fontStyle: FontStyle.italic))),
                                      ],
                                    ),
                                  )
                                ]
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildMacroStat(String label, String value, Color color) {
    return Column(children: [Text(value, style: TextStyle(color: color, fontSize: 18, fontWeight: FontWeight.bold)), Text(label, style: const TextStyle(color: Colors.grey, fontSize: 12))]);
  }

  Widget _buildSmallBadge(String text, Color color) {
    return Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4), decoration: BoxDecoration(color: color.withOpacity(0.2), borderRadius: BorderRadius.circular(5)), child: Text(text, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.bold)));
  }
}