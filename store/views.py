from rest_framework.decorators import api_view, parser_classes, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone
import os
import base64
import json
import re 

# --- HYBRID LIBRARIES ---
from openai import OpenAI 
import google.generativeai as genai 

# --- IMPORTS ---
from .models import FoodItem, UserProfile, FoodKnowledge 
from .serializers import FoodItemSerializer, UserProfileSerializer

# --- CONFIGURATION ---
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY") 
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY") 

SITE_URL = "https://nutrichoice.onrender.com"
APP_NAME = "NutriChoice"

def normalize_food_name(name):
    if not name: return "unknown"
    clean = name.lower().strip()
    return clean

def encode_image(image_file):
    image_file.seek(0)
    return base64.b64encode(image_file.read()).decode('utf-8')

def safe_json_extract(text):
    if not text: return None
    text = re.sub(r"```[a-z]*", "", text).replace("```", "").strip()
    try: return json.loads(text)
    except: pass
    try:
        fixed_text = re.sub(r'(?<!")(\b\w+\b)(?=\s*:)', r'"\1"', text)
        fixed_text = re.sub(r'(:\s*)([a-zA-Z_]\w*)(?=\s*[,}])', r'\1"\2"', fixed_text)
        return json.loads(fixed_text)
    except: return None

# =========================================================================
# 1. SMART SCANNER (Google -> Mistral -> OpenRouter)
# =========================================================================
@method_decorator(csrf_exempt, name='dispatch')
class ScanFoodView(APIView):
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        image_file = request.FILES.get('image')
        text_query = request.data.get('food_name') or request.data.get('query')
        
        data = None
        source_used = "None"
        food_name_normalized = ""

        if image_file:
            print("📸 IMAGE SCAN: Processing...")
            b64 = encode_image(image_file)
            prompt = """Analyze this food. Return STRICT JSON: { "food_name": "Paneer", "estimated_calories": 300, "protein": 10, "carbs": 20, "fat": 15, "ingredients": ["paneer"], "confidence_score": 90 }"""
            
            # 1. GOOGLE DIRECT (Vision)
            if GOOGLE_KEY:
                genai.configure(api_key=GOOGLE_KEY)
                try:
                    model = genai.GenerativeModel('gemini-2.0-flash-exp')
                    res = model.generate_content(
                        [{'mime_type': 'image/jpeg', 'data': b64}, prompt],
                        generation_config={"response_mime_type": "application/json"}
                    )
                    if res.text:
                        data = safe_json_extract(res.text)
                        source_used = "Google Vision (Gemini 2.0)"
                except Exception as e: print(f"   ❌ Google Failed: {e}")

            # 2. MISTRAL DIRECT (Pixtral Vision)
            if not data and MISTRAL_KEY:
                try:
                    print("   👉 Trying Mistral Direct (Pixtral)...")
                    client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=MISTRAL_KEY)
                    res = client.chat.completions.create(
                        model="pixtral-12b-2409",
                        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]
                    )
                    data = safe_json_extract(res.choices[0].message.content)
                    source_used = "Mistral Direct (Pixtral)"
                except Exception as e: print(f"   ❌ Mistral Failed: {e}")

            # 3. OPENROUTER (Fallback)
            if not data and OPENROUTER_KEY:
                try:
                    print("   👉 Trying OpenRouter Fallback...")
                    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
                    res = client.chat.completions.create(
                        model="google/gemini-2.0-flash-exp:free",
                        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]
                    )
                    data = safe_json_extract(res.choices[0].message.content)
                    source_used = "OpenRouter Vision"
                except: pass

        elif text_query:
            food_name_normalized = normalize_food_name(str(text_query))
            print(f"🔍 TEXT SCAN: Checking '{food_name_normalized}'...")
            
            cached = FoodKnowledge.objects.filter(name__iexact=food_name_normalized).first()
            if cached:
                print(f"⚡ CACHE HIT: {cached.name}")
                return Response({
                    "saved_data": { "food_name": cached.name.title(), "estimated_calories": cached.calories, "protein": cached.protein, "carbs": cached.carbs, "fat": cached.fat, "ingredients": cached.ingredients },
                    "source": "Local Knowledge Base"
                })

            prompt = f"Analyze '{food_name_normalized}'. JSON: {{ \"food_name\": \"{food_name_normalized}\", \"estimated_calories\": 0, \"protein\": 0, \"carbs\": 0, \"fat\": 0, \"ingredients\": [] }}"
            
            if GOOGLE_KEY:
                try:
                    genai.configure(api_key=GOOGLE_KEY)
                    model = genai.GenerativeModel('gemini-2.0-flash-exp')
                    res = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                    data = safe_json_extract(res.text)
                    if data: source_used = "Google Text"
                except: pass

            if not data and MISTRAL_KEY:
                try:
                    client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=MISTRAL_KEY)
                    res = client.chat.completions.create(
                        model="mistral-small-latest",
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"}
                    )
                    data = safe_json_extract(res.choices[0].message.content)
                    source_used = "Mistral Direct"
                except: pass

            if not data and OPENROUTER_KEY:
                try:
                    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
                    res = client.chat.completions.create(
                        model="google/gemini-2.0-flash-exp:free",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    data = safe_json_extract(res.choices[0].message.content)
                    source_used = "OpenRouter Text"
                except: pass

        if data:
            name = normalize_food_name(data.get('food_name', 'Unknown'))
            try:
                c_raw = str(data.get('estimated_calories', 0))
                c_clean = "".join(filter(str.isdigit, c_raw))
                cals = int(c_clean) if c_clean else 0
                prot = float(data.get('protein', 0))
                carbs = float(data.get('carbs', 0))
                fat = float(data.get('fat', 0))
                ingredients = data.get('ingredients', [])
            except: cals, prot, carbs, fat, ingredients = 0, 0, 0, 0, []

            if name != "unknown":
                fk = None
                if cals > 0:
                    fk, _ = FoodKnowledge.objects.update_or_create(
                        name=name,
                        defaults={'calories': cals, 'protein': prot, 'carbs': carbs, 'fat': fat, 'ingredients': ingredients, 'source': source_used}
                    )
                else:
                    fk = FoodKnowledge.objects.filter(name=name).first()

                FoodItem.objects.create(
                    user=request.user if request.user.is_authenticated else None, 
                    name=name.title(), 
                    calories=cals, protein=prot, carbs=carbs, fat=fat, 
                    knowledge_source=fk
                )

            return Response({
                "message": "Success", 
                "saved_data": { "id": 0, "food_name": name.title(), "estimated_calories": cals, "protein": prot, "carbs": carbs, "fat": fat, "ingredients": ingredients }, 
                "source": source_used
            })
        
        return Response({"error": "AI Busy. Manual entry required."}, 422)

# =========================================================================
# 2. SMART MEAL PLANNER (With Recipe & Macros)
# =========================================================================
@csrf_exempt
@api_view(['POST'])
def generate_meal_plan(request):
    user = User.objects.first() 
    if not user: return Response({"error": "No user profile"}, 400)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    # 1. EXTRACT DATA
    print("🍱 MEAL PLAN REQUEST:")
    app_target = request.data.get('daily_calories')
    daily_target = int(app_target) if (app_target and int(app_target) > 0) else (profile.daily_calorie_target or 2200)
    context = request.data.get('activity_context', 'Standard')
    ingredients = request.data.get('available_ingredients', [])

    today = timezone.now().date()
    current_hour = timezone.localtime().hour 
    eaten_today = FoodItem.objects.filter(created_at__date=today)
    total_eaten = sum(item.calories for item in eaten_today)
    remaining_cals = daily_target - total_eaten
    
    print(f"   - Gap: {remaining_cals} kcal (Target {daily_target})")

    pantry_text = ", ".join(ingredients) if ingredients else "Simple ingredients"
    
    # 2. DETERMINE SCHEDULE (Force Multi-Meal)
    meal_instruction = "Generate at least 3 meals (Breakfast, Lunch, Dinner)."
    if current_hour > 20:
        meal_instruction = "Late Night: Generate 1 light snack."
    elif current_hour > 14:
        meal_instruction = "Afternoon: Generate 2 meals (Snack + Dinner)."
    elif remaining_cals < 500:
        meal_instruction = "Low Calorie: Generate 2 small snacks."

    # 3. PROMPT (Strict Structure)
    prompt = f"""
    You are a professional Nutritionist API. Output strictly valid JSON.
    
    TASK: Plan meals to fill exactly {remaining_cals} calories.
    - Current Time: {current_hour}:00
    - Context: {context}
    - Pantry: {pantry_text}
    - Requirement: {meal_instruction}

    REQUIRED JSON STRUCTURE (Must include 'nutrients' object and 'recipe' list):
    {{
      "analysis": "Brief explanation.",
      "meals": [
        {{
           "name": "Dish Name",
           "time": "Breakfast/Lunch/Dinner",
           "calories": 400,
           "nutrients": {{ "protein": 20, "carbs": 40, "fat": 10 }}, 
           "ingredients": ["Item 1", "Item 2"],
           "recipe": [
              "Step 1: Prep ingredients.",
              "Step 2: Cook method.",
              "Step 3: Serve."
           ]
        }}
      ]
    }}
    """

    plan_text = None
    ai_source = "None"

    # --- 1. GOOGLE DIRECT ---
    if GOOGLE_KEY:
        try:
            print("   👉 1. Trying Google Gemini 2.0...")
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-2.0-flash-exp')
            plan_text = m.generate_content(
                prompt, 
                generation_config={"response_mime_type": "application/json"}
            ).text
            ai_source = "Google Gemini"
        except Exception as e: print(f"   ❌ Google Failed: {e}")

    # --- 2. MISTRAL DIRECT ---
    if not plan_text and MISTRAL_KEY:
        try:
            print("   👉 2. Trying Mistral Direct...")
            client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=MISTRAL_KEY)
            res = client.chat.completions.create(
                model="mistral-small-latest", 
                messages=[
                    {"role": "system", "content": "You are a JSON generator. Always include 'nutrients' object and 'recipe' list."}, 
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            plan_text = res.choices[0].message.content
            ai_source = "Mistral Direct"
        except Exception as e: print(f"   ❌ Mistral Failed: {e}")

    # --- 3. OPENROUTER ---
    if not plan_text and OPENROUTER_KEY:
        try:
            print("   👉 3. Trying OpenRouter Fallback...")
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
            res = client.chat.completions.create(
                model="google/gemini-2.0-flash-exp:free", 
                messages=[{"role": "user", "content": prompt}]
            )
            plan_text = res.choices[0].message.content
            ai_source = "OpenRouter"
        except: pass

    if plan_text:
        print(f"   ✅ AI Success via {ai_source}")
        data = safe_json_extract(plan_text)
        if data and "meals" in data and isinstance(data["meals"], list):
            return Response(data)

    print("   ⚠️ Sending Hard Fallback Meal")
    return Response({
        "analysis": "AI busy. Here is a complete default plan.",
        "meals": [
            { 
                "name": "Masala Oats & Milk", 
                "time": "Breakfast",
                "calories": 350, 
                "nutrients": { "protein": 12, "carbs": 45, "fat": 8 },
                "ingredients": ["Oats", "Milk", "Vegetables", "Spices"],
                "recipe": ["Boil milk and oats.", "Add chopped veggies and spices.", "Cook for 5 mins until thick."]
            },
            { 
                "name": "Paneer Salad", 
                "time": "Lunch",
                "calories": 400, 
                "nutrients": { "protein": 20, "carbs": 15, "fat": 25 },
                "ingredients": ["Paneer", "Cucumber", "Tomato", "Lemon"],
                "recipe": ["Cube the paneer.", "Chop vegetables.", "Toss everything with lemon juice and salt."]
            }
        ]
    })

@csrf_exempt
@api_view(['POST'])
def swap_meal(request):
    old_meal = request.data.get('goal', 'Meal') 
    calories = request.data.get('calories', 500)
    context = request.data.get('context', 'Standard')
    
    prompt = f"""
    Suggest replacement for '{old_meal}' (~{calories} kcal). Context: {context}. 
    Return strictly nested JSON with 'nutrients' and 'recipe'.
    
    JSON: {{ "name": "...", "calories": {calories}, "nutrients": {{ "protein": 0, "carbs": 0, "fat": 0 }}, "ingredients": [], "recipe": ["Step 1", "Step 2"] }}
    """
    
    plan_text = None
    if GOOGLE_KEY:
        try:
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-2.0-flash-exp') 
            plan_text = m.generate_content(prompt, generation_config={"response_mime_type": "application/json"}).text
        except: pass
    
    if not plan_text and MISTRAL_KEY:
        try:
            client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=MISTRAL_KEY)
            res = client.chat.completions.create(
                model="mistral-small-latest", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}
            )
            plan_text = res.choices[0].message.content
        except: pass

    if plan_text:
        data = safe_json_extract(plan_text)
        if data: return Response(data)

    return Response({
        "name": "Masala Oats", "calories": calories, 
        "nutrients": { "protein": 8, "carbs": 40, "fat": 5 },
        "ingredients": ["Oats", "Spices"], "recipe": ["Boil water", "Add oats & spices"]
    })

# ==========================================
# 3. ROSTER ANALYZER (Google -> Mistral Pixtral -> OpenRouter)
# ==========================================
@method_decorator(csrf_exempt, name='dispatch') 
class AnalyzeRosterView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        if 'file' not in request.FILES: return Response({"error": "No file"}, 400)
        img = request.FILES['file']
        b64 = encode_image(img)
        
        prompt = """
        Analyze this timetable/roster image. 
        Extract the schedule into strict JSON format.
        JSON Structure: { "weekly_schedule": { "Monday": [{"time": "10:00", "event": "Math"}], "Tuesday": [] } }
        """
        data = None

        # 1. GOOGLE DIRECT
        if GOOGLE_KEY:
            try:
                print("📅 Analyzing Roster (Google)...")
                genai.configure(api_key=GOOGLE_KEY)
                m = genai.GenerativeModel('gemini-2.0-flash-exp')
                res = m.generate_content([{'mime_type': 'image/jpeg', 'data': b64}, prompt], generation_config={"response_mime_type": "application/json"})
                if res.text: data = safe_json_extract(res.text)
            except Exception as e: print(f"   ❌ Google Failed: {e}")

        # 2. MISTRAL DIRECT (Pixtral)
        if not data and MISTRAL_KEY:
            try:
                print("📅 Analyzing Roster (Mistral Pixtral)...")
                client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=MISTRAL_KEY)
                res = client.chat.completions.create(
                    model="pixtral-12b-2409",
                    messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]
                )
                data = safe_json_extract(res.choices[0].message.content)
            except Exception as e: print(f"   ❌ Mistral Failed: {e}")

        if data: return Response(data)
        return Response({"error": "Busy. Please try again in 1 minute."}, 503)

@csrf_exempt 
@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def ai_status_check(request):
    return Response({"Status": "Online"})

class FoodItemList(ListCreateAPIView):
    queryset = FoodItem.objects.all().order_by('-created_at')
    serializer_class = FoodItemSerializer
    authentication_classes = [] 
    permission_classes = []

class FoodItemDetail(RetrieveUpdateDestroyAPIView):
    queryset = FoodItem.objects.all()
    serializer_class = FoodItemSerializer
    authentication_classes = []
    permission_classes = []

@csrf_exempt
@api_view(['POST'])
def ask_nutritionist(request):
    q = request.data.get('question')
    if not q: return Response({"error": "No question"}, 400)
    try:
        if GOOGLE_KEY:
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-2.0-flash-exp') 
            return Response({"answer": m.generate_content(q).text})
    except: return Response({"error": "AI Error"}, 500)

@csrf_exempt
@api_view(['POST', 'GET'])
def user_profile_view(request):
    if settings.DEBUG and not User.objects.exists():
        try: User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        except: pass 
    user = User.objects.first()
    if not user: return Response({"error": "No users"}, 404)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if request.method == 'GET': return Response(UserProfileSerializer(profile).data)
    if request.method == 'POST':
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Updated"})
        return Response(serializer.errors, 400)
