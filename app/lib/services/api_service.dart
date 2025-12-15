import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

class ApiService {
  // Your Backend URL
  static const String baseUrl = "https://nutrichoice-xvpf.onrender.com/api";

  // --- 1. USER PROFILE ---
  static Future<Map<String, dynamic>> updateProfile({
    required double weight,
    required int height,
    required String goal,
    required String activityLevel,
  }) async {
    final url = Uri.parse('$baseUrl/profile/');
    try {
      print("Sending profile data to $url...");
      final response = await http.post(
        url,
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "current_weight": weight,
          "height": height,
          "goal": goal,
          "activity_level": activityLevel,
        }),
      );

      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      } else {
        throw Exception("Failed to update profile: ${response.body}");
      }
    } catch (e) {
      print("❌ Connection Error: $e");
      throw Exception("Error connecting to server: $e");
    }
  }

  // --- 2. GET FOODS ---
  static Future<List<dynamic>> getFoods() async {
    final url = Uri.parse('$baseUrl/foods/');
    try {
      print("Fetching foods from $url...");
      final response = await http.get(url);
      
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      } else {
        throw Exception("Failed to load foods: ${response.statusCode}");
      }
    } catch (e) {
      print("❌ Error fetching foods: $e");
      throw Exception("Error fetching foods: $e");
    }
  }

  // --- 3. ASK AI (Chat) ---
  static Future<String> askAI(String question) async {
    final url = Uri.parse('$baseUrl/ask-ai/');
    try {
      final response = await http.post(
        url,
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"question": question}),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return data['answer'];
      } else {
        return "AI Error: ${response.statusCode}";
      }
    } catch (e) {
      return "Connection Error: $e";
    }
  }

  // --- 4. SMART SCAN (Text or Image) ---
  // UPDATED: Now supports sending Text (OCR) OR Image
  static Future<Map<String, dynamic>> scanFoodSmart(File? imageFile, String? extractedText) async {
    final url = Uri.parse('$baseUrl/scan-food/');
    try {
      var request = http.MultipartRequest('POST', url);

      // STRATEGY: Prioritize Text (Faster/Cheaper)
      if (extractedText != null && extractedText.isNotEmpty) {
        print("🚀 Sending EXTRACTED TEXT to Backend: $extractedText");
        request.fields['food_name'] = extractedText;
      } 
      // Fallback: Send Image (Vision AI)
      else if (imageFile != null) {
        print("📸 Sending IMAGE to Backend...");
        request.files.add(await http.MultipartFile.fromPath('image', imageFile.path));
      } else {
        throw Exception("No image or text provided.");
      }

      var streamedResponse = await request.send();
      var response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      } else {
        throw Exception("Scan failed: ${response.body}");
      }
    } catch (e) {
      print("❌ Scan Error: $e");
      throw Exception("Error scanning food: $e");
    }
  }

  // --- 5. DELETE FOOD ---
  static Future<void> deleteFood(int id) async {
    final url = Uri.parse('$baseUrl/foods/$id/'); 
    try {
      print("Deleting food ID $id...");
      final response = await http.delete(url);
      
      if (response.statusCode != 204 && response.statusCode != 200) {
        print("⚠️ Server Warning: Could not delete on server (Code ${response.statusCode})");
      } else {
        print("✅ Deleted successfully from server.");
      }
    } catch (e) {
      print("❌ Delete Error: $e");
    }
  }

  // --- 6. GENERATE MEAL PLAN ---
  static Future<Map<String, dynamic>> generateMealPlan({
    required String goal,
    required int calories,
    required String context,
    required List<String> ingredients,
  }) async {
    final url = Uri.parse('$baseUrl/generate-meal-plan/'); // Note: Added trailing slash just in case
    try {
      print("Generating plan for context: $context...");
      final response = await http.post(
        url,
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "user_goal": goal,
          "daily_calories": calories,
          "activity_context": context,
          "available_ingredients": ingredients,
        }),
      );

      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      } else {
        throw Exception("Generation failed: ${response.body}");
      }
    } catch (e) {
      print("❌ Generation Error: $e");
      throw Exception("Error generating plan: $e");
    }
  }

  // --- 7. SWAP MEAL ---
  static Future<Map<String, dynamic>> swapMeal({
    required String goal,
    required int calories,
    required String context,
  }) async {
    final url = Uri.parse('$baseUrl/swap-meal/');
    try {
      print("Swapping meal...");
      final response = await http.post(
        url,
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "user_goal": goal,
          "daily_calories": calories,
          "activity_context": context,
        }),
      );

      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      } else {
        throw Exception("Swap failed: ${response.body}");
      }
    } catch (e) {
      print("❌ Swap Error: $e");
      throw Exception("Error swapping meal: $e");
    }
  }
}