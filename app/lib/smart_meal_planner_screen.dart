import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/api_service.dart'; 

class SmartMealPlannerScreen extends StatefulWidget {
  const SmartMealPlannerScreen({super.key});

  @override
  State<SmartMealPlannerScreen> createState() => _SmartMealPlannerScreenState();
}

class _SmartMealPlannerScreenState extends State<SmartMealPlannerScreen> {
  bool _isLoading = false;
  List<dynamic> _meals = [];
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

  // Helper for Safe Parsing (Prevents Null Crashes)
  int _safeInt(dynamic val) {
    if (val == null) return 0;
    if (val is int) return val;
    return int.tryParse(val.toString()) ?? 0;
  }

  @override
  void initState() {
    super.initState();
    _loadOrGeneratePlan();
  }

  // --- 1. LOAD OR GENERATE LOGIC ---
  Future<void> _loadOrGeneratePlan() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;

    setState(() {
      _userGoal = prefs.getString('user_goal') ?? "Maintain";
      int dynamicCal = prefs.getInt('dynamic_calorie_target') ?? 0;
      int baseCal = prefs.getInt('daily_calorie_target') ?? 2000;
      _dailyCalories = (dynamicCal > baseCal) ? dynamicCal : baseCal;
    });

    String todayDate = DateTime.now().toIso8601String().split('T')[0];
    String currentKey = "${_selectedContext}_${_dailyCalories}_${_availableIngredients.join(',')}";
    
    String? savedDate = prefs.getString('saved_plan_date');
    String? savedKey = prefs.getString('saved_plan_key');
    String? savedMeals = prefs.getString('saved_plan_json');

    // Load Cache ONLY if Key Matches (prevents stale data)
    if (savedDate == todayDate && savedKey == currentKey && savedMeals != null) {
      print("📅 Loading cached plan...");
      setState(() {
        _meals = jsonDecode(savedMeals);
      });
    } else {
      print("🧠 Generating NEW Plan (Cache Miss)...");
      _generateFullPlan();
    }
  }

  // --- 2. CALL BACKEND (Generate) ---
  Future<void> _generateFullPlan() async {
    setState(() => _isLoading = true);
    try {
      final prefs = await SharedPreferences.getInstance();
      
      final data = await ApiService.generateMealPlan(
        goal: _userGoal,
        calories: _dailyCalories,
        context: _selectedContext,
        ingredients: _availableIngredients,
      );

      if (!mounted) return;

      if (data['meals'] != null) {
        setState(() {
          _meals = data['meals'];
          _isLoading = false;
        });

        String todayDate = DateTime.now().toIso8601String().split('T')[0];
        String currentKey = "${_selectedContext}_${_dailyCalories}_${_availableIngredients.join(',')}";
        
        await prefs.setString('saved_plan_date', todayDate);
        await prefs.setString('saved_plan_key', currentKey);
        await prefs.setString('saved_plan_json', jsonEncode(_meals));
      } else {
         setState(() => _isLoading = false);
         ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("AI is busy. Try again.")));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Error: $e")));
      setState(() => _isLoading = false);
    }
  }

  // --- 3. CALL BACKEND (Swap Meal) ---
  Future<void> _swapSingleMeal(int index) async {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Chef is cooking up a swap...")));
    try {
      final oldMealName = _meals[index]['name'] ?? "Meal";
      final targetCals = _safeInt(_meals[index]['calories']);

      final newMeal = await ApiService.swapMeal(
        goal: oldMealName, 
        calories: targetCals,
        context: _selectedContext,
      );

      if (!mounted) return;

      setState(() {
        newMeal['time'] = _meals[index]['time']; // Keep old time
        _meals[index] = newMeal;
      });
      
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('saved_plan_json', jsonEncode(_meals));

    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Swap failed: $e")));
    }
  }

  Future<void> _checkPrice(dynamic meal) async {
    String query = meal['name'] ?? "Groceries";
    if (meal['ingredients'] != null && (meal['ingredients'] as List).isNotEmpty) {
      query = meal['ingredients'][0];
    }
    Uri url = Uri.parse("https://blinkit.com/s/?q=${query.replaceAll(" ", "%20")}");
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
      _generateFullPlan();
    }
  }

  void _removeIngredient(String item) {
    setState(() {
      _availableIngredients.remove(item);
    });
    _generateFullPlan();
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
        title: const Text("Context Chef AI"),
        backgroundColor: Colors.teal.shade900,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Regenerating Plan...")));
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
          // 1. CONTEXT & PANTRY SECTION
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
                color: Colors.grey.shade900,
                border: Border(bottom: BorderSide(color: Colors.teal.shade900))
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                DropdownButtonFormField<String>(
                  value: _contextOptions.contains(_selectedContext) ? _selectedContext : _contextOptions[0],
                  dropdownColor: Colors.grey.shade800,
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                  decoration: const InputDecoration(
                    labelText: "Today's Goal", 
                    labelStyle: TextStyle(color: Colors.teal),
                    border: OutlineInputBorder(),
                    enabledBorder: OutlineInputBorder(borderSide: BorderSide(color: Colors.white24)),
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
                          hintText: "Add pantry item (e.g. Paneer)",
                          hintStyle: TextStyle(color: Colors.grey),
                          isDense: true,
                          contentPadding: EdgeInsets.symmetric(vertical: 12, horizontal: 10),
                          filled: true,
                          fillColor: Colors.black26,
                          border: OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
                        ),
                        onSubmitted: (_) => _addIngredient(),
                      ),
                    ),
                    IconButton(icon: const Icon(Icons.add_circle, color: Colors.teal, size: 30), onPressed: _addIngredient),
                  ],
                ),
                if (_availableIngredients.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 8.0),
                    child: Wrap(
                      spacing: 8,
                      children: _availableIngredients.map((item) => Chip(
                        label: Text(item),
                        onDeleted: () => _removeIngredient(item),
                        backgroundColor: Colors.teal.withOpacity(0.2),
                        labelStyle: const TextStyle(color: Colors.white),
                        deleteIconColor: Colors.redAccent,
                      )).toList(),
                    ),
                  ),
              ],
            ),
          ),

          // 2. MEAL LIST
          Expanded(
            child: _isLoading 
                ? Center(child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const CircularProgressIndicator(color: Colors.tealAccent),
                      const SizedBox(height: 15),
                      Text("Chef is planning your $_selectedContext...", style: const TextStyle(color: Colors.white70))
                    ],
                  )) 
                : _meals.isEmpty 
                    ? const Center(child: Text("No meals generated yet.", style: TextStyle(color: Colors.grey)))
                    : ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: _meals.length,
                        itemBuilder: (context, index) {
                          final meal = _meals[index];
                          final ingredients = meal['ingredients'] as List?;
                          
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
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                        decoration: BoxDecoration(color: Colors.teal.withOpacity(0.2), borderRadius: BorderRadius.circular(5)),
                                        child: Text(meal['time'] ?? "Meal", style: const TextStyle(color: Colors.tealAccent, fontWeight: FontWeight.bold, fontSize: 12)),
                                      ),
                                      Text("${_safeInt(meal['calories'])} kcal", style: const TextStyle(color: Colors.white70, fontWeight: FontWeight.bold)),
                                    ],
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    meal['name'] ?? "Unknown Dish", 
                                    style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)
                                  ),
                                  const SizedBox(height: 15),
                                  
                                  // Macros
                                  Container(
                                    padding: const EdgeInsets.symmetric(vertical: 10),
                                    decoration: BoxDecoration(
                                      color: Colors.black38,
                                      borderRadius: BorderRadius.circular(10),
                                    ),
                                    child: Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceAround,
                                      children: [
                                        _nutrientBadge("PRO", "${_safeInt(meal['protein'])}g", Colors.blue),
                                        _nutrientBadge("CARBS", "${_safeInt(meal['carbs'])}g", Colors.orange),
                                        _nutrientBadge("FAT", "${_safeInt(meal['fat'])}g", Colors.red),
                                      ],
                                    ),
                                  ),
                                  
                                  const SizedBox(height: 15),

                                  // --- NEW: INGREDIENTS LIST ---
                                  if (ingredients != null && ingredients.isNotEmpty) ...[
                                    const Text("Ingredients needed:", style: TextStyle(color: Colors.white60, fontSize: 12)),
                                    const SizedBox(height: 5),
                                    Wrap(
                                      spacing: 6,
                                      runSpacing: 6,
                                      children: ingredients.map<Widget>((ing) => 
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                          decoration: BoxDecoration(
                                            color: Colors.white10,
                                            borderRadius: BorderRadius.circular(8),
                                            border: Border.all(color: Colors.white24, width: 0.5)
                                          ),
                                          child: Text(ing.toString(), style: const TextStyle(color: Colors.white70, fontSize: 12)),
                                        )
                                      ).toList(),
                                    ),
                                    const SizedBox(height: 10),
                                  ],

                                  // Recipe Expandable
                                  if (meal['recipe'] != null && (meal['recipe'] as List).isNotEmpty)
                                    ExpansionTile(
                                      tilePadding: EdgeInsets.zero,
                                      title: const Text("View Recipe Steps", style: TextStyle(color: Colors.tealAccent, fontSize: 14)),
                                      children: (meal['recipe'] as List).map<Widget>((step) => 
                                        ListTile(
                                          leading: const Icon(Icons.circle, size: 6, color: Colors.white54),
                                          title: Text(step.toString(), style: const TextStyle(color: Colors.white70, fontSize: 13)),
                                          dense: true,
                                          visualDensity: VisualDensity.compact,
                                        )
                                      ).toList(),
                                    ),
                                  
                                  // Actions
                                  const SizedBox(height: 10),
                                  Row(
                                    mainAxisAlignment: MainAxisAlignment.end,
                                    children: [
                                        TextButton.icon(
                                         icon: const Icon(Icons.shopping_cart, size: 16, color: Colors.greenAccent),
                                         label: const Text("Order Items", style: TextStyle(color: Colors.greenAccent)),
                                         onPressed: () => _checkPrice(meal),
                                        ),
                                        const SizedBox(width: 8),
                                        OutlinedButton.icon(
                                         icon: const Icon(Icons.swap_horiz, size: 16, color: Colors.white70),
                                         label: const Text("Swap", style: TextStyle(color: Colors.white70)),
                                         onPressed: () => _swapSingleMeal(index),
                                         style: OutlinedButton.styleFrom(side: const BorderSide(color: Colors.white24)),
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
        Text(label, style: const TextStyle(color: Colors.grey, fontSize: 10)),
      ],
    );
  }
}

// --- CHEF CHAT WIDGET (Unchanged) ---
class ChefChatWidget extends StatefulWidget {
  const ChefChatWidget({super.key});

  @override
  State<ChefChatWidget> createState() => _ChefChatWidgetState();
}

class _ChefChatWidgetState extends State<ChefChatWidget> {
  final TextEditingController _chatController = TextEditingController();
  final List<Map<String, String>> _messages = [
    {"role": "system", "content": "Hello! I am your AI Chef. Ask me about nutrition or recipes!"}
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
      height: MediaQuery.of(context).size.height * 0.75,
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.5), blurRadius: 10)]
      ),
      child: Column(
        children: [
          Container(width: 40, height: 4, margin: const EdgeInsets.symmetric(vertical: 10), decoration: BoxDecoration(color: Colors.grey, borderRadius: BorderRadius.circular(2))),
          const Text("Chef AI", style: TextStyle(color: Colors.tealAccent, fontSize: 18, fontWeight: FontWeight.bold)),
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
                    constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.8),
                    decoration: BoxDecoration(
                      color: isUser ? Colors.teal.shade700 : Colors.grey.shade800,
                      borderRadius: BorderRadius.only(
                        topLeft: const Radius.circular(12),
                        topRight: const Radius.circular(12),
                        bottomLeft: isUser ? const Radius.circular(12) : Radius.zero,
                        bottomRight: isUser ? Radius.zero : const Radius.circular(12),
                      ),
                    ),
                    child: Text(msg['content']!, style: const TextStyle(color: Colors.white, fontSize: 15)),
                  ),
                );
              },
            ),
          ),
          if (_isTyping)
            const Padding(
              padding: EdgeInsets.all(8.0),
              child: Text("Chef is thinking...", style: TextStyle(color: Colors.tealAccent, fontStyle: FontStyle.italic)),
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
                      hintText: "Ask about a recipe...",
                      hintStyle: const TextStyle(color: Colors.grey),
                      filled: true,
                      fillColor: Colors.black,
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(30), borderSide: BorderSide.none),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                    ),
                    onSubmitted: (_) => _sendMessage(),
                  ),
                ),
                const SizedBox(width: 10),
                CircleAvatar(
                  backgroundColor: Colors.tealAccent, 
                  child: IconButton(icon: const Icon(Icons.send, color: Colors.black), onPressed: _sendMessage)
                )
              ],
            ),
          )
        ],
      ),
    );
  }
}