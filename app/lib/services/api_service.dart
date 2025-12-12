import 'dart:convert';
import 'dart:io'; // <--- Needed for File (Camera images)
import 'package:http/http.dart' as http;

class ApiService {
  // Your Backend URL
  static const String baseUrl = "https://nutrichoice-xvpf.onrender.com/api";

  // --- 1. USER PROFILE (Physique Architect) ---
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
        print("✅ Success! Server Response: ${response.body}");
        return jsonDecode(response.body);
      } else {
        print("❌ Server Error: ${response.body}");
        throw Exception("Failed to update profile: ${response.body}");
      }
    } catch (e) {
      print("❌ Connection Error: $e");
      throw Exception("Error connecting to server: $e");
    }
  }

  // --- 2. GET FOODS (Meal Tracker) ---
  // Connects to: FoodItemList view
  static Future<List<dynamic>> getFoods() async {
    final url = Uri.parse('$baseUrl/foods/');
    try {
      print("Fetching foods from $url...");
      final response = await http.get(url);
      
      if (response.statusCode == 200) {
        return jsonDecode(response.body); // Returns a List of foods
      } else {
        throw Exception("Failed to load foods: ${response.statusCode}");
      }
    } catch (e) {
      print("❌ Error fetching foods: $e");
      throw Exception("Error fetching foods: $e");
    }
  }

  // --- 3. ASK AI (Smart Chef) ---
  // Connects to: ask_nutritionist view
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

  // --- 4. SCAN FOOD (Camera) ---
  // Connects to: ScanFoodView
  static Future<Map<String, dynamic>> scanFood(File imageFile) async {
    final url = Uri.parse('$baseUrl/scan-food/');
    try {
      print("Uploading image to $url...");
      
      // We use MultipartRequest because we are sending a FILE, not just text
      var request = http.MultipartRequest('POST', url);
      request.files.add(await http.MultipartFile.fromPath('image', imageFile.path));

      var streamedResponse = await request.send();
      var response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        print("✅ Scan Complete: ${response.body}");
        return jsonDecode(response.body);
      } else {
        throw Exception("Scan failed: ${response.body}");
      }
    } catch (e) {
      print("❌ Scan Error: $e");
      throw Exception("Error scanning food: $e");
    }
  }

  // --- 5. DELETE FOOD (New Feature) ---
  // Connects to: DELETE /api/foods/{id}/
  static Future<void> deleteFood(int id) async {
    // Note: This endpoint must exist on your backend.
    // If you haven't added a specific DELETE view yet, this will act as a placeholder
    // that removes it from the UI, but it might fail on the server side until we update views.py.
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
}