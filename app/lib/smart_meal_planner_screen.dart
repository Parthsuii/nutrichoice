import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import 'services/api_service.dart'; // <--- USES YOUR CENTRAL SERVICE

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

  // --- 2. GENERATE NEW PLAN (Updated to use ApiService) ---
  Future<void> _generateFullPlan() async {
    setState(() => _isLoading = true);
    
    try {
      final prefs = await SharedPreferences.getInstance();
      List<String> soreMuscles = prefs.getStringList('sore_muscles') ?? [];
      
      String finalContext = _selectedContext;
      if (soreMuscles.isNotEmpty) {
        finalContext += ". USER SORE IN: ${soreMuscles.join(', ')}. ADD ANTI-INFLAMMATORY FOODS.";
      }

      // CALL API SERVICE
      final data = await ApiService.generateMealPlan(
        goal: _userGoal,
        calories: _dailyCalories,
        context: finalContext,
        ingredients: _availableIngredients,
      );

      if (!mounted) return;

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
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Error: $e")));
      setState(() => _isLoading = false);
    }
  }

  // --- 3. SWAP MEAL LOGIC (Updated to use ApiService) ---
  Future<void> _swapSingleMeal(int index) async {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Swapping meal...")));
    try {
      // CALL API SERVICE
      final newMeal = await ApiService.swapMeal(
        goal: _userGoal,
        calories: _dailyCalories,
        context: _selectedContext,
      );

      if (!mounted) return;

      setState(() {
        newMeal['type'] = _meals[index]['type']; // Keep Breakfast/Lunch tag
        _meals[index] = newMeal;
      });
      
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('saved_plan_json', jsonEncode(_meals));

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

  void _showChatSheet() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => const ChefChatWidget(),
    );
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
      
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _showChatSheet,
        backgroundColor: Colors.tealAccent,
        foregroundColor: Colors.black,
        icon: const Icon(Icons.chat_bubble_outline),
        label: const Text("Ask Chef"),
      ),

      body: Column(
        children: [
          // CONTEXT SECTION
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
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  Text(meal['type'] ?? "Meal", style: const TextStyle(color: Colors.tealAccent, fontWeight: FontWeight.bold)),
                                  Text("${meal['calories']} kcal", style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                                ],
                              ),
                              const SizedBox(height: 8),
                              Text(
                                meal['name'] ?? "Unknown Dish", 
                                style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold)
                              ),
                              const SizedBox(height: 15),
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
                              ExpansionTile(
                                tilePadding: EdgeInsets.zero,
                                title: const Text("👩‍🍳 View Recipe", style: TextStyle(color: Colors.white70, fontSize: 14)),
                                children: [
                                  Container(
                                    width: double.infinity,
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(color: Colors.black26, borderRadius: BorderRadius.circular(8)),
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

// --- CHEF CHAT WIDGET ---
class ChefChatWidget extends StatefulWidget {
  const ChefChatWidget({super.key});

  @override
  State<ChefChatWidget> createState() => _ChefChatWidgetState();
}

class _ChefChatWidgetState extends State<ChefChatWidget> {
  final TextEditingController _chatController = TextEditingController();
  final List<Map<String, String>> _messages = [
    {"role": "system", "content": "Hello! I am your AI Chef. Ask me about nutrition, recipes, or your meal plan!"}
  ];
  bool _isTyping = false;

  Future<void> _sendMessage() async {
    final text = _chatController.text.trim();
    if (text.isEmpty) return;

    setState(() {
      _messages.add({"role": "user", "content": text});
      _isTyping = true;
      _chatController.clear();
    });

    try {
      final response = await ApiService.askAI(text);
      if(mounted) {
        setState(() {
          _messages.add({"role": "system", "content": response});
          _isTyping = false;
        });
      }
    } catch (e) {
      if(mounted) {
        setState(() {
          _messages.add({"role": "system", "content": "Error: Could not connect to Chef."});
          _isTyping = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).size.height * 0.7,
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        children: [
          Container(width: 40, height: 4, margin: const EdgeInsets.symmetric(vertical: 10), decoration: BoxDecoration(color: Colors.grey, borderRadius: BorderRadius.circular(2))),
          const Text("Chat with Chef", style: TextStyle(color: Colors.tealAccent, fontSize: 18, fontWeight: FontWeight.bold)),
          const Divider(color: Colors.grey),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final msg = _messages[index];
                final isUser = msg['role'] == 'user';
                return Align(
                  alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.symmetric(vertical: 5),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: isUser ? Colors.teal : Colors.grey.shade800,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(msg['content']!, style: const TextStyle(color: Colors.white)),
                  ),
                );
              },
            ),
          ),
          if (_isTyping)
            const Padding(
              padding: EdgeInsets.all(8.0),
              child: Text("Chef is typing...", style: TextStyle(color: Colors.grey, fontStyle: FontStyle.italic)),
            ),
          Padding(
            padding: EdgeInsets.only(left: 16, right: 16, top: 10, bottom: MediaQuery.of(context).viewInsets.bottom + 20),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _chatController,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      hintText: "Ask about food...",
                      hintStyle: const TextStyle(color: Colors.grey),
                      filled: true,
                      fillColor: Colors.black,
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(30), borderSide: BorderSide.none),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                    ),
                    onSubmitted: (_) => _sendMessage(),
                  ),
                ),
                const SizedBox(width: 10),
                CircleAvatar(backgroundColor: Colors.teal, child: IconButton(icon: const Icon(Icons.send, color: Colors.white), onPressed: _sendMessage))
              ],
            ),
          )
        ],
      ),
    );
  }
}