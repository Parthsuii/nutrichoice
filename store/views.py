from rest_framework.decorators import api_view, parser_classes, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework import serializers
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.models import User
from django.conf import settings
import os
import base64
import json
import time
import requests 
import re 

# --- HYBRID LIBRARIES ---
from openai import OpenAI  # For OpenRouter (Fallback)
import google.generativeai as genai # For Google Direct (Primary)

# --- IMPORTS FROM YOUR APP ---
from .models import FoodItem, UserProfile, FoodKnowledge 
from .serializers import FoodItemSerializer, UserProfileSerializer

# --- CONFIGURATION ---
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY") 
HF_KEY = os.environ.get("HUGGINGFACE_API_KEY") # Added back for status check

SITE_URL = "https://nutrichoice.onrender.com"
APP_NAME = "NutriChoice"

# --- GLOBAL CIRCUIT BREAKER ---
GOOGLE_COOLDOWN_UNTIL = 0 

# --- HELPER: Normalization ---
def normalize_food_name(name):
    """Standardizes food names to improve cache hits."""
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
# SMART SCANNER (Handles Image OR Text -> Knowledge Base)
# =========================================================================
@method_decorator(csrf_exempt, name='dispatch')
class ScanFoodView(APIView):
    """
    Hybrid Analyzer:
    1. If Image: Vision AI -> Extract Name/Macros -> Save to Knowledge Base.
    2. If Text: Check Knowledge Base (0 cost) -> Else Text AI -> Save.
    """
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
            print("📸 IMAGE SCAN: Processing via Vision AI...")
            b64 = encode_image(image_file)
            prompt = """
            Analyze this food. Return STRICT JSON:
            { "food_name": "Paneer", "estimated_calories": 300, "protein": 10, "carbs": 20, "fat": 15, "ingredients": ["paneer"], "confidence_score": 90 }
            """
            
            if GOOGLE_KEY:
                try:
                    genai.configure(api_key=GOOGLE_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    res = model.generate_content([{'mime_type': 'image/jpeg', 'data': b64}, prompt])
                    if res.text:
                        data = safe_json_extract(res.text)
                        source_used = "Google Vision"
                except Exception as e: print(f"Vision Error: {e}")
            
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

        # PATH B: TEXT ONLY
        elif text_query:
            food_name_normalized = normalize_food_name(str(text_query))
            print(f"🔍 TEXT SCAN: Checking '{food_name_normalized}'...")

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

            print("🌐 CACHE MISS: Calling Text AI...")
            prompt = f"Analyze '{food_name_normalized}'. Return JSON: {{ \"food_name\": \"{food_name_normalized}\", \"estimated_calories\": 0, \"protein\": 0, \"carbs\": 0, \"fat\": 0, \"ingredients\": [] }}"
            
            if GOOGLE_KEY:
                try:
                    genai.configure(api_key=GOOGLE_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    res = model.generate_content(prompt)
                    data = safe_json_extract(res.text)
                    source_used = "Google Text AI"
                except: pass

        # SAVE & RETURN
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
                conf = int(data.get('confidence_score', 80))
            except: cals, prot, carbs, fat, ingredients, conf = 0, 0, 0, 0, [], 0

            if name != "unknown" and cals > 0:
                fk, _ = FoodKnowledge.objects.update_or_create(
                    name=name,
                    defaults={'calories': cals, 'protein': prot, 'carbs': carbs, 'fat': fat, 'ingredients': ingredients, 'confidence_score': conf, 'source': source_used}
                )
                FoodItem.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    name=name.title(), calories=cals, protein=prot, carbs=carbs, fat=fat, knowledge_source=fk
                )

            return Response({
                "message": "Success", 
                "saved_data": { "id": 0, "food_name": name.title(), "estimated_calories": cals, "protein": prot, "carbs": carbs, "fat": fat, "ingredients": ingredients }, 
                "source": source_used
            })

        return Response({"error": "Scan Failed"}, 500)

# ==========================================
# ROSTER SCANNER
# ==========================================
@method_decorator(csrf_exempt, name='dispatch') 
class AnalyzeRosterView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        if 'file' not in request.FILES: return Response({"error": "No file"}, status=400)
        image_file = request.FILES['file']
        base64_img = encode_image(image_file)
        prompt = """Analyze this timetable. Output STRICT VALID JSON only. Format: { "weekly_schedule": { "Monday": [{"time": "10:00", "event": "Math"}] } }"""
        
        if GOOGLE_KEY:
            try:
                genai.configure(api_key=GOOGLE_KEY)
                model = genai.GenerativeModel('gemini-1.5-flash')
                res = model.generate_content([{'mime_type': 'image/jpeg', 'data': base64_img}, prompt])
                if res.text: return Response(safe_json_extract(res.text))
            except: pass
        return Response({"error": "Roster scan busy"}, 503)

# ==========================================
# 3. DIAGNOSTIC ENDPOINT (RESTORED!)
# ==========================================
@csrf_exempt 
@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def ai_status_check(request):
    results = {}
    if GOOGLE_KEY:
        try:
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-1.5-flash')
            m.generate_content("Ping")
            results["GoogleDirect"] = "SUCCESS"
        except Exception as e: results["GoogleDirect"] = f"FAILED: {str(e)[:50]}"
    else: results["GoogleDirect"] = "MISSING KEY"

    if OPENROUTER_KEY:
        results["OpenRouter"] = "KEY PRESENT"
    else: results["OpenRouter"] = "MISSING KEY"

    return Response(results)

# ==========================================
# STANDARD VIEWS
# ==========================================
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
            m = genai.GenerativeModel('gemini-1.5-flash')
            resp = m.generate_content(q)
            return Response({"answer": resp.text})
    except: return Response({"error": "AI Error"}, 500)

@csrf_exempt
@api_view(['POST', 'GET'])
def user_profile_view(request):
    if settings.DEBUG and not User.objects.exists():
        try: User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        except: pass 
    user = User.objects.first()
    if not user: return Response({"error": "No users found"}, status=404)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if request.method == 'GET': return Response(UserProfileSerializer(profile).data)
    if request.method == 'POST':
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Updated"})
        return Response(serializer.errors, status=400)

@csrf_exempt
@api_view(['POST'])
def generate_meal_plan(request):
    return Response({"meals": []}) 

@csrf_exempt
@api_view(['POST'])
def swap_meal(request):
    return Response({"name": "New Meal"})