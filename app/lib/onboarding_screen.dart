import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dashboard.dart';
import 'services/api_service.dart'; // <--- IMPORT YOUR API SERVICE

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  // Controllers
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _ageController = TextEditingController();
  final TextEditingController _heightController = TextEditingController();
  final TextEditingController _weightController = TextEditingController();

  // Dropdowns
  String _selectedGender = "Male";
  String _selectedGoal = "Lean / Cut"; // Default

  final List<String> _genders = ["Male", "Female"];
  final List<String> _goals = [
    "Lean / Cut",       // Deficit
    "Bulk / Size",      // Surplus
    "Recomposition",    // Maintenance / Slight Deficit
    "Maintain"          // Maintenance
  ];

  // --- THE NEW "LOUD" CONNECTION FUNCTION ---
  Future<void> _calculateAndComplete() async {
    // 1. Validation
    if (_nameController.text.isEmpty ||
        _ageController.text.isEmpty ||
        _heightController.text.isEmpty ||
        _weightController.text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Please fill in all fields.")),
      );
      return;
    }

    // 2. Parse Inputs
    double heightCm = double.parse(_heightController.text);
    double weightKg = double.parse(_weightController.text);
    
    // 3. SHOW LOADING STATUS
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text("Connecting to Server... (Please Wait)"), 
        duration: Duration(seconds: 10)
      ),
    );

    try {
      // Convert Goal to Backend Keywords
      String backendGoal = 'MAINTAIN';
      if (_selectedGoal.contains("Cut") || _selectedGoal.contains("Lean")) {
        backendGoal = 'SHRED';
      } else if (_selectedGoal.contains("Bulk")) {
        backendGoal = 'BULK';
      }

      print("🚀 SENDING REQUEST TO: ${ApiService.baseUrl}/profile/");

      // 4. CALL API (This will throw an error if it fails)
      final serverData = await ApiService.updateProfile(
        weight: weightKg,
        height: heightCm.toInt(),
        goal: backendGoal,
        activityLevel: 'SEDENTARY',
      );

      // 5. SUCCESS!
      print("✅ DATA SENT! Server replied: $serverData");
      
      // Save locally
      int targetCalories = serverData['calculated_calories'] ?? 2000;
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('user_name', _nameController.text);
      await prefs.setString('user_goal', _selectedGoal);
      await prefs.setInt('daily_calorie_target', targetCalories);
      
      // Save raw stats
      await prefs.setDouble('user_weight', weightKg);
      await prefs.setDouble('user_height', heightCm);
      await prefs.setBool('is_onboarded', true);

      if (!mounted) return;
      
      // Go to Dashboard
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (context) => const DashboardScreen()),
      );

    } catch (e) {
      // 6. FAILURE - SHOW THE ERROR ON SCREEN
      print("❌ CRITICAL ERROR: $e");
      
      if (!mounted) return;
      
      // SHOW A POPUP WITH THE EXACT ERROR
      showDialog(
        context: context, 
        builder: (ctx) => AlertDialog(
          title: const Text("Connection Failed"),
          content: SingleChildScrollView(
            child: Text("Could not save to database.\n\nError details:\n$e"),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx), 
              child: const Text("OK")
            )
          ],
        )
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(30.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Center(
                child: Icon(Icons.calculate, color: Colors.tealAccent, size: 60),
              ),
              const SizedBox(height: 20),
              const Center(
                child: Text(
                  "Physique Architect",
                  style: TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.bold),
                ),
              ),
              const Center(
                child: Text(
                  "Enter stats to auto-calculate fuel.",
                  style: TextStyle(color: Colors.grey, fontSize: 16),
                ),
              ),
              const SizedBox(height: 40),
              
              // Name
              _buildInput("Codename / Name", _nameController, false),
              const SizedBox(height: 15),

              // Gender & Age Row
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      initialValue: _selectedGender,
                      dropdownColor: Colors.grey.shade900,
                      style: const TextStyle(color: Colors.white),
                      decoration: _inputDecoration("Gender"),
                      items: _genders.map((g) => DropdownMenuItem(value: g, child: Text(g))).toList(),
                      onChanged: (val) => setState(() => _selectedGender = val!),
                    ),
                  ),
                  const SizedBox(width: 15),
                  Expanded(
                    child: _buildInput("Age", _ageController, true),
                  ),
                ],
              ),
              const SizedBox(height: 15),

              // Height & Weight Row
              Row(
                children: [
                  Expanded(
                    child: _buildInput("Height (cm)", _heightController, true),
                  ),
                  const SizedBox(width: 15),
                  Expanded(
                    child: _buildInput("Weight (kg)", _weightController, true),
                  ),
                ],
              ),
              const SizedBox(height: 15),

              // Goal Input
              DropdownButtonFormField<String>(
                initialValue: _selectedGoal,
                dropdownColor: Colors.grey.shade900,
                style: const TextStyle(color: Colors.white),
                decoration: _inputDecoration("Target Physique"),
                items: _goals.map((g) => DropdownMenuItem(value: g, child: Text(g))).toList(),
                onChanged: (val) => setState(() => _selectedGoal = val!),
              ),

              const SizedBox(height: 50),
              
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _calculateAndComplete,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.teal.shade800,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                  child: const Text("CALCULATE & ACCESS SYSTEM", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildInput(String label, TextEditingController controller, bool isNumber) {
    return TextField(
      controller: controller,
      keyboardType: isNumber ? TextInputType.number : TextInputType.text,
      style: const TextStyle(color: Colors.white),
      decoration: _inputDecoration(label),
    );
  }

  InputDecoration _inputDecoration(String label) {
    return InputDecoration(
      labelText: label,
      labelStyle: const TextStyle(color: Colors.teal),
      filled: true,
      fillColor: Colors.grey.shade900,
      enabledBorder: OutlineInputBorder(
        borderSide: BorderSide(color: Colors.grey.shade800),
        borderRadius: BorderRadius.circular(10),
      ),
      focusedBorder: OutlineInputBorder(
        borderSide: const BorderSide(color: Colors.tealAccent),
        borderRadius: BorderRadius.circular(10),
      ),
    );
  }
}