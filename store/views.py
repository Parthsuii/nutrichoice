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
# 1. SMART SCANNER (Google -> OpenRouter -> Qwen/Llama)
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
            
            if GOOGLE_KEY:
                genai.configure(api_key=GOOGLE_KEY)
                try:
                    model = genai.GenerativeModel('gemini-2.0-flash-exp')
                    res = model.generate_content([{'mime_type': 'image/jpeg', 'data': b64}, prompt])
                    if res.text:
                        data = safe_json_extract(res.text)
                        source_used = "Google Vision (Gemini 2.0)"
                except Exception as e: print(f"Google Failed: {e}")

            if not data and OPENROUTER_KEY:
                try:
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
            
            # 1. Check Cache
            cached = FoodKnowledge.objects.filter(name__iexact=food_name_normalized).first()
            if cached:
                print(f"⚡ CACHE HIT: {cached.name}")
                return Response({
                    "saved_data": {
                        "food_name": cached.name.title(),
                        "estimated_calories": cached.calories,
                        "protein": cached.protein,
                        "carbs": cached.carbs,
                        "fat": cached.fat,
                        "ingredients": cached.ingredients
                    },
                    "source": "Local Knowledge Base"
                })

            # 2. AI Fetch
            prompt = f"Analyze '{food_name_normalized}'. JSON: {{ \"food_name\": \"{food_name_normalized}\", \"estimated_calories\": 0, \"protein\": 0, \"carbs\": 0, \"fat\": 0, \"ingredients\": [] }}"
            
            if GOOGLE_KEY:
                try:
                    genai.configure(api_key=GOOGLE_KEY)
                    model = genai.GenerativeModel('gemini-2.0-flash-exp')
                    res = model.generate_content(prompt)
                    data = safe_json_extract(res.text)
                    if data: source_used = "Google Text"
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
                # --- FIX: SAFE CACHE UPDATE ---
                # Only update global knowledge if we found valid calories (>0)
                # This prevents AI hallucinations (0 cal) from poisoning the DB
                fk = None
                if cals > 0:
                    fk, _ = FoodKnowledge.objects.update_or_create(
                        name=name,
                        defaults={'calories': cals, 'protein': prot, 'carbs': carbs, 'fat': fat, 'ingredients': ingredients, 'source': source_used}
                    )
                else:
                    # If AI failed to get cals, try to find existing knowledge without overwriting
                    fk = FoodKnowledge.objects.filter(name=name).first()

                # Create user log regardless
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
# 2. SMART MEAL PLANNER (Mistral Fallback + App Priority)
# =========================================================================
@csrf_exempt
@api_view(['POST'])
def generate_meal_plan(request):
    user = User.objects.first() 
    if not user: return Response({"error": "No user profile"}, 400)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    # 1. PRIORITY: App Data > DB Data
    print("🍱 MEAL PLAN REQUEST:")
    print(f"   - App Calories: {request.data.get('daily_calories')}")
    print(f"   - Context: {request.data.get('activity_context')}")
    
    app_target = request.data.get('daily_calories')
    daily_target = int(app_target) if app_target else (profile.daily_calorie_target or 2200)
    context = request.data.get('activity_context', 'Standard')
    ingredients = request.data.get('available_ingredients', [])

    today = timezone.now().date()
    current_hour = timezone.localtime().hour 
    eaten_today = FoodItem.objects.filter(created_at__date=today)
    total_eaten = sum(item.calories for item in eaten_today)
    remaining_cals = daily_target - total_eaten
    
    print(f"   - Gap: {remaining_cals} kcal")

    prompt = f"""
    Act as a Michelin Star Nutritionist.
    
    CLIENT DATA:
    - Target: {daily_target} kcal
    - Eaten: {total_eaten} kcal
    - REMAINING TO FILL: {remaining_cals} kcal (Important!)
    - Current Time: {current_hour}:00
    - Mode: {context} (Adjust macros based on this).
    - Pantry: {', '.join(ingredients) if ingredients else 'Any common ingredients'}
    
    INSTRUCTIONS:
    1. If remaining calories are low (< 200), suggest a light snack.
    2. If remaining calories are high (> 600), suggest a full meal.
    3. Use the Pantry ingredients if possible.
    
    OUTPUT JSON ONLY:
    {{
      "analysis": "1 sentence on why this fits.",
      "meals": [
        {{ 
           "name": "Creative Dish Name", 
           "calories": 450, "protein": 25, "carbs": 40, "fat": 15, 
           "time": "Dinner",
           "ingredients": ["Item 1", "Item 2"],
           "recipe": ["Step 1", "Step 2"]
        }}
      ]
    }}
    """
    
    plan_text = None

    # ATTEMPT 1: Google Gemini 2.0 (Fastest)
    if GOOGLE_KEY:
        try:
            print("   -> Trying Google Gemini 2.0...")
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-2.0-flash-exp')
            plan_text = m.generate_content(prompt).text
        except Exception as e: print(f"   x Google Failed: {e}")

    # ATTEMPT 2: OpenRouter (Gemini)
    if not plan_text and OPENROUTER_KEY:
        try:
            print("   -> Trying OpenRouter Gemini...")
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
            res = client.chat.completions.create(
                model="google/gemini-2.0-flash-exp:free", 
                messages=[{"role": "user", "content": prompt}]
            )
            plan_text = res.choices[0].message.content
        except: pass

    # ATTEMPT 3: OpenRouter (MISTRAL 7B - Reliable JSON)
    if not plan_text and OPENROUTER_KEY:
        try:
            print("   -> Trying MISTRAL (Fallback)...")
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
            res = client.chat.completions.create(
                model="mistralai/mistral-7b-instruct:free", 
                messages=[{"role": "user", "content": prompt}]
            )
            plan_text = res.choices[0].message.content
        except: pass

    if plan_text:
        data = safe_json_extract(plan_text)
        if data and "meals" in data:
            return Response(data)

    print("   ⚠️ Sending Hard Fallback Meal")
    return Response({
        "analysis": "AI was unreachable. Here is a balanced default option.",
        "meals": [
            { 
                "name": "Quick Protein Oats", 
                "calories": 300, "protein": 15, "carbs": 35, "fat": 6, 
                "time": "Anytime",
                "ingredients": ["Oats", "Milk", "Peanut Butter"],
                "recipe": ["Boil oats in milk.", "Stir in peanut butter.", "Serve warm."]
            }
        ]
    })

@csrf_exempt
@api_view(['POST'])
def swap_meal(request):
    old_meal = request.data.get('goal', 'Meal') 
    calories = request.data.get('calories', 500)
    context = request.data.get('context', 'Standard')
    
    prompt = f"Suggest ONE vegetarian Indian replacement for '{old_meal}' (~{calories} kcal). Context: {context}. Return JSON: {{ \"name\": \"...\", \"calories\": {calories}, \"protein\": 0, \"carbs\": 0, \"fat\": 0, \"ingredients\": [], \"recipe\": [] }}"
    
    try:
        if GOOGLE_KEY:
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-2.0-flash-exp') 
            res = m.generate_content(prompt)
            data = safe_json_extract(res.text)
            if data: return Response(data)
    except: pass
    
    return Response({
        "name": "Masala Oats", "calories": calories, "protein": 8, "carbs": 40, "fat": 5, 
        "ingredients": ["Oats", "Spices"], "recipe": ["Boil water", "Add oats & spices"]
    })

# ==========================================
# 3. ROSTER ANALYZER (Google -> Qwen-2-VL)
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
        If text is unclear, guess based on layout.
        """
        data = None

        if GOOGLE_KEY:
            try:
                print("📅 Analyzing Roster with Gemini 2.0...")
                genai.configure(api_key=GOOGLE_KEY)
                m = genai.GenerativeModel('gemini-2.0-flash-exp')
                r = m.generate_content([{'mime_type': 'image/jpeg', 'data': b64}, prompt])
                if r.text: data = safe_json_extract(r.text)
            except Exception as e: print(f"⚠️ Google Roster Failed: {e}")

        if not data and OPENROUTER_KEY:
            try:
                client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
                try:
                    print("📅 Switching to OpenRouter (Gemini)...")
                    res = client.chat.completions.create(
                        model="google/gemini-2.0-flash-exp:free",
                        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]
                    )
                    data = safe_json_extract(res.choices[0].message.content)
                except: 
                    # --- FIX: SWAP PIXTRAL FOR QWEN-2-VL ---
                    print("⚠️ OpenRouter Gemini Failed. Trying Qwen-2-VL (More Stable)...")
                    res = client.chat.completions.create(
                        model="qwen/qwen-2-vl-7b-instruct:free", 
                        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]
                    )
                    data = safe_json_extract(res.choices[0].message.content)
            except Exception as e: print(f"⚠️ OpenRouter Failed: {e}")

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