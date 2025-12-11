import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

class SmartMealPlannerScreen extends StatefulWidget {
  const SmartMealPlannerScreen({super.key});

  @override
  State<SmartMealPlannerScreen> createState() => _SmartMealPlannerScreenState();
}

class _SmartMealPlannerScreenState extends State<SmartMealPlannerScreen> {
  bool _isLoading = false;
  List<dynamic> _meals = [];
  String _chefAnalysis = "";

  String _userGoal = "Maintain";
  int _dailyCalories = 2000;

  // CONTEXT VARIABLES
  String _selectedContext = "Standard Day";
  final List<String> _contextOptions = [
    "Standard Day",
    "Heavy Lifting 🏋️",
    "Rest / Recovery 🛌",
    "Exam / High Focus 🧠",
    "Cardio Day 🏃",
  ];

  final TextEditingController _ingredientController = TextEditingController();
  final List<String> _availableIngredients = [];

  @override
  void initState() {
    super.initState();
    _loadOrGeneratePlan();
  }

  // --- 1. SMART LOAD LOGIC ---
  Future<void> _loadOrGeneratePlan() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;

    String todayDate = DateTime.now().toIso8601String().split('T')[0];
    String? savedDate = prefs.getString('saved_plan_date');
    String? savedMeals = prefs.getString('saved_plan_json');

    if (savedDate == todayDate && savedMeals != null) {
      List<dynamic> loadedMeals = jsonDecode(savedMeals);
      bool isOldVersion = loadedMeals.isNotEmpty && (loadedMeals[0]['recipe'] == null);

      if (isOldVersion) {
        _initPlannerLogic();
      } else {
        setState(() {
          _meals = loadedMeals;
          _selectedContext = prefs.getString('saved_plan_context') ?? "Standard Day";
          _chefAnalysis = prefs.getString('saved_plan_analysis') ?? "";
          _isLoading = false;
        });
        _userGoal = prefs.getString('user_goal') ?? "Maintain";
        _dailyCalories = prefs.getInt('daily_calorie_target') ?? 2000;
      }
    } else {
      _initPlannerLogic();
    }
  }

  Future<void> _initPlannerLogic() async {
    final prefs = await SharedPreferences.getInstance();
    int reflexScore = prefs.getInt('last_reflex_score') ?? 0;
    double sleepHours = prefs.getDouble('last_sleep_hours') ?? 7.0;
    String scheduleText = prefs.getString('saved_schedule_text') ?? "";

    String detectedContext = "Standard Day";
    if (sleepHours < 6.0 || (reflexScore > 350 && reflexScore > 0)) {
      detectedContext = "Rest / Recovery 🛌";
    } else if (scheduleText.toLowerCase().contains("exam")) {
      detectedContext = "Exam / High Focus 🧠";
    } else if (reflexScore > 0 && reflexScore < 250) {
      detectedContext = "Heavy Lifting 🏋️";
    }

    if (!mounted) return;

    setState(() {
      _userGoal = prefs.getString('user_goal') ?? "Maintain";
      int dynamicCal = prefs.getInt('dynamic_calorie_target') ?? 0;
      int baseCal = prefs.getInt('daily_calorie_target') ?? 2000;
      _dailyCalories = (dynamicCal > baseCal) ? dynamicCal : baseCal;
      _selectedContext = detectedContext;
    });

    _generateFullPlan();
  }

  // --- 2. GENERATE NEW PLAN ---
  Future<void> _generateFullPlan() async {
    setState(() => _isLoading = true);
    
    try {
      final prefs = await SharedPreferences.getInstance();
      List<String> soreMuscles = prefs.getStringList('sore_muscles') ?? [];
      
      String finalContext = _selectedContext;
      if (soreMuscles.isNotEmpty) {
        finalContext += ". USER SORE IN: ${soreMuscles.join(', ')}. ADD ANTI-INFLAMMATORY FOODS.";
      }

      final response = await http.post(
        Uri.parse('http://10.0.2.2:8000/generate-meal-plan'),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "user_goal": _userGoal,
          "daily_calories": _dailyCalories,
          "dietary_preference": "Indian",
          "available_ingredients": _availableIngredients,
          "activity_context": finalContext,
        }),
      );

      if (!mounted) return;

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data['meals'] != null) {
          setState(() {
            _meals = data['meals'];
            _chefAnalysis = data['analysis'] ?? "Here is your plan.";
            _isLoading = false;
          });

          String todayDate = DateTime.now().toIso8601String().split('T')[0];
          await prefs.setString('saved_plan_date', todayDate);
          await prefs.setString('saved_plan_json', jsonEncode(_meals));
          await prefs.setString('saved_plan_context', _selectedContext);
          await prefs.setString('saved_plan_analysis', _chefAnalysis);
        }
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Error: $e")));
      setState(() => _isLoading = false);
    }
  }

  // --- SWAP MEAL LOGIC ---
  Future<void> _swapSingleMeal(int index) async {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Swapping meal...")));
    try {
      final response = await http.post(
        Uri.parse('http://10.0.2.2:8000/swap-meal'),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "user_goal": _userGoal,
          "daily_calories": _dailyCalories, 
          "dietary_preference": "Indian",
          "available_ingredients": _availableIngredients,
          "activity_context": _selectedContext,
        }),
      );

      if (!mounted) return;

      if (response.statusCode == 200) {
        final newMeal = jsonDecode(response.body);
        setState(() {
          newMeal['type'] = _meals[index]['type']; // Maintain meal type (e.g., Breakfast)
          _meals[index] = newMeal;
        });
        
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('saved_plan_json', jsonEncode(_meals));
      } else {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Server rejected request (422)")));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Swap failed: $e")));
    }
  }

  Future<void> _checkPrice(String ingredient) async {
    String query = ingredient.replaceAll(" ", "%20");
    Uri url = Uri.parse("https://blinkit.com/s/?q=$query");
    if (!await launchUrl(url, mode: LaunchMode.externalApplication)) {
      if(!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Could not open store.")));
    }
  }

  // --- UI HELPERS ---
  void _addIngredient() {
    String text = _ingredientController.text.trim();
    if (text.isNotEmpty && !_availableIngredients.contains(text)) {
      setState(() {
        _availableIngredients.add(text);
        _ingredientController.clear();
      });
    }
  }

  void _removeIngredient(String item) {
    setState(() => _availableIngredients.remove(item));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("Context Chef"),
        backgroundColor: Colors.teal.shade900,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Regenerating...")));
              _generateFullPlan();
            },
          )
        ],
      ),
      body: Column(
        children: [
          // CONTEXT & PANTRY SECTION
          Container(
            padding: const EdgeInsets.all(16),
            color: Colors.grey.shade900,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                DropdownButtonFormField<String>(
                  initialValue: _selectedContext,
                  dropdownColor: Colors.grey.shade800,
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                  decoration: const InputDecoration(
                    labelText: "Bio-Sync Mode", 
                    labelStyle: TextStyle(color: Colors.teal),
                    border: OutlineInputBorder()
                  ),
                  items: _contextOptions.map((v) => DropdownMenuItem(value: v, child: Text(v))).toList(),
                  onChanged: (val) {
                    setState(() => _selectedContext = val!);
                    _generateFullPlan();
                  },
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _ingredientController,
                        style: const TextStyle(color: Colors.white),
                        decoration: const InputDecoration(
                          hintText: "Add pantry item (e.g. Eggs)",
                          hintStyle: TextStyle(color: Colors.grey),
                          isDense: true,
                        ),
                        onSubmitted: (_) => _addIngredient(),
                      ),
                    ),
                    IconButton(icon: const Icon(Icons.add, color: Colors.teal), onPressed: _addIngredient),
                  ],
                ),
                if (_availableIngredients.isNotEmpty)
                  Wrap(
                    spacing: 8,
                    children: _availableIngredients.map((item) => Chip(
                      label: Text(item),
                      onDeleted: () => _removeIngredient(item),
                      backgroundColor: Colors.teal.withOpacity(0.2),
                      labelStyle: const TextStyle(color: Colors.white),
                      deleteIconColor: Colors.redAccent,
                    )).toList(),
                  ),
              ],
            ),
          ),

          // MEAL LIST
          Expanded(
            child: _isLoading 
                ? const Center(child: CircularProgressIndicator(color: Colors.tealAccent)) 
                : ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _meals.length,
                    itemBuilder: (context, index) {
                      final meal = _meals[index];
                      final nutrients = meal['nutrients'] ?? {"protein": "N/A", "carbs": "N/A", "fat": "N/A"};
                      final List<dynamic> recipeSteps = meal['recipe'] ?? ["No recipe steps provided."];
                      final List<dynamic> ingredients = meal['ingredients'] ?? [];

                      return Card(
                        color: Colors.grey.shade900,
                        margin: const EdgeInsets.only(bottom: 20),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(15), 
                          side: BorderSide(color: Colors.teal.withOpacity(0.3))
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(16.0),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // 1. HEADER
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  Text(meal['type'] ?? "Meal", style: const TextStyle(color: Colors.tealAccent, fontWeight: FontWeight.bold)),
                                  Text("${meal['calories']} kcal", style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                                ],
                              ),
                              const SizedBox(height: 8),
                              
                              // 2. NAME
                              Text(
                                meal['name'] ?? "Unknown Dish", 
                                style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold)
                              ),
                              const SizedBox(height: 15),

                              // 3. NUTRIENTS BADGE
                              Container(
                                padding: const EdgeInsets.symmetric(vertical: 10),
                                decoration: BoxDecoration(
                                  color: Colors.black38,
                                  borderRadius: BorderRadius.circular(10),
                                  border: Border.all(color: Colors.white10)
                                ),
                                child: Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                                  children: [
                                    _nutrientBadge("PRO", "${nutrients['protein']}", Colors.blue),
                                    _nutrientBadge("CARBS", "${nutrients['carbs']}", Colors.orange),
                                    _nutrientBadge("FAT", "${nutrients['fat']}", Colors.red),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 15),

                              // 4. INGREDIENTS
                              Wrap(
                                spacing: 8,
                                children: ingredients.map<Widget>((ing) {
                                  return ActionChip(
                                    label: Text(ing.toString(), style: const TextStyle(color: Colors.white)),
                                    backgroundColor: Colors.deepPurple.shade900,
                                    onPressed: () => _checkPrice(ing.toString()),
                                    avatar: const Icon(Icons.shopping_cart, size: 12, color: Colors.white70),
                                  );
                                }).toList(),
                              ),
                              
                              const SizedBox(height: 10),

                              // 5. RECIPE STEPS
                              ExpansionTile(
                                tilePadding: EdgeInsets.zero,
                                title: const Text("👩‍🍳 View Recipe", style: TextStyle(color: Colors.white70, fontSize: 14)),
                                children: [
                                  Container(
                                    width: double.infinity,
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(
                                      color: Colors.black26,
                                      borderRadius: BorderRadius.circular(8)
                                    ),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: recipeSteps.asMap().entries.map((entry) {
                                        return Padding(
                                          padding: const EdgeInsets.only(bottom: 8.0),
                                          child: Row(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Text("${entry.key + 1}. ", style: const TextStyle(color: Colors.tealAccent, fontWeight: FontWeight.bold)),
                                              Expanded(child: Text(entry.value.toString(), style: const TextStyle(color: Colors.grey))),
                                            ],
                                          ),
                                        );
                                      }).toList(),
                                    ),
                                  )
                                ],
                              ),

                              const SizedBox(height: 10),
                              
                              // 6. ACTIONS
                              Row(
                                children: [
                                  Expanded(
                                    child: OutlinedButton(
                                      onPressed: () => _swapSingleMeal(index),
                                      child: const Text("Swap Meal"),
                                    ),
                                  ),
                                ],
                              )
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

  Widget _nutrientBadge(String label, String value, Color color) {
    return Column(
      children: [
        Text(value, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 16)),
        Text(label, style: const TextStyle(color: Colors.grey, fontSize: 9)),
      ],
    );
  }
}