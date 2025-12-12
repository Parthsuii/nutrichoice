from rest_framework.decorators import api_view, parser_classes, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import serializers
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from PIL import Image
from django.contrib.auth.models import User
import os
import base64
import json

# --- IMPORTS FROM YOUR APP ---
from .models import FoodItem, UserProfile 
from .serializers import FoodItemSerializer, UserProfileSerializer, FoodImageSerializer

# --- AI LIBRARIES ---
import google.generativeai as genai
from mistralai import Mistral
from groq import Groq

# --- CONFIGURATION ---
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY")
GROQ_KEY = os.environ.get("GROQ_API_KEY")

if GOOGLE_KEY:
    genai.configure(api_key=GOOGLE_KEY)

# --- HELPER: Convert Image to Base64 ---
def encode_image(image_file):
    return base64.b64encode(image_file.read()).decode('utf-8')

# ==========================================
# 1. STANDARD CRUD VIEWS (FOOD ITEMS)
# ==========================================

class FoodItemList(ListCreateAPIView):
    queryset = FoodItem.objects.all()
    serializer_class = FoodItemSerializer
    authentication_classes = [] # Allows access without login
    permission_classes = []

class FoodItemDetail(RetrieveUpdateDestroyAPIView):
    queryset = FoodItem.objects.all()
    serializer_class = FoodItemSerializer
    authentication_classes = []
    permission_classes = []

# ==========================================
# 2. AI TEXT ENDPOINT (Nutrition Q&A)
# ==========================================

@csrf_exempt  # <--- FIX FOR 403 ERROR
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def ask_nutritionist(request):
    user_question = request.data.get('question')
    if not user_question:
        return Response({"error": "Please provide a 'question'"}, status=400)

    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(f"You are a nutritionist. Answer briefly: {user_question}")
        return Response({"answer": response.text, "source": "Gemini"})
    except Exception as e:
        return Response({"error": str(e)}, status=500)

# ==========================================
# 3. FOOD SCANNER (With CSRF Fix)
# ==========================================

@method_decorator(csrf_exempt, name='dispatch') # <--- FIX FOR 403 ERROR
class ScanFoodView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = [] # Allow public access
    permission_classes = []

    def post(self, request, *args, **kwargs):
        if 'image' not in request.FILES:
            return Response({"error": "No image provided"}, status=400)
        
        image_file = request.FILES['image']
        
        # Prompt for strict JSON output
        prompt = """
        Analyze this food image. Identify the food items.
        Estimate the calories and macros (Protein, Carbs, Fats).
        Your response MUST be ONLY a single, valid JSON object.
        JSON Format:
        {
            "food_name": "...",
            "estimated_calories": integer,
            "protein": float,
            "carbs": float,
            "fat": float
        }
        """

        try:
            pil_image = Image.open(image_file)
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            response = model.generate_content([prompt, pil_image])
            
            # Clean JSON
            clean_json_str = response.text.strip().replace("```json", "").replace("```", "").strip()
            parsed_data = json.loads(clean_json_str)

            # Save to DB
            new_food = FoodItem.objects.create(
                name=parsed_data.get('food_name', 'Unknown'),
                calories=int(parsed_data.get('estimated_calories', 0)),
                protein=float(parsed_data.get('protein', 0.0)),
                carbs=float(parsed_data.get('carbs', 0.0)),
                fat=float(parsed_data.get('fat', 0.0)),
            )

            return Response({
                "message": "Food analyzed successfully!",
                "saved_data": {
                    "name": new_food.name,
                    "calories": new_food.calories
                }
            })
        except Exception as e:
            return Response({"error": f"Analysis failed: {str(e)}"}, status=500)

# ==========================================
# 4. ROSTER ANALYZER (Updated with Robust Parsing)
# ==========================================

@method_decorator(csrf_exempt, name='dispatch') # <--- FIX FOR 403 ERROR
class AnalyzeRosterView(APIView):
    """
    Endpoint for the Roster/Schedule Flutter App.
    Accepts an image, returns a Weekly Schedule JSON.
    Tries Gemini first, falls back to Mistral (Pixtral) if needed.
    """
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        if 'file' not in request.FILES:
            return Response({"error": "No file provided. Key must be 'file'."}, status=400)

        image_file = request.FILES['file']
        
        # --- ENHANCED PROMPT FOR ROBUST JSON ---
        prompt_text = """
        STRICT INSTRUCTION: Act as a structured data extraction API.
        Analyze the timetable/roster image. Extract the schedule for each day of the week.
        Your ENTIRE response MUST be ONLY a single, valid JSON object. DO NOT include ANY commentary, markdown, or surrounding text.

        JSON Format Required:
        {
            "weekly_schedule": {
                "Monday": [ {"time": "10:00", "event": "Math Class"}, {"time": "11:30", "event": "Science Lab"} ],
                "Tuesday": [ {"time": "09:00", "event": "History Lecture"} ]
            }
        }
        If a day has no events, use an empty array. Time format can be HH:MM or AM/PM string.
        """

        analysis_data = None
        source_name = "None"

        # --- ATTEMPT 1: GEMINI VISION ---
        try:
            print("Attempting Roster Scan with Gemini...")
            pil_image = Image.open(image_file)
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            response = model.generate_content([prompt_text, pil_image])
            analysis_data = response.text
            source_name = "Gemini"
            
        except Exception as e_gemini:
            print(f"Gemini Roster Failed: {e_gemini}")

            # --- ATTEMPT 2: MISTRAL VISION (PIXTRAL) ---
            if MISTRAL_KEY:
                try:
                    print("Switching to Mistral Pixtral for Roster...")
                    image_file.seek(0) # Reset file pointer
                    base64_image = encode_image(image_file)
                    
                    client = Mistral(api_key=MISTRAL_KEY)
                    chat_response = client.chat.complete(
                        model="pixtral-12b-2409",
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text}, 
                                {"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"}
                            ]
                        }]
                    )
                    analysis_data = chat_response.choices[0].message.content
                    source_name = "Mistral"
                except Exception as e_mistral:
                    print(f"Mistral Roster Failed: {e_mistral}")

        # --- FINAL PROCESSING ---
        if analysis_data:
            try:
                # 1. Aggressively clean the JSON output 
                clean_json = analysis_data.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json.split('\n', 1)[-1].strip()
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3].strip()

                data = json.loads(clean_json)
                
                # 2. STRICT VALIDATION: Check for the required top-level key
                if 'weekly_schedule' not in data or not isinstance(data['weekly_schedule'], dict):
                    # If AI returned JSON but without the key, raise an error
                    raise ValueError("'weekly_schedule' key is missing or not a dictionary.")

                data['ai_source'] = source_name 
                return Response(data)
                
            except Exception as e:
                # If JSON parsing or key check fails, return a specific error
                print(f"JSON Structure Error: {e}")
                return Response({
                    "error": f"AI returned unusable data. Failed to parse final JSON ({source_name}).", 
                    "raw_output": analysis_data
                }, status=500)
        
        return Response({"error": "All AI services failed to analyze the roster."}, status=500)

# ==========================================
# 5. USER PROFILE & MEAL PLANNING
# ==========================================

@csrf_exempt
@api_view(['POST', 'GET'])
@authentication_classes([])
@permission_classes([])
def user_profile_view(request):
    # ... (Your existing Profile Logic) ...
    if not User.objects.exists():
        try: User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        except: pass 
    user = User.objects.first()
    profile, _ = UserProfile.objects.get_or_create(user=user)

    if request.method == 'GET':
        return Response(UserProfileSerializer(profile).data)

    if request.method == 'POST':
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Profile updated"})
        return Response(serializer.errors, status=400)

@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def generate_meal_plan(request):
    """
    Generates a full day's meal plan based on Goal, Calories, and Context.
    """
    user_goal = request.data.get('user_goal', 'Maintain')
    calories = request.data.get('daily_calories', 2000)
    context = request.data.get('activity_context', 'Standard Day')
    ingredients = request.data.get('available_ingredients', [])
    
    prompt = f"""
    You are an elite sports nutritionist. Create a 1-day meal plan.
    GOAL: {user_goal}
    TARGET CALORIES: {calories}
    CONTEXT: {context} (e.g. if 'Sore', add anti-inflammatory foods. If 'Exam', add brain foods).
    PANTRY: Use these if possible: {', '.join(ingredients)}
    
    Output strictly valid JSON with this structure:
    {{
        "analysis": "Brief explanation of why this plan fits the context.",
        "meals": [
            {{
                "type": "Breakfast",
                "name": "Dish Name",
                "calories": 500,
                "nutrients": {{"protein": "30g", "carbs": "40g", "fat": "15g"}},
                "ingredients": ["Egg", "Bread"],
                "recipe": ["Step 1", "Step 2"]
            }}
        ]
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(prompt)
        clean_json = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
        return Response(data)
    except Exception as e:
        return Response({"error": "Failed to generate plan. AI might be busy."}, status=500)

@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def swap_meal(request):
    """
    Swaps a SINGLE meal for a new option while keeping the context.
    """
    context = request.data.get('activity_context', 'Standard Day')
    user_goal = request.data.get('user_goal', 'Maintain')
    
    prompt = f"""
    Suggest ONE alternative meal for a user with Goal: {user_goal} and Context: {context}.
    Return strictly valid JSON for a single meal object:
    {{
        "name": "New Dish Name",
        "calories": 500,
        "nutrients": {{"protein": "30g", "carbs": "40g", "fat": "15g"}},
        "ingredients": ["List", "of", "items"],
        "recipe": ["Step 1", "Step 2"]
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(prompt)
        clean_json = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
        return Response(data)
    except Exception as e:
        return Response({"error": str(e)}, status=500)