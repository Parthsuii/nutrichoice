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
    # This function is correct and already used.
    image_file.seek(0) # Ensure pointer is at the start
    return base64.b64encode(image_file.read()).decode('utf-8')

# ==========================================
# 1. STANDARD CRUD VIEWS (FOOD ITEMS)
# ... (UNMODIFIED)
# ==========================================

class FoodItemList(ListCreateAPIView):
    queryset = FoodItem.objects.all()
    serializer_class = FoodItemSerializer
    authentication_classes = [] 
    permission_classes = []

class FoodItemDetail(RetrieveUpdateDestroyAPIView):
    queryset = FoodItem.objects.all()
    serializer_class = FoodItemSerializer
    authentication_classes = []
    permission_classes = []

# ==========================================
# 2. AI TEXT ENDPOINT (Nutrition Q&A)
# ... (UNMODIFIED)
# ==========================================

@csrf_exempt
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
# ... (UNMODIFIED)
# ==========================================

@method_decorator(csrf_exempt, name='dispatch')
class ScanFoodView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = [] 
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
# 4. ROSTER ANALYZER (Updated with Groq Two-Step Fallback)
# ==========================================

@method_decorator(csrf_exempt, name='dispatch') 
class AnalyzeRosterView(APIView):
    """
    Endpoint for the Roster/Schedule Flutter App.
    Accepts an image, returns a Weekly Schedule JSON.
    Tries Gemini, then Mistral, then Groq (2-step process).
    """
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        if 'file' not in request.FILES:
            return Response({"error": "No file provided. Key must be 'file'."}, status=400)

        image_file = request.FILES['file']
        
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
        
        # --- Store current file position ---
        original_file_position = image_file.tell()

        # --- ATTEMPT 1: GEMINI VISION ---
        try:
            print("Attempting Roster Scan with Gemini...")
            image_file.seek(0)
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
                    image_file.seek(0)
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

            # --- ATTEMPT 3 (NEW): GROQ Text Extraction + JSON Conversion ---
            if GROQ_KEY and not analysis_data:
                try:
                    print("Switching to GROQ/Gemini Combo (Two-Step OCR)...")
                    image_file.seek(0)
                    base64_image = encode_image(image_file)
                    
                    # Step 1: Groq for raw text extraction
                    raw_text_prompt = "Extract all text and tabular schedule data from this image, listing the day, time, and event clearly. Do not format as JSON."
                    client = Groq(api_key=GROQ_KEY)
                    raw_completion = client.chat.completions.create(
                        model="llama3-8b-8192", 
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": raw_text_prompt}, 
                                {"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"}
                            ]
                        }]
                    )
                    raw_text_output = raw_completion.choices[0].message.content
                    
                    # Step 2: Gemini for reliable text-to-JSON conversion
                    json_prompt = f"""
                    STRICTLY CONVERT the following raw schedule data into the requested JSON format. 
                    RAW DATA: {raw_text_output}
                    JSON FORMAT: {prompt_text}
                    """
                    model = genai.GenerativeModel('gemini-2.0-flash-exp')
                    json_response = model.generate_content(json_prompt)
                    analysis_data = json_response.text
                    source_name = "Groq/Gemini"
                    
                except Exception as e_groq_combo:
                    print(f"GROQ/Gemini Combo Failed: {e_groq_combo}")

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
                if 'weekly_schedule' not in data or not isinstance(data.get('weekly_schedule'), dict):
                    # If AI returned JSON but without the required key, this means the extraction failed.
                    raise ValueError("AI returned JSON but structure is invalid or missing 'weekly_schedule' key.")

                data['ai_source'] = source_name 
                return Response(data)
                
            except Exception as e:
                # If JSON parsing or key check fails, return a specific error
                print(f"JSON Structure Error: {e}")
                return Response({
                    "error": f"AI returned unusable data. Failed to parse final JSON ({source_name}).", 
                    "raw_output": analysis_data # Return the raw output for debugging
                }, status=500)
        
        # This will be hit if ALL three attempts failed to produce extractable data
        return Response({"error": "All AI services failed to analyze the roster."}, status=500)

# ==========================================
# 5. USER PROFILE & MEAL PLANNING
# ... (UNMODIFIED)
# ==========================================

@csrf_exempt
@api_view(['POST', 'GET'])
@authentication_classes([])
@permission_classes([])
def user_profile_view(request):
    # ... (Logic remains the same) ...
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
    # ... (Logic remains the same) ...
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
    # ... (Logic remains the same) ...
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