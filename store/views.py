from rest_framework.decorators import api_view, parser_classes, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone # Core Django Timezone utils
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

# --- HELPER: Normalization ---
def normalize_food_name(name):
    if not name: return "unknown"
    clean = name.lower().strip()
    return clean

# --- HELPER: Encode Image ---
def encode_image(image_file):
    image_file.seek(0)
    return base64.b64encode(image_file.read()).decode('utf-8')

# --- HELPER: Robust JSON Extraction ---
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
# 1. SMART SCANNER (Failover: Google 2.0 -> OpenRouter -> Llama)
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

        # PATH A: IMAGE RECEIVED
        if image_file:
            print("📸 IMAGE SCAN: Processing...")
            b64 = encode_image(image_file)
            prompt = """Analyze this food. Return STRICT JSON: { "food_name": "Paneer", "estimated_calories": 300, "protein": 10, "carbs": 20, "fat": 15, "ingredients": ["paneer"], "confidence_score": 90 }"""
            
            # 1. Try Google Direct
            if GOOGLE_KEY:
                models_to_try = ['gemini-2.0-flash-exp']
                genai.configure(api_key=GOOGLE_KEY)
                
                for model_name in models_to_try:
                    try:
                        print(f"🔹 Google: Trying {model_name}...")
                        model = genai.GenerativeModel(model_name)
                        res = model.generate_content([{'mime_type': 'image/jpeg', 'data': b64}, prompt])
                        if res.text:
                            data = safe_json_extract(res.text)
                            source_used = f"Google Vision ({model_name})"
                            break 
                    except Exception as e:
                        print(f"⚠️ Google Failed: {str(e)[:100]}") # Print first 100 chars of error
                        continue 

            # 2. OpenRouter Fallback
            if not data:
                if not OPENROUTER_KEY:
                    print("❌ OpenRouter Skipped: No API Key found in Environment!")
                else:
                    try:
                        print("🔄 Trying OpenRouter (Gemini 2.0)...")
                        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
                        res = client.chat.completions.create(
                            model="google/gemini-2.0-flash-exp:free",
                            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]
                        )
                        data = safe_json_extract(res.choices[0].message.content)
                        source_used = "OpenRouter Vision"
                    except Exception as e: 
                        print(f"❌ OpenRouter Gemini Error: {e}") 
                        
                        # Tertiary Backup: Llama 3.2
                        try:
                            print("🔄 Trying OpenRouter (Llama 3.2)...")
                            res = client.chat.completions.create(
                                model="meta-llama/llama-3.2-90b-vision-instruct:free",
                                messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]
                            )
                            data = safe_json_extract(res.choices[0].message.content)
                            source_used = "OpenRouter Vision (Llama)"
                        except Exception as e2:
                             print(f"❌ OpenRouter Llama Error: {e2}") 

        # PATH B: TEXT ONLY
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

            # 2. Text AI
            print("🌐 CACHE MISS: Calling Text AI...")
            prompt = f"Analyze '{food_name_normalized}'. Return JSON: {{ \"food_name\": \"{food_name_normalized}\", \"estimated_calories\": 0, \"protein\": 0, \"carbs\": 0, \"fat\": 0, \"ingredients\": [] }}"
            
            if GOOGLE_KEY:
                genai.configure(api_key=GOOGLE_KEY)
                try:
                    model = genai.GenerativeModel('gemini-2.0-flash-exp')
                    res = model.generate_content(prompt)
                    data = safe_json_extract(res.text)
                    if data: source_used = "Google Text (Gemini 2.0)"
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
                except: 
                    # Soft Landing
                    data = {"food_name": food_name_normalized.title(), "estimated_calories": 0, "protein": 0, "carbs": 0, "fat": 0, "ingredients": [], "confidence_score": 0}
                    source_used = "Manual Entry (AI Failed)"

        # SAVE & RETURN
        if data:
            name = normalize_food_name(data.get('food_name', 'Unknown'))
            if len(name) < 3 or name.isnumeric(): return Response({"error": "Scan unclear"}, status=422)

            try:
                c_raw = str(data.get('estimated_calories', 0))
                c_clean = "".join(filter(str.isdigit, c_raw))
                cals = int(c_clean) if c_clean else 0
                prot = float(data.get('protein', 0))
                carbs = float(data.get('carbs', 0))
                fat = float(data.get('fat', 0))
                ingredients = data.get('ingredients', [])
                conf = int(data.get('confidence_score', 80))
            except: cals, prot, carbs, fat, ingredients, conf = 0, 0, 0, 0, [], 0

            if name != "unknown" and cals > 0 and "Manual" not in source_used:
                fk, _ = FoodKnowledge.objects.update_or_create(
                    name=name,
                    defaults={'calories': cals, 'protein': prot, 'carbs': carbs, 'fat': fat, 'ingredients': ingredients, 'confidence_score': conf, 'source': source_used}
                )
                FoodItem.objects.create(user=request.user if request.user.is_authenticated else None, name=name.title(), calories=cals, protein=prot, carbs=carbs, fat=fat, knowledge_source=fk)
            elif name != "unknown": 
                FoodItem.objects.create(user=request.user if request.user.is_authenticated else None, name=name.title(), calories=0, protein=0, carbs=0, fat=0)

            return Response({
                "message": "Success", 
                "saved_data": { "id": 0, "food_name": name.title(), "estimated_calories": cals, "protein": prot, "carbs": carbs, "fat": fat, "ingredients": ingredients }, 
                "source": source_used
            })
        
        # FINAL SAFETY NET
        print("❌ ALL AIs FAILED. Returning 422 to Client.")
        return Response({"error": "AI Busy. Please enter food manually."}, 422)

# =========================================================================
# 5. SMART MEAL PLANNER (Fix: Trusts App Data)
# =========================================================================
@csrf_exempt
@api_view(['POST'])
def generate_meal_plan(request):
    user = User.objects.first() 
    if not user: return Response({"error": "No user profile"}, 400)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    # 1. Get Data from App (TRUST THIS over DB default)
    context = request.data.get('activity_context', 'Standard Day')
    ingredients = request.data.get('available_ingredients', [])
    
    # Get target from App request, fallback to DB, fallback to 2000
    app_target = request.data.get('daily_calories')
    daily_target = int(app_target) if app_target else (profile.daily_calorie_target or 2000)
    
    # 2. Calculate Calories
    today = timezone.now().date()
    # Use Django's localtime() which respects settings.TIME_ZONE (Asia/Kolkata)
    current_hour = timezone.localtime().hour 
    
    eaten_today = FoodItem.objects.filter(created_at__date=today)
    total_eaten = sum(item.calories for item in eaten_today)
    
    remaining_cals = daily_target - total_eaten
    
    print(f"🧮 Planner Debug: Target {daily_target} - Eaten {total_eaten} = Remaining {remaining_cals}")

    # 3. Handle "Full" State (Don't return empty, return light option)
    if remaining_cals <= 100:
        return Response({
            "analysis": "You have hit your calorie goal! Just stay hydrated.",
            "meals": [
                 { 
                   "name": "Green Tea or Water", 
                   "calories": 0, "protein": 0, "carbs": 0, "fat": 0, 
                   "time": "Evening",
                   "ingredients": ["Water", "Tea Bag"],
                   "recipe": ["Boil water", "Steep tea"]
                }
            ]
        })

    # 4. Prompt Engineering
    time_instruction = f"It is {current_hour}:00."
    if current_hour > 21: time_instruction += " Late Night. Suggest ONLY light milk/snacks."
    elif current_hour > 15: time_instruction += " Lunch is over. Suggest Dinner & Snack."
    elif current_hour < 11: time_instruction += " Morning. Suggest Lunch & Dinner."

    context_instruction = "Balanced Diet."
    if "Lifting" in context: context_instruction = "High Protein for muscle recovery."
    elif "Exam" in context: context_instruction = "Brain Food (Nuts, Omega-3)."
    elif "Rest" in context: context_instruction = "Low Carb, High Volume."

    ingredient_instruction = ""
    if ingredients:
        ingredient_instruction = f"MUST use: {', '.join(ingredients)}."

    prompt = f"""
    Act as an elite Indian Sports Nutritionist.
    
    USER STATS:
    - Target: {daily_target} kcal
    - Remaining Gap: {remaining_cals} kcal (FILL THIS GAP).
    - Time: {time_instruction}
    - Context: {context_instruction}
    - Pantry: {ingredient_instruction}
    
    TASK: Plan meals to hit the remaining calories.
    OUTPUT STRICT JSON:
    {{
      "analysis": "Reason for choices.",
      "meals": [
        {{ 
           "name": "Dish Name", 
           "calories": 300, "protein": 10, "carbs": 20, "fat": 5, 
           "time": "Dinner",
           "ingredients": ["Item1"],
           "recipe": ["Step 1"]
        }}
      ]
    }}
    """
    
    plan_text = None

    # AI GENERATION (Google -> OpenRouter)
    if GOOGLE_KEY:
        try:
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-2.0-flash-exp')
            plan_text = m.generate_content(prompt).text
        except Exception as e: print(f"Google Error: {e}")

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
        if data and "meals" in data:
            return Response(data)

    # Fallback
    return Response({
        "analysis": "AI busy. Here is a safe default.",
        "meals": [
            { 
                "name": "Oats & Milk", "calories": 300, "protein": 10, "carbs": 40, "fat": 8, "time": "Anytime",
                "ingredients": ["Oats", "Milk"], "recipe": ["Boil and eat"]
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
# 3. ROSTER ANALYZER (Failover: Gemini -> Pixtral)
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

        # 1. Try Google Direct (Gemini 2.0)
        if GOOGLE_KEY:
            try:
                print("📅 Analyzing Roster with Gemini 2.0...")
                genai.configure(api_key=GOOGLE_KEY)
                m = genai.GenerativeModel('gemini-2.0-flash-exp')
                r = m.generate_content([{'mime_type': 'image/jpeg', 'data': b64}, prompt])
                if r.text: data = safe_json_extract(r.text)
            except Exception as e:
                print(f"⚠️ Google Roster Failed: {e}")

        # 2. OpenRouter Fallback chain
        if not data and OPENROUTER_KEY:
            try:
                client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
                # Backup A: Gemini 2.0 via OpenRouter
                try:
                    print("📅 Switching to OpenRouter (Gemini)...")
                    res = client.chat.completions.create(
                        model="google/gemini-2.0-flash-exp:free",
                        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]
                    )
                    data = safe_json_extract(res.choices[0].message.content)
                except: 
                    print("⚠️ OpenRouter Gemini Failed.")

                # Backup B: Mistral Pixtral 12B (Great for Text/OCR)
                if not data:
                    print("📅 Switching to Mistral Pixtral 12B...")
                    res = client.chat.completions.create(
                        model="mistralai/pixtral-12b:free", 
                        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]
                    )
                    data = safe_json_extract(res.choices[0].message.content)

            except Exception as e:
                print(f"⚠️ OpenRouter Fallback Failed: {e}")

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