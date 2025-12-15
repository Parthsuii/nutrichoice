import 'dart:io';
import 'dart:math'; // For min function
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
// 1. ADD ML KIT IMPORT
import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';
import '../services/api_service.dart'; 

class MealLogScreen extends StatefulWidget {
  const MealLogScreen({super.key});

  @override
  State<MealLogScreen> createState() => _MealLogScreenState();
}

class _MealLogScreenState extends State<MealLogScreen> {
  List<Map<String, dynamic>> _mealHistory = [];
  bool _isLoading = false;
  
  // Daily Totals
  int _totalCalories = 0;
  double _totalProtein = 0;
  double _totalCarbs = 0;
  double _totalFat = 0;

  @override
  void initState() {
    super.initState();
    _fetchFoodHistory(); 
  }

  // --- 1. LOAD DATA ---
  Future<void> _fetchFoodHistory() async {
    setState(() => _isLoading = true);
    try {
      final foods = await ApiService.getFoods();
      
      setState(() {
        _mealHistory = foods.map((food) => {
          "id": food['id'], 
          "description": food['name'],
          "calories": food['calories'],
          "macros": {
            "protein": food['protein'],
            "carbs": food['carbs'] ?? 0,
            "fat": food['fat'] ?? 0,
          },
        }).toList().cast<Map<String, dynamic>>();
        
        // Show newest first
        _mealHistory = _mealHistory.toList(); 
        _calculateTotals();
        _isLoading = false;
      });
    } catch (e) {
      print("Offline or Error: $e");
      setState(() => _isLoading = false);
    }
  }

  // --- 2. DELETE FUNCTION ---
  Future<void> _deleteMeal(int id, int index) async {
    setState(() {
      _mealHistory.removeAt(index);
      _calculateTotals();
    });

    try {
      await ApiService.deleteFood(id);
      if(mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Meal deleted."), duration: Duration(seconds: 1)),
        );
      }
    } catch (e) {
      print("Could not delete from server: $e");
    }
  }

  void _calculateTotals() {
    int cals = 0;
    double p = 0, c = 0, f = 0;
    for (var log in _mealHistory) {
      cals += (log['calories'] as num).toInt();
      if (log['macros'] != null) {
        p += (log['macros']['protein'] as num).toDouble();
        c += (log['macros']['carbs'] as num).toDouble();
        f += (log['macros']['fat'] as num).toDouble();
      }
    }
    setState(() {
      _totalCalories = cals;
      _totalProtein = p;
      _totalCarbs = c;
      _totalFat = f;
    });
  }

  // --- 3. HYBRID SCANNER (OCR + VISION) ---
  Future<void> _pickImage(ImageSource source) async {
    final picker = ImagePicker();
    final pickedFile = await picker.pickImage(source: source);
    
    if (pickedFile != null) {
      setState(() => _isLoading = true);
      
      try {
        final File imageFile = File(pickedFile.path);
        String? extractedText;

        // PHASE A: ON-DEVICE OCR (Instant & Free)
        try {
          print("⚡ Running On-Device OCR...");
          final inputImage = InputImage.fromFile(imageFile);
          final textRecognizer = TextRecognizer(script: TextRecognitionScript.latin);
          final RecognizedText recognizedText = await textRecognizer.processImage(inputImage);
          
          String rawText = recognizedText.text.trim();
          textRecognizer.close(); // Clean up

          // HEURISTIC: Only use text if it looks like a real label (>4 chars)
          if (rawText.length > 4) {
             // Clean newlines to make it a single search query
             extractedText = rawText.replaceAll("\n", " "); 
             print("⚡ ML KIT FOUND: $extractedText");
             
             if(mounted) {
               ScaffoldMessenger.of(context).showSnackBar(
                 SnackBar(content: Text("Reading Label: '${extractedText!.substring(0, min(20, extractedText.length))}...'"), backgroundColor: Colors.teal),
               );
             }
          }
        } catch (e) {
          print("⚠️ OCR Failed (Falling back to Vision AI): $e");
        }

        // PHASE B: CALL BACKEND (Smart Scan)
        // We pass 'extractedText'. 
        // If it exists, backend uses Text Search (0 Cost).
        // If null, backend uses Image Vision (1 Call).
        final response = await ApiService.scanFoodSmart(imageFile, extractedText);

        if (response['saved_data'] != null) {
           final foodData = response['saved_data'];
           
           // Insert new meal at top
           setState(() {
             _mealHistory.insert(0, {
                "id": foodData['id'] ?? 0, 
                "description": foodData['food_name'],
                "calories": foodData['estimated_calories'],
                "macros": {
                  "protein": foodData['protein'],
                  "carbs": foodData['carbs'],
                  "fat": foodData['fat'],
                }
             });
             _calculateTotals();
           });
        }

      } catch (e) {
        if(mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Scan Failed: $e")));
        }
      } finally {
        if(mounted) setState(() => _isLoading = false);
      }
    }
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("Calorie Tracker"),
        backgroundColor: Colors.teal.shade900,
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _fetchFoodHistory),
          IconButton(icon: const Icon(Icons.add_a_photo), onPressed: () => _showImageSourceSheet()),
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
                )
              ],
            ),
          ),

          // FOOD LIST
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator(color: Colors.teal))
                : _mealHistory.isEmpty
                    ? const Center(child: Text("No meals logged yet.", style: TextStyle(color: Colors.grey)))
                    : ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: _mealHistory.length,
                        itemBuilder: (context, index) {
                          final log = _mealHistory[index];
                          final macros = log['macros'];
                          final int id = log['id'] ?? 0;

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
                                          log['description'] ?? "Meal",
                                          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                      Text("${log['calories']} kcal", style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                                      const SizedBox(width: 10),
                                      IconButton(
                                        icon: const Icon(Icons.delete_outline, color: Colors.redAccent),
                                        onPressed: () => _deleteMeal(id, index),
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