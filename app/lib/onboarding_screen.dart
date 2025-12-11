import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dashboard.dart';

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

  Future<void> _calculateAndComplete() async {
    if (_nameController.text.isEmpty ||
        _ageController.text.isEmpty ||
        _heightController.text.isEmpty ||
        _weightController.text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Please fill in all fields to calibrate.")),
      );
      return;
    }

    // 1. PARSE INPUTS
    int age = int.parse(_ageController.text);
    double heightCm = double.parse(_heightController.text);
    double weightKg = double.parse(_weightController.text);

    // 2. CALCULATE BMR (Mifflin-St Jeor Equation)
    // Male: (10 x W) + (6.25 x H) - (5 x A) + 5
    // Female: (10 x W) + (6.25 x H) - (5 x A) - 161
    double bmr = (10 * weightKg) + (6.25 * heightCm) - (5 * age);
    
    if (_selectedGender == "Male") {
      bmr += 5;
    } else {
      bmr -= 161;
    }

    // 3. CALCULATE TDEE (Baseline Activity)
    // We assume "Sedentary" (1.2) as a baseline because the Dashboard 
    // tracks *active* steps separately and adds them on top.
    double tdee = bmr * 1.2;

    // 4. ADJUST FOR GOAL
    int targetCalories = tdee.round();

    if (_selectedGoal.contains("Cut") || _selectedGoal.contains("Lean")) {
      targetCalories -= 500; // Aggressive deficit
    } else if (_selectedGoal.contains("Bulk")) {
      targetCalories += 300; // Lean bulk surplus
    } else if (_selectedGoal.contains("Recomposition")) {
      targetCalories -= 200; // Slight deficit to burn fat while building
    }
    // "Maintain" keeps TDEE as is.

    // Safety Clamps (Don't starve/overfeed dangerously)
    if (targetCalories < 1200) targetCalories = 1200;
    if (targetCalories > 4000) targetCalories = 4000;

    // 5. SAVE DATA
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('user_name', _nameController.text);
    await prefs.setString('user_goal', _selectedGoal);
    await prefs.setInt('daily_calorie_target', targetCalories);
    
    // Save raw stats for potential future use (BMI etc)
    await prefs.setDouble('user_weight', weightKg);
    await prefs.setDouble('user_height', heightCm);
    
    // Mark as done
    await prefs.setBool('is_onboarded', true);

    if (!mounted) return;
    
    // Show the result briefly before navigating
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text("Baseline Calculated: $targetCalories kcal/day"),
        backgroundColor: Colors.teal,
        duration: const Duration(seconds: 2),
      ),
    );

    // Give user a moment to see the message, then go
    await Future.delayed(const Duration(seconds: 1));
    if (!mounted) return;

    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (context) => const DashboardScreen()),
    );
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