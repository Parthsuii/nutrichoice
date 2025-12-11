import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

class ShoppingListScreen extends StatefulWidget {
  const ShoppingListScreen({super.key});

  @override
  State<ShoppingListScreen> createState() => _ShoppingListScreenState();
}

class _ShoppingListScreenState extends State<ShoppingListScreen> {
  List<String> _shoppingList = [];
  final Map<String, bool> _checkedItems = {};
  final TextEditingController _addItemController = TextEditingController();
  
  @override
  void initState() {
    super.initState();
    _loadData();
  }

  // --- 1. DATA MANAGEMENT ---
  Future<void> _loadData() async {
    final prefs = await SharedPreferences.getInstance();
    
    // Load existing manual list
    List<String> savedList = prefs.getStringList('shopping_list') ?? [];
    
    // Check if new items came from Meal Planner
    String? savedPlanJson = prefs.getString('saved_plan_json');
    if (savedPlanJson != null) {
      List<dynamic> meals = jsonDecode(savedPlanJson);
      for (var meal in meals) {
        if (meal['ingredients'] is List) {
          for (var rawIng in meal['ingredients']) {
            String clean = _cleanItemName(rawIng.toString());
            if (!savedList.contains(clean)) {
              savedList.add(clean);
            }
          }
        }
      }
    }

    setState(() {
      _shoppingList = savedList;
      // Initialize check states
      for (var item in _shoppingList) {
        if (!_checkedItems.containsKey(item)) {
          _checkedItems[item] = false;
        }
      }
      _sortList();
    });
  }

  String _cleanItemName(String raw) {
    // Strips numbers/units: "200g Paneer" -> "Paneer"
    final regex = RegExp(r'^[\d\./]+\s*(g|kg|ml|l|oz|lb|tbsp|tsp|cup|cups|x|pcs)?\s*', caseSensitive: false);
    String clean = raw.replaceAll(regex, '').trim();
    return clean.isNotEmpty ? clean[0].toUpperCase() + clean.substring(1) : clean;
  }

  Future<void> _saveList() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList('shopping_list', _shoppingList);
  }

  void _addItem() {
    String text = _addItemController.text.trim();
    if (text.isNotEmpty) {
      String clean = _cleanItemName(text);
      if (!_shoppingList.contains(clean)) {
        setState(() {
          _shoppingList.insert(0, clean); // Add to top
          _checkedItems[clean] = false;
        });
        _saveList();
      }
      _addItemController.clear();
    }
  }

  void _removeItem(String item) {
    setState(() {
      _shoppingList.remove(item);
      _checkedItems.remove(item);
    });
    _saveList();
  }

  void _toggleCheck(String item) {
    setState(() {
      _checkedItems[item] = !(_checkedItems[item] ?? false);
      _sortList();
    });
  }

  void _sortList() {
    _shoppingList.sort((a, b) {
      bool aChecked = _checkedItems[a] ?? false;
      bool bChecked = _checkedItems[b] ?? false;
      if (aChecked == bChecked) return a.compareTo(b);
      return aChecked ? 1 : -1; // Unchecked first
    });
  }

  void _clearChecked() {
    setState(() {
      _shoppingList.removeWhere((item) => _checkedItems[item] == true);
      _checkedItems.removeWhere((key, val) => val == true);
    });
    _saveList();
  }

  // --- 2. SMART PRICE CHECK (Your Logic) ---
  Future<void> _comparePrice(String item) async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => const Center(child: CircularProgressIndicator(color: Colors.green)),
    );

    try {
      final response = await http.post(
        Uri.parse('https://nutrichoice-xvpf.onrender.com/compare-prices'),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"item_name": item}),
      );

      if (!mounted) return;
      Navigator.pop(context); // Close loader

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _showSmartComparisonSheet(item, data['results']);
      }
    } catch (e) {
      if (!mounted) return;
      Navigator.pop(context);
      _fallbackSearch(item); // Fallback if API fails
    }
  }

  Future<void> _fallbackSearch(String item) async {
    String query = item.replaceAll(" ", "%20");
    Uri url = Uri.parse("https://blinkit.com/s/?q=$query");
    await launchUrl(url, mode: LaunchMode.externalApplication);
  }

  // --- 3. UI COMPONENTS ---
  void _showSmartComparisonSheet(String item, List<dynamic> results) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.grey.shade900,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (context) => Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text("Best Deals for '$item'", style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 15),
            ...results.map((res) {
              bool isCheapest = res['is_cheapest'] ?? false;
              return Card(
                color: isCheapest ? Colors.green.withOpacity(0.15) : Colors.grey.shade800,
                child: ListTile(
                  onTap: () => _fallbackSearch(item), // Or use specific link if available
                  leading: const Icon(Icons.store, color: Colors.white70),
                  title: Text(res['store'], style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                  trailing: Text("₹${res['price']}", style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
                  subtitle: isCheapest ? const Text("✨ Best Price", style: TextStyle(color: Colors.greenAccent)) : null,
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    int total = _shoppingList.length;
    int checkedCount = _checkedItems.values.where((v) => v).length;
    double progress = total == 0 ? 0 : checkedCount / total;

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("Smart Grocery Cart"),
        backgroundColor: Colors.green.shade900,
        actions: [
          IconButton(
            icon: const Icon(Icons.delete_sweep),
            tooltip: "Clear Checked",
            onPressed: _clearChecked,
          )
        ],
      ),
      body: Column(
        children: [
          // PROGRESS HEADER
          if (total > 0)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 15),
              decoration: BoxDecoration(color: Colors.grey.shade900, border: Border(bottom: BorderSide(color: Colors.green.withOpacity(0.3)))),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text("$checkedCount / $total Found", style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                      Text("${(progress * 100).toInt()}%", style: const TextStyle(color: Colors.greenAccent, fontWeight: FontWeight.bold)),
                    ],
                  ),
                  const SizedBox(height: 8),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: progress,
                      minHeight: 6,
                      backgroundColor: Colors.black,
                      valueColor: AlwaysStoppedAnimation<Color>(progress == 1.0 ? Colors.greenAccent : Colors.green),
                    ),
                  ),
                ],
              ),
            ),

          // INPUT AREA
          Container(
            padding: const EdgeInsets.all(16),
            color: Colors.black,
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _addItemController,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      hintText: "Add item (e.g. Milk)...",
                      hintStyle: TextStyle(color: Colors.grey.shade600),
                      filled: true,
                      fillColor: Colors.grey.shade900,
                      isDense: true,
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(30), borderSide: BorderSide.none),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                    ),
                    onSubmitted: (_) => _addItem(),
                  ),
                ),
                const SizedBox(width: 10),
                FloatingActionButton.small(
                  onPressed: _addItem,
                  backgroundColor: Colors.green,
                  child: const Icon(Icons.add, color: Colors.white),
                )
              ],
            ),
          ),

          // LIST
          Expanded(
            child: _shoppingList.isEmpty 
              ? const Center(child: Text("Cart is empty.", style: TextStyle(color: Colors.grey)))
              : ListView.builder(
                  padding: const EdgeInsets.only(bottom: 80, left: 10, right: 10),
                  itemCount: _shoppingList.length,
                  itemBuilder: (context, index) {
                    final item = _shoppingList[index];
                    final isChecked = _checkedItems[item] ?? false;

                    return Dismissible(
                      key: Key(item),
                      background: Container(color: Colors.red, alignment: Alignment.centerRight, padding: const EdgeInsets.only(right: 20), child: const Icon(Icons.delete, color: Colors.white)),
                      onDismissed: (_) => _removeItem(item),
                      child: Card(
                        color: isChecked ? Colors.green.withOpacity(0.05) : Colors.grey.shade900,
                        margin: const EdgeInsets.only(bottom: 8),
                        child: ListTile(
                          leading: Checkbox(
                            value: isChecked,
                            activeColor: Colors.green,
                            checkColor: Colors.black,
                            side: const BorderSide(color: Colors.grey),
                            onChanged: (val) => _toggleCheck(item),
                          ),
                          title: Text(
                            item,
                            style: TextStyle(
                              color: isChecked ? Colors.grey : Colors.white,
                              fontSize: 16,
                              decoration: isChecked ? TextDecoration.lineThrough : null,
                              decorationColor: Colors.green,
                            ),
                          ),
                          trailing: isChecked 
                            ? null 
                            : IconButton(
                                icon: const Icon(Icons.search, color: Colors.blueAccent),
                                onPressed: () => _comparePrice(item),
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
}