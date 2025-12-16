import 'dart:io';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart'; // Required for MediaType
import 'package:shared_preferences/shared_preferences.dart';

class MealLogScreen extends StatefulWidget {
  const MealLogScreen({super.key});

  @override
  State<MealLogScreen> createState() => _MealLogScreenState();
}

class _MealLogScreenState extends State<MealLogScreen> {
  final TextEditingController _textController = TextEditingController();
  File? _image;
  bool _isAnalyzing = false;
  String _statusMessage = "Scan a meal to track calories."; // Feedback state
  List<Map<String, dynamic>> _loggedMeals = [];

  // Daily Totals
  int _totalCalories = 0;
  double _totalProtein = 0;
  double _totalCarbs = 0;
  double _totalFat = 0;

  @override
  void initState() {
    super.initState();
    _loadMeals();
  }

  Future<void> _loadMeals() async {
    final prefs = await SharedPreferences.getInstance();
    final String? logs = prefs.getString('meal_logs');
    if (logs != null) {
      setState(() {
        _loggedMeals = List<Map<String, dynamic>>.from(jsonDecode(logs));
        _calculateTotals();
      });
    }
  }

  Future<void> _saveMeals() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('meal_logs', jsonEncode(_loggedMeals));
    _calculateTotals();
  }

  void _calculateTotals() {
    int cals = 0;
    double p = 0, c = 0, f = 0;
    for (var meal in _loggedMeals) {
      cals += (meal['calories'] as num).toInt();
      final macros = meal['macros'] ?? {};
      p += (macros['protein'] as num?)?.toDouble() ?? 0;
      c += (macros['carbs'] as num?)?.toDouble() ?? 0;
      f += (macros['fat'] as num?)?.toDouble() ?? 0;
    }
    setState(() {
      _totalCalories = cals;
      _totalProtein = p;
      _totalCarbs = c;
      _totalFat = f;
    });
  }

  // --- 1. PICK IMAGE ---
  Future<void> _pickImage(ImageSource source) async {
    try {
      final picker = ImagePicker();
      final pickedFile = await picker.pickImage(source: source, imageQuality: 80);
      if (pickedFile != null) {
        setState(() => _image = File(pickedFile.path));
        _analyzeFood(imageFile: _image);
      }
    } catch (e) {
      _showSnack("Error: $e", Colors.red);
    }
  }

  // --- 2. ANALYZE FOOD (5-Model Strategy) ---
  Future<void> _analyzeFood({File? imageFile, String? textQuery}) async {
    setState(() {
      _isAnalyzing = true;
      // Inform user of the fallback chain
      _statusMessage = "Analyzing... (Gemini → Mistral → Moondream → Llama)";
    });

    try {
      var uri = Uri.parse('https://nutrichoice-xvpf.onrender.com/api/scan-food/');
      var request = http.MultipartRequest('POST', uri);

      if (imageFile != null) {
        request.files.add(await http.MultipartFile.fromPath(
          'image', 
          imageFile.path,
          contentType: MediaType('image', 'jpeg'),
        ));
      } else if (textQuery != null) {
        request.fields['food_name'] = textQuery;
      }

      // Extended timeout to 100s for fallback chain
      var streamedResponse = await request.send().timeout(
        const Duration(seconds: 100),
        onTimeout: () {
          throw Exception("Analysis timed out. 5 AI Agents attempted but were busy.");
        },
      );

      var response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final foodData = data['saved_data'];
        final source = data['source'] ?? "AI";

        setState(() {
          _loggedMeals.insert(0, {
            "name": foodData['food_name'],
            "calories": foodData['estimated_calories'],
            "macros": {
              "protein": foodData['protein'],
              "carbs": foodData['carbs'],
              "fat": foodData['fat']
            },
            "time": DateTime.now().toString(),
            "source": source
          });
          _statusMessage = "Identified: ${foodData['food_name']} ($source)";
          _image = null;
          _textController.clear();
        });
        await _saveMeals();
      } else {
        setState(() => _statusMessage = "Server Error: ${response.statusCode}");
      }
    } catch (e) {
      setState(() => _statusMessage = "Connection Error: $e");
    } finally {
      setState(() => _isAnalyzing = false);
    }
  }

  void _showSnack(String msg, Color color) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), backgroundColor: color));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("Calorie Tracker"),
        backgroundColor: Colors.teal.shade900,
        actions: [
          IconButton(
            icon: const Icon(Icons.delete_outline),
            onPressed: () async {
              setState(() => _loggedMeals.clear());
              await _saveMeals();
            },
          )
        ],
      ),
      body: Column(
        children: [
          // SUMMARY BOX
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
                ),
              ],
            ),
          ),

          // INPUT AREA
          Container(
            padding: const EdgeInsets.all(16),
            color: Colors.black,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Status Box
                if (_isAnalyzing || _statusMessage.contains("Identified") || _statusMessage.contains("Error"))
                  Container(
                    padding: const EdgeInsets.all(12),
                    margin: const EdgeInsets.only(bottom: 12),
                    decoration: BoxDecoration(
                      color: Colors.grey.shade900,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Colors.white24),
                    ),
                    child: Row(
                      children: [
                        Icon(Icons.auto_awesome, size: 16, color: _isAnalyzing ? Colors.tealAccent : Colors.grey),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _statusMessage,
                            style: TextStyle(color: _isAnalyzing ? Colors.tealAccent : Colors.grey, fontSize: 12),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),

                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _textController,
                        style: const TextStyle(color: Colors.white),
                        decoration: InputDecoration(
                          hintText: "Type food (e.g. 'Avocado Toast')",
                          hintStyle: const TextStyle(color: Colors.white38),
                          filled: true,
                          fillColor: Colors.grey.shade900,
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16),
                        ),
                        onSubmitted: (val) {
                          if (val.isNotEmpty) _analyzeFood(textQuery: val);
                        },
                      ),
                    ),
                    const SizedBox(width: 10),
                    IconButton.filled(
                      onPressed: () {
                        if (_textController.text.isNotEmpty) _analyzeFood(textQuery: _textController.text);
                      },
                      icon: const Icon(Icons.send),
                      style: IconButton.styleFrom(backgroundColor: Colors.teal),
                    )
                  ],
                ),
                const SizedBox(height: 15),
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton.icon(
                        onPressed: _isAnalyzing ? null : () => _pickImage(ImageSource.camera),
                        icon: const Icon(Icons.camera_alt),
                        label: const Text("Camera"),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.blue.shade900,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: ElevatedButton.icon(
                        onPressed: _isAnalyzing ? null : () => _pickImage(ImageSource.gallery),
                        icon: const Icon(Icons.photo_library),
                        label: const Text("Gallery"),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.purple.shade900,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),

          if (_isAnalyzing) const LinearProgressIndicator(color: Colors.tealAccent, backgroundColor: Colors.black),

          // FOOD LIST
          Expanded(
            child: _loggedMeals.isEmpty
                ? const Center(child: Text("No meals logged today.", style: TextStyle(color: Colors.grey)))
                : ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _loggedMeals.length,
                    itemBuilder: (context, index) {
                      final meal = _loggedMeals[index];
                      final macros = meal['macros'] ?? {};
                      return Card(
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
                                      meal['name'] ?? "Meal",
                                      style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                  Text("${meal['calories']} kcal", style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                                  const SizedBox(width: 10),
                                  IconButton(
                                    icon: const Icon(Icons.delete_outline, color: Colors.redAccent),
                                    onPressed: () {
                                      setState(() {
                                        _loggedMeals.removeAt(index);
                                      });
                                      _saveMeals();
                                    },
                                  ),
                                ],
                              ),
                              const SizedBox(height: 10),
                              Row(
                                children: [
                                  _buildSmallBadge("PRO ${macros['protein']}g", Colors.blue),
                                  const SizedBox(width: 8),
                                  _buildSmallBadge("CARB ${macros['carbs']}g", Colors.orange),
                                  const SizedBox(width: 8),
                                  _buildSmallBadge("FAT ${macros['fat']}g", Colors.red),
                                ],
                              ),
                              if (meal['source'] != null)
                                Padding(
                                  padding: const EdgeInsets.only(top: 8.0),
                                  child: Text("Source: ${meal['source']}", style: const TextStyle(color: Colors.grey, fontSize: 10)),
                                ),
                            ],
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
 