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

# --- SAFETY NET FUNCTION (Improved Logic) ---
def enrich_meal_data(meal):
    """Ensures every meal has a recipe and valid nutrients."""
    # 1. Ensure Name
    if 'name' not in meal: meal['name'] = "Healthy Choice"
    
    # 2. Ensure Calories
    cals = meal.get('calories', 400)
    if isinstance(cals, str): 
        # Extract digits if string provided (e.g. "400 kcal")
        cals = int("".join(filter(str.isdigit, cals)) or 400)
    meal['calories'] = cals

    # 3. Ensure Recipe
    if 'recipe' not in meal or not meal['recipe']:
        name_lower = meal['name'].lower()
        if "salad" in name_lower:
            meal['recipe'] = ["Chop all vegetables.", "Mix in a bowl.", "Add dressing.", "Serve fresh."]
        elif "shake" in name_lower or "smoothie" in name_lower:
            meal['recipe'] = ["Add ingredients to blender.", "Blend until smooth.", "Pour and serve."]
        elif "oats" in name_lower:
            meal['recipe'] = ["Boil liquid.", "Add oats.", "Cook for 5 mins.", "Add toppings."]
        else:
            meal['recipe'] = ["Prep ingredients.", "Cook main protein.", "Combine with sides.", "Serve warm."]

    # 4. Ensure Nutrients (Zero-Check Improvement)
    nutrients = meal.get('nutrients', {})
    # Calculate sum safely handling potential strings
    total_val = 0
    try:
        total_val = sum(int(v) for v in nutrients.values() if isinstance(v, (int, float, str)) and str(v).isdigit())
    except: pass

    # If missing or effectively zero, calculate defaults
    if not nutrients or total_val < 5:
        p = int((cals * 0.25) / 4) # 25% Protein
        f = int((cals * 0.30) / 9) # 30% Fat
        c = int((cals * 0.45) / 4) # 45% Carbs
        meal['nutrients'] = { "protein": p, "fat": f, "carbs": c }
    
    # 5. Flatten for Frontend Compatibility
    meal['protein'] = meal['nutrients'].get('protein', 0)
    meal['fat'] = meal['nutrients'].get('fat', 0)
    meal['carbs'] = meal['nutrients'].get('carbs', 0)

    return meal

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
            print("📸 IMAGE SCAN...")
            b64 = encode_image(image_file)
            prompt = """Analyze food. JSON: { "food_name": "Paneer", "estimated_calories": 300, "protein": 10, "carbs": 20, "fat": 15, "ingredients": ["paneer"] }"""
            
            # 1. Google
            if GOOGLE_KEY:
                try:
                    genai.configure(api_key=GOOGLE_KEY)
                    m = genai.GenerativeModel('gemini-2.0-flash-exp')
                    res = m.generate_content([{'mime_type': 'image/jpeg', 'data': b64}, prompt], generation_config={"response_mime_type": "application/json"})
                    if res.text:
                        data = safe_json_extract(res.text)
                        source_used = "Google Vision"
                except: pass
            
            # 2. Mistral Direct (Syntax Fixed)
            if not data and MISTRAL_KEY:
                try: 
                    client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=MISTRAL_KEY)
                    res = client.chat.completions.create(
                        model="pixtral-12b-2409", 
                        messages=[{
                            "role": "user", 
                            "content": [
                                {"type": "text", "text": prompt}, 
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                            ]
                        }] 
                    )
                    data = safe_json_extract(res.choices[0].message.content)
                    source_used = "Mistral Vision"
                except Exception as e: print(f"Mistral Error: {e}")

        elif text_query:
            print(f"🔍 TEXT SCAN: {text_query}")
            prompt = f"Analyze '{text_query}'. JSON: {{ \"food_name\": \"{text_query}\", \"estimated_calories\": 200, \"protein\": 10, \"carbs\": 20, \"fat\": 5, \"ingredients\": [] }}"
            
            # 1. Check Cache
            name_clean = normalize_food_name(str(text_query))
            cached = FoodKnowledge.objects.filter(name__iexact=name_clean).first()
            if cached:
                return Response({
                    "saved_data": { "food_name": cached.name.title(), "estimated_calories": cached.calories, "protein": cached.protein, "carbs": cached.carbs, "fat": cached.fat, "ingredients": cached.ingredients },
                    "source": "Local Cache"
                })

            # 2. Google
            if GOOGLE_KEY:
                try:
                    genai.configure(api_key=GOOGLE_KEY)
                    m = genai.GenerativeModel('gemini-2.0-flash-exp')
                    res = m.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                    data = safe_json_extract(res.text)
                    source_used = "Google Text"
                except: pass

        if data:
            name = normalize_food_name(data.get('food_name', 'Unknown'))
            cals = int(data.get('estimated_calories', 0))
            if name != "unknown":
                fk = None
                # Only update cache if calories are valid (>0)
                if cals > 0:
                    fk, _ = FoodKnowledge.objects.update_or_create(name=name, defaults={'calories': cals, 'protein': data.get('protein',0), 'carbs': data.get('carbs',0), 'fat': data.get('fat',0), 'source': source_used})
                else:
                    fk = FoodKnowledge.objects.filter(name=name).first()
                
                FoodItem.objects.create(user=request.user if request.user.is_authenticated else None, name=name.title(), calories=cals, protein=data.get('protein',0), carbs=data.get('carbs',0), fat=data.get('fat',0), knowledge_source=fk)
            
            return Response({"message": "Success", "saved_data": data, "source": source_used})
        
        return Response({"error": "Scan failed"}, 422)

# =========================================================================
# 2. SMART MEAL PLANNER
# =========================================================================
@csrf_exempt
@api_view(['POST'])
def generate_meal_plan(request):
    user = User.objects.first() 
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
    
    print(f"🍱 PLAN: Target {daily_target} | Gap {remaining_cals}")

    meal_instruction = "Generate 3 meals (Breakfast, Lunch, Dinner)."
    if current_hour > 20: meal_instruction = "Late Night: 1 light snack."
    elif current_hour > 14: meal_instruction = "Afternoon: 2 meals (Snack + Dinner)."
    elif remaining_cals < 500: meal_instruction = "Low Calorie: 2 small snacks."

    prompt = f"""
    Act as a Nutritionist. Output strict JSON.
    
    TASK: Plan meals to fill {remaining_cals} calories.
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
    
    # 1. Google
    if GOOGLE_KEY:
        try:
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-2.0-flash-exp')
            plan_text = m.generate_content(prompt, generation_config={"response_mime_type": "application/json"}).text
        except: pass

    # 2. Mistral Direct
    if not plan_text and MISTRAL_KEY:
        try:
            client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=MISTRAL_KEY)
            res = client.chat.completions.create(
                model="mistral-small-latest", 
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            plan_text = res.choices[0].message.content
        except: pass

    # 3. OpenRouter (Fallback)
    if not plan_text and OPENROUTER_KEY:
        try:
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
            res = client.chat.completions.create(
                model="google/gemini-2.0-flash-exp:free", 
                messages=[{"role": "user", "content": prompt}]
            )
            plan_text = res.choices[0].message.content
        except: pass

    if plan_text:
        data = safe_json_extract(plan_text)
        if data and "meals" in data and isinstance(data["meals"], list):
            # Apply Safety Net
            data['meals'] = [enrich_meal_data(m) for m in data['meals']]
            return Response(data)

    # Fallback with FULL DATA (Enriched)
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
    
    prompt = f"""
    Suggest replacement for '{old_meal}' (~{calories} kcal). Context: {context}.
    JSON: {{ "name": "...", "calories": {calories}, "nutrients": {{ "protein": 0, "carbs": 0, "fat": 0 }}, "ingredients": [], "recipe": ["Step 1", "Step 2"] }}
    """
    
    plan_text = None
    if GOOGLE_KEY:
        try:
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-2.0-flash-exp') 
            plan_text = m.generate_content(prompt, generation_config={"response_mime_type": "application/json"}).text
        except: pass
    
    if plan_text:
        data = safe_json_extract(plan_text)
        if data: 
            return Response(enrich_meal_data(data))

    return Response(enrich_meal_data({
        "name": "Masala Oats", "calories": calories
    }))

# ==========================================
# 3. ROSTER ANALYZER (Corrected Syntax)
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
        
        # 1. Google
        if GOOGLE_KEY:
            try:
                genai.configure(api_key=GOOGLE_KEY)
                m = genai.GenerativeModel('gemini-2.0-flash-exp')
                res = m.generate_content([{'mime_type': 'image/jpeg', 'data': b64}, prompt], generation_config={"response_mime_type": "application/json"})
                if res.text: return Response(safe_json_extract(res.text))
            except: pass

        # 2. Mistral Direct (Syntax Fixed)
        if MISTRAL_KEY:
            try:
                client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=MISTRAL_KEY)
                res = client.chat.completions.create(
                    model="pixtral-12b-2409", 
                    messages=[{
                        "role": "user", 
                        "content": [
                            {"type": "text", "text": prompt}, 
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                        ]
                    }] 
                )
                return Response(safe_json_extract(res.choices[0].message.content))
            except: pass

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