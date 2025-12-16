import logging
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

# --- LOGGER SETUP ---
logger = logging.getLogger(__name__)

# --- HELPERS ---
def normalize_food_name(name):
    if not name: return "unknown"
    return name.lower().strip()

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

# --- SAFETY NET FUNCTION ---
def enrich_meal_data(meal):
    if 'name' not in meal: meal['name'] = "Healthy Choice"
    cals = meal.get('calories', 400)
    if isinstance(cals, str): 
        cals = int("".join(filter(str.isdigit, cals)) or 400)
    meal['calories'] = cals

    if 'recipe' not in meal or not meal['recipe']:
        name_lower = meal['name'].lower()
        if "salad" in name_lower: meal['recipe'] = ["Chop vegetables.", "Mix in bowl.", "Add dressing.", "Serve."]
        elif "oats" in name_lower: meal['recipe'] = ["Boil liquid.", "Add oats.", "Cook 5 mins.", "Add toppings."]
        else: meal['recipe'] = ["Prep ingredients.", "Cook main protein.", "Combine sides.", "Serve warm."]

    nutrients = meal.get('nutrients', {})
    def get_val(v):
        if isinstance(v, (int, float)): return int(v)
        if isinstance(v, str) and v.isdigit(): return int(v)
        return 0

    p = get_val(nutrients.get('protein', 0))
    f = get_val(nutrients.get('fat', 0))
    c = get_val(nutrients.get('carbs', 0))

    if p + f + c < 5:
        p = int((cals * 0.30) / 4)
        f = int((cals * 0.30) / 9)
        c = int((cals * 0.40) / 4)
    else:
        macro_cals = (p * 4) + (c * 4) + (f * 9)
        if macro_cals > 0:
            scale = cals / macro_cals
            p = int(p * scale)
            c = int(c * scale)
            f = int(f * scale)

    meal['nutrients'] = { "protein": p, "fat": f, "carbs": c }
    meal['protein'] = p
    meal['fat'] = f
    meal['carbs'] = c
    return meal

def get_user_safe(request):
    if request.user.is_authenticated:
        return request.user
    return User.objects.first()

# =========================================================================
# 1. SMART SCANNER
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

        if image_file:
            logger.info("📸 IMAGE SCAN: Processing started...")
            b64 = encode_image(image_file)
            prompt = """Analyze food. JSON: { "food_name": "Paneer", "estimated_calories": 300, "protein": 10, "carbs": 20, "fat": 15, "ingredients": ["paneer"] }"""
            
            if GOOGLE_KEY:
                try:
                    genai.configure(api_key=GOOGLE_KEY)
                    m = genai.GenerativeModel('gemini-2.0-flash-exp')
                    res = m.generate_content([{'mime_type': 'image/jpeg', 'data': b64}, prompt], generation_config={"response_mime_type": "application/json"})
                    if res.text:
                        data = safe_json_extract(res.text)
                        source_used = "Google Vision"
                except Exception as e:
                    logger.error(f"❌ Google Vision Failed: {e}")

            if not data and MISTRAL_KEY:
                try: 
                    client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=MISTRAL_KEY)
                    res = client.chat.completions.create(model="pixtral-12b-2409", messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}])
                    data = safe_json_extract(res.choices[0].message.content)
                    source_used = "Mistral Vision"
                except Exception as e:
                    logger.error(f"❌ Mistral Vision Failed: {e}")

        elif text_query:
            logger.info(f"🔍 TEXT SCAN: {text_query}")
            prompt = f"Analyze '{text_query}'. JSON: {{ \"food_name\": \"{text_query}\", \"estimated_calories\": 200, \"protein\": 10, \"carbs\": 20, \"fat\": 5, \"ingredients\": [] }}"
            
            name_clean = normalize_food_name(str(text_query))
            cached = FoodKnowledge.objects.filter(name__iexact=name_clean).first()
            if cached:
                logger.info(f"⚡ CACHE HIT: {name_clean}")
                return Response({
                    "saved_data": { "food_name": cached.name.title(), "estimated_calories": cached.calories, "protein": cached.protein, "carbs": cached.carbs, "fat": cached.fat, "ingredients": cached.ingredients },
                    "source": "Local Cache"
                })

            if GOOGLE_KEY:
                try:
                    genai.configure(api_key=GOOGLE_KEY)
                    m = genai.GenerativeModel('gemini-2.0-flash-exp')
                    res = m.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                    data = safe_json_extract(res.text)
                    source_used = "Google Text"
                except Exception as e:
                    logger.error(f"❌ Google Text Scan Failed: {e}")

        if data:
            name = normalize_food_name(data.get('food_name', 'Unknown'))
            cals = int(data.get('estimated_calories', 0))
            if name != "unknown":
                fk = None
                ingredients = data.get('ingredients', [])
                if not isinstance(ingredients, list) or len(ingredients) < 2:
                    ingredients = [] 

                if cals > 0:
                    fk, _ = FoodKnowledge.objects.update_or_create(
                        name=name, 
                        defaults={'calories': cals, 'protein': data.get('protein',0), 'carbs': data.get('carbs',0), 'fat': data.get('fat',0), 'ingredients': ingredients, 'source': source_used}
                    )
                else:
                    fk = FoodKnowledge.objects.filter(name=name).first()
                
                user = get_user_safe(request)
                FoodItem.objects.create(user=user, name=name.title(), calories=cals, protein=data.get('protein',0), carbs=data.get('carbs',0), fat=data.get('fat',0), knowledge_source=fk)
            
            return Response({"message": "Success", "saved_data": data, "source": source_used})
        
        return Response({"error": "Scan failed"}, 422)

# =========================================================================
# 2. SMART MEAL PLANNER
# =========================================================================
@csrf_exempt
@api_view(['POST'])
def generate_meal_plan(request):
    user = get_user_safe(request)
    if not user: return Response({"error": "No user"}, 400)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    app_target = request.data.get('daily_calories')
    daily_target = int(app_target) if (app_target and int(app_target) > 0) else (profile.daily_calorie_target or 2200)
    context = request.data.get('activity_context', 'Standard')
    ingredients = request.data.get('available_ingredients', [])

    today = timezone.now().date()
    current_hour = timezone.localtime().hour 
    eaten_today = FoodItem.objects.filter(created_at__date=today)
    total_eaten = sum(item.calories for item in eaten_today)
    
    remaining_cals = daily_target - total_eaten
    remaining_cals = max(remaining_cals, 200) 
    
    logger.info(f"🍱 MEAL PLAN REQ: Target {daily_target} | Eaten {total_eaten} | Gap {remaining_cals}")

    meal_instruction = "Generate 3 meals (Breakfast, Lunch, Dinner)."
    if current_hour > 20: meal_instruction = "Late Night: 1 light snack."
    elif current_hour > 14: meal_instruction = "Afternoon: 2 meals (Snack + Dinner)."
    elif remaining_cals < 500: meal_instruction = "Low Calorie: 2 small snacks."

    prompt = f"""
    Act as a Nutritionist. Output strict JSON.
    TASK: Plan meals to fill exactly {remaining_cals} calories.
    - Time: {current_hour}:00
    - Context: {context}
    - Schedule: {meal_instruction}
    - Ingredients: {", ".join(ingredients)}

    REQUIRED JSON:
    {{
      "analysis": "Brief reason.",
      "meals": [
        {{
           "name": "Dish Name",
           "time": "Breakfast/Lunch/Dinner",
           "calories": 400,
           "nutrients": {{ "protein": 20, "carbs": 40, "fat": 10 }}, 
           "ingredients": ["Item 1", "Item 2"],
           "recipe": ["Step 1", "Step 2", "Step 3"]
        }}
      ]
    }}
    """

    plan_text = None
    if GOOGLE_KEY:
        try:
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-2.0-flash-exp')
            plan_text = m.generate_content(prompt, generation_config={"response_mime_type": "application/json"}).text
        except Exception as e:
            logger.error(f"❌ Google Meal Plan Failed: {e}")

    if not plan_text and MISTRAL_KEY:
        try:
            client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=MISTRAL_KEY)
            res = client.chat.completions.create(model="mistral-small-latest", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
            plan_text = res.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ Mistral Meal Plan Failed: {e}")

    if not plan_text and OPENROUTER_KEY:
        try:
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
            res = client.chat.completions.create(model="google/gemini-2.0-flash-exp:free", messages=[{"role": "user", "content": prompt}])
            plan_text = res.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ OpenRouter Meal Plan Failed: {e}")

    if plan_text:
        data = safe_json_extract(plan_text)
        if data and "meals" in data and isinstance(data["meals"], list):
            data['meals'] = data['meals'][:3] 
            data['meals'] = [enrich_meal_data(m) for m in data['meals']]
            return Response(data)

    logger.warning("⚠️ All AI Providers failed. Returning fallback meal plan.")
    return Response({
        "analysis": "AI busy. Default plan loaded.",
        "meals": [
            enrich_meal_data({ "name": "Oats & Milk", "calories": 350, "time": "Breakfast" }),
            enrich_meal_data({ "name": "Chicken Salad", "calories": 450, "time": "Lunch" })
        ]
    })

@csrf_exempt
@api_view(['POST'])
def swap_meal(request):
    old_meal = request.data.get('goal', 'Meal') 
    calories = request.data.get('calories', 500)
    context = request.data.get('context', 'Standard')
    prompt = f"Suggest replacement for '{old_meal}' (~{calories} kcal). Context: {context}. JSON: {{ \"name\": \"...\", \"calories\": {calories}, \"nutrients\": {{ \"protein\": 0, \"carbs\": 0, \"fat\": 0 }}, \"ingredients\": [], \"recipe\": [] }}"
    
    plan_text = None
    if GOOGLE_KEY:
        try:
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-2.0-flash-exp') 
            plan_text = m.generate_content(prompt, generation_config={"response_mime_type": "application/json"}).text
        except Exception as e:
            logger.error(f"❌ Google Swap Failed: {e}")
    
    if plan_text:
        data = safe_json_extract(plan_text)
        if data: return Response(enrich_meal_data(data))

    return Response(enrich_meal_data({ "name": "Masala Oats", "calories": calories }))

# =========================================================================
# 3. SMART WORKOUT (REAL AI VERSION - DEPLOYMENT V5)
# =========================================================================
@csrf_exempt
@api_view(['POST'])
def generate_workout(request):
    # --- TRACER LOG: Proves the update is live ---
    logger.info("--- 🚀 REAL AI DEPLOYMENT LIVE: Generating Workout... ---")
    
    context_data = request.data.get('context', 'General Fitness')
    
    # 2. Prompt for AI
    prompt = f"""
    Act as an elite Coach.
    CLIENT CONTEXT: {context_data}
    
    TASK: Create a workout session.
    OUTPUT STRICT JSON ONLY:
    {{
      "advice": "1 sentence coaching tip.",
      "exercises": [
        {{ "name": "Exercise Name", "sets": 3, "reps": "10-12" }}
      ]
    }}
    """

    plan_text = None
    
    # 3. Try AI Providers
    if GOOGLE_KEY:
        try:
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-2.0-flash-exp')
            plan_text = m.generate_content(prompt, generation_config={"response_mime_type": "application/json"}).text
        except Exception as e:
            logger.error(f"❌ Google Workout Failed: {e}")

    if not plan_text and MISTRAL_KEY:
        try:
            client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=MISTRAL_KEY)
            res = client.chat.completions.create(
                model="mistral-small-latest", 
                messages=[{"role": "user", "content": prompt}], 
                response_format={"type": "json_object"}
            )
            plan_text = res.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ Mistral Workout Failed: {e}")

    # 4. Parse & Return
    if plan_text:
        data = safe_json_extract(plan_text)
        if data and "exercises" in data:
            # Type Safety
            for ex in data.get("exercises", []):
                try: ex["sets"] = int(ex.get("sets", 3))
                except: ex["sets"] = 3
            return Response(data)

    # 5. Fallback
    logger.warning("⚠️ All AI Providers failed. Returning fallback workout.")
    return Response({
        "advice": "AI busy. Here is a balanced session.",
        "exercises": [
            { "name": "Bodyweight Squats", "sets": 3, "reps": "15" },
            { "name": "Push-ups", "sets": 3, "reps": "10-12" },
            { "name": "Plank", "sets": 3, "reps": "45 sec" }
        ]
    })

# ==========================================
# 4. ROSTER ANALYZER
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
        prompt = "Analyze timetable. JSON: { \"weekly_schedule\": { \"Monday\": [{\"time\": \"10:00\", \"event\": \"Math\"}] } }"
        
        if GOOGLE_KEY:
            try:
                logger.info("📅 Roster Analysis: Trying Google...")
                genai.configure(api_key=GOOGLE_KEY)
                m = genai.GenerativeModel('gemini-2.0-flash-exp')
                res = m.generate_content([{'mime_type': 'image/jpeg', 'data': b64}, prompt], generation_config={"response_mime_type": "application/json"})
                if res.text: return Response(safe_json_extract(res.text))
            except Exception as e:
                logger.error(f"❌ Google Roster Failed: {e}")

        if MISTRAL_KEY:
            try:
                logger.info("📅 Roster Analysis: Trying Mistral...")
                client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=MISTRAL_KEY)
                res = client.chat.completions.create(model="pixtral-12b-2409", messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}])
                return Response(safe_json_extract(res.choices[0].message.content))
            except Exception as e:
                logger.error(f"❌ Mistral Roster Failed: {e}")

        return Response({"error": "Busy"}, 503)

# ... Standard Views ...
@csrf_exempt 
@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def ai_status_check(request): return Response({"Status": "Online"})

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
    except Exception as e:
        logger.error(f"Chat AI Error: {e}")
        return Response({"error": "AI Error"}, 500)

@csrf_exempt
@api_view(['POST', 'GET'])
def user_profile_view(request):
    user = get_user_safe(request)
    if not user: return Response({"error": "No users"}, 404)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if request.method == 'GET': return Response(UserProfileSerializer(profile).data)
    if request.method == 'POST':
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Updated"})
        return Response(serializer.errors, 400)