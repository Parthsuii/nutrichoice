from rest_framework.decorators import api_view, parser_classes, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.models import User
from django.conf import settings
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
HF_KEY = os.environ.get("HUGGINGFACE_API_KEY")

SITE_URL = "https://nutrichoice.onrender.com"
APP_NAME = "NutriChoice"

# --- HELPER: Normalization ---
def normalize_food_name(name):
    if not name: return "unknown"
    clean = name.lower().strip()
    aliases = {
        "butter paneer": "paneer butter masala",
        "makhani paneer": "paneer butter masala",
        "shahi paneer": "paneer butter masala",
    }
    return aliases.get(clean, clean)

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
# SMART SCANNER (Robust Model Fallback)
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

        # ---------------------------------------------------------
        # PATH A: IMAGE RECEIVED
        # ---------------------------------------------------------
        if image_file:
            print("📸 IMAGE SCAN: Processing via Vision AI...")
            b64 = encode_image(image_file)
            prompt = """Analyze this food. Return STRICT JSON: { "food_name": "Paneer", "estimated_calories": 300, "protein": 10, "carbs": 20, "fat": 15, "ingredients": ["paneer"], "confidence_score": 90 }"""
            
            # TRY GOOGLE VISION (Loop through known working models)
            if GOOGLE_KEY:
                # 1. Try Exact Version (Safest)
                # 2. Try Alias (Standard)
                # 3. Try Pro Vision (Legacy backup)
                models_to_try = ['gemini-1.5-flash-001', 'gemini-1.5-flash', 'gemini-pro-vision']
                
                genai.configure(api_key=GOOGLE_KEY)
                
                for model_name in models_to_try:
                    try:
                        print(f"Trying Google Model: {model_name}...")
                        model = genai.GenerativeModel(model_name)
                        res = model.generate_content([{'mime_type': 'image/jpeg', 'data': b64}, prompt])
                        if res.text:
                            data = safe_json_extract(res.text)
                            source_used = f"Google Vision ({model_name})"
                            break # Success! Stop trying other models
                    except Exception as e:
                        print(f"Failed {model_name}: {e}")
                        continue 

            # OPENROUTER FALLBACK (If all Google models fail)
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

        # ---------------------------------------------------------
        # PATH B: TEXT ONLY (Robust)
        # ---------------------------------------------------------
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

            # 2. Call AI (Try Multiple Google Models)
            print("🌐 CACHE MISS: Calling Text AI...")
            prompt = f"Analyze '{food_name_normalized}'. Return JSON: {{ \"food_name\": \"{food_name_normalized}\", \"estimated_calories\": 0, \"protein\": 0, \"carbs\": 0, \"fat\": 0, \"ingredients\": [] }}"
            
            if GOOGLE_KEY:
                # Text models to try (Flash is best, Pro is backup)
                text_models = ['gemini-1.5-flash-001', 'gemini-1.5-flash', 'gemini-pro']
                genai.configure(api_key=GOOGLE_KEY)
                
                for model_name in text_models:
                    try:
                        print(f"Trying Text Model: {model_name}...")
                        model = genai.GenerativeModel(model_name)
                        res = model.generate_content(prompt)
                        data = safe_json_extract(res.text)
                        if data:
                            source_used = f"Google Text ({model_name})"
                            break
                    except Exception as e:
                        print(f"Text Model {model_name} failed: {e}")
                        continue

            # 3. Call AI (OpenRouter Fallback)
            if not data and OPENROUTER_KEY:
                print("🔄 Google Failed. Trying OpenRouter Text...")
                try:
                    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
                    res = client.chat.completions.create(
                        model="google/gemini-2.0-flash-exp:free",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    data = safe_json_extract(res.choices[0].message.content)
                    source_used = "OpenRouter Text"
                except Exception as e: 
                    # SOFT LANDING
                    data = {
                        "food_name": food_name_normalized.title(),
                        "estimated_calories": 0, "protein": 0, "carbs": 0, "fat": 0, "ingredients": [], "confidence_score": 0
                    }
                    source_used = "Manual Entry (AI Failed)"

        # ---------------------------------------------------------
        # SAVE & RETURN
        # ---------------------------------------------------------
        if data:
            name = normalize_food_name(data.get('food_name', 'Unknown'))
            if len(name) < 3 or name.isnumeric():
                return Response({"error": "Scan unclear, please type name manually"}, status=422)

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

            if name != "unknown" and cals > 0 and source_used != "Manual Entry (AI Failed)":
                fk, _ = FoodKnowledge.objects.update_or_create(
                    name=name,
                    defaults={'calories': cals, 'protein': prot, 'carbs': carbs, 'fat': fat, 'ingredients': ingredients, 'confidence_score': conf, 'source': source_used}
                )
                FoodItem.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    name=name.title(), calories=cals, protein=prot, carbs=carbs, fat=fat, knowledge_source=fk
                )
            elif name != "unknown": 
                FoodItem.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    name=name.title(), calories=0, protein=0, carbs=0, fat=0
                )

            return Response({
                "message": "Success", 
                "saved_data": { "id": 0, "food_name": name.title(), "estimated_calories": cals, "protein": prot, "carbs": carbs, "fat": fat, "ingredients": ingredients }, 
                "source": source_used
            })

        return Response({"error": "Scan Failed"}, 500)

# ==========================================
# OTHER VIEWS
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
        prompt = """Analyze timetable. JSON: { "weekly_schedule": { "Monday": [{"time": "10:00", "event": "Math"}] } }"""
        
        # Try multiple models for Roster too
        if GOOGLE_KEY:
            genai.configure(api_key=GOOGLE_KEY)
            for m_name in ['gemini-1.5-flash-001', 'gemini-1.5-flash', 'gemini-pro-vision']:
                try:
                    m = genai.GenerativeModel(m_name)
                    r = m.generate_content([{'mime_type': 'image/jpeg', 'data': b64}, prompt])
                    if r.text: return Response(safe_json_extract(r.text))
                except: continue
        return Response({"error": "Busy"}, 503)

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
            m = genai.GenerativeModel('gemini-1.5-flash-001')
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

@csrf_exempt
@api_view(['POST'])
def generate_meal_plan(request): return Response({"meals": []}) 

@csrf_exempt
@api_view(['POST'])
def swap_meal(request): return Response({"name": "New Meal"})