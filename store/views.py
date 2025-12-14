from rest_framework.decorators import api_view, parser_classes, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
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

# --- HYBRID LIBRARIES ---
from openai import OpenAI  # For OpenRouter
import google.generativeai as genai # For Google Direct

# --- IMPORTS FROM YOUR APP ---
from .models import FoodItem, UserProfile 
from .serializers import FoodItemSerializer, UserProfileSerializer

# --- CONFIGURATION ---
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
HF_KEY = os.environ.get("HUGGINGFACE_API_KEY")
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY") # <--- NEW KEY

SITE_URL = "https://nutrichoice.onrender.com"
APP_NAME = "NutriChoice"

# --- HELPER: Encode Image ---
def encode_image(image_file):
    image_file.seek(0)
    return base64.b64encode(image_file.read()).decode('utf-8')

# --- HELPER: Robust JSON Extraction ---
def safe_json_extract(text):
    """Finds the first '{' and last '}' to isolate JSON from AI chatter."""
    if not text: return None
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start:end+1])
    except Exception:
        pass
    try:
        clean = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except:
        return None

# =========================================================================
# LAYER 0: GOOGLE DIRECT (The Tank - 15 RPM Free)
# =========================================================================
def scan_with_google_direct(prompt, base64_img):
    if not GOOGLE_KEY: 
        print("Skipping Layer 0: GOOGLE_API_KEY not found.")
        return None, None
    
    print("Trying Layer 0 (Google Direct)...")
    try:
        genai.configure(api_key=GOOGLE_KEY)
        # Use Flash 1.5 - Fast, Free, Vision-Native
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Google SDK expects a dict for image data
        response = model.generate_content([
            {'mime_type': 'image/jpeg', 'data': base64_img},
            prompt
        ])
        
        if response.text:
            return response.text, "Google Gemini Direct"
            
    except Exception as e:
        print(f"Layer 0 (Google) Failed: {e}")
        # Common Google Errors: 400 (Bad Request), 429 (Quota), 500
        
    return None, None

# =========================================================================
# LAYER 1: OPENROUTER SWARM (The Backup)
# =========================================================================
def scan_with_openrouter(prompt, base64_img):
    if not OPENROUTER_KEY: 
        print("CRITICAL ERROR: OPENROUTER_API_KEY is missing!")
        return None, None
    
    # Expanded Swarm
    models = [
        "qwen/qwen-2.5-vl-72b-instruct:free",    # 1. High Accuracy
        "meta-llama/llama-3.2-11b-vision-instruct:free", # 2. Llama
        "microsoft/phi-3.5-vision-instruct:free", # 3. Phi
        "google/gemini-2.0-flash-exp:free",      # 4. Fallback Google via OR
    ]

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)

    for model in models:
        try:
            print(f"Trying Layer 1 (OpenRouter): {model}...")
            completion = client.chat.completions.create(
                extra_headers={"HTTP-Referer": SITE_URL, "X-Title": APP_NAME},
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                    ]
                }]
            )
            return completion.choices[0].message.content, f"OpenRouter {model}"
        except Exception as e:
            err_str = str(e)
            print(f"Model {model} failed. Reason: {err_str[:50]}...")
            if "401" in err_str: break 
            time.sleep(0.5)
            continue 
            
    return None, None

# ==========================================
# 1. DIAGNOSTIC ENDPOINT
# ==========================================
@csrf_exempt 
@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def ai_status_check(request):
    results = {}
    
    # Check Google Direct
    if GOOGLE_KEY:
        try:
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-1.5-flash')
            m.generate_content("Ping")
            results["GoogleDirect"] = "SUCCESS"
        except Exception as e: results["GoogleDirect"] = f"FAILED: {str(e)[:50]}"
    else: results["GoogleDirect"] = "MISSING KEY"

    # Check OpenRouter
    if OPENROUTER_KEY:
        try:
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
            client.chat.completions.create(
                model="microsoft/phi-3.5-vision-instruct:free", 
                messages=[{"role": "user", "content": "Hi"}]
            )
            results["OpenRouter"] = "SUCCESS"
        except Exception as e:
            if "429" in str(e): results["OpenRouter"] = "SUCCESS (Rate Limited)"
            else: results["OpenRouter"] = f"Warning: {str(e)[:50]}"
    else: results["OpenRouter"] = "MISSING KEY"

    # Check HF (Account Only)
    if HF_KEY:
        try:
            r = requests.get("https://huggingface.co/api/whoami-v2", headers={"Authorization": f"Bearer {HF_KEY}"})
            if r.status_code == 200: results["HuggingFace"] = "SUCCESS"
            else: results["HuggingFace"] = f"FAILED: {r.status_code}"
        except: results["HuggingFace"] = "FAILED: Connection"
    else: results["HuggingFace"] = "MISSING KEY"

    return Response(results)

# ==========================================
# 2. ROSTER SCANNER (Google -> OpenRouter)
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
        
        prompt = """
        Read this timetable image.
        Output JSON ONLY.
        Format: { "weekly_schedule": { "Monday": [{"time": "HH:MM", "event": "Name"}] } }
        Sort by time. If unsure, list under Monday.
        """

        print("--- STARTING SCAN ---")

        # 1. TRY GOOGLE DIRECT (Best Chance)
        data, source = scan_with_google_direct(prompt, base64_img)

        # 2. TRY OPENROUTER SWARM (Backup)
        if not data:
            data, source = scan_with_openrouter(prompt, base64_img)

        print(f"DEBUG: Source used: {source}")
        
        if not data:
             return Response({"error": "All AI Services Busy. Try again in 1 min."}, status=503)

        try:
            json_data = safe_json_extract(data)
            if json_data:
                if "weekly_schedule" not in json_data:
                    json_data = {"weekly_schedule": json_data}
                
                days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                for d in days:
                    if d not in json_data["weekly_schedule"]:
                        json_data["weekly_schedule"][d] = []
                
                # Sort events
                for day, events in json_data["weekly_schedule"].items():
                    if isinstance(events, list):
                        events.sort(key=lambda x: x.get("time", ""))

                json_data['ai_source'] = source
                return Response(json_data)

            # Raw Fallback
            clean_text = str(data)[:200].replace('"', '')
            return Response({
                "weekly_schedule": {
                    "Monday": [{"time": "Info", "event": f"Raw: {clean_text}..."}],
                    "Tuesday": [], "Wednesday": [], "Thursday": [], "Friday": [], "Saturday": [], "Sunday": []
                },
                "ai_source": f"{source} (Raw Mode)"
            })

        except Exception as e:
            print(f"Parsing Error: {e}")
            return Response({"error": "Failed to parse result."}, status=500)

# ==========================================
# 3. STANDARD VIEWS
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

@csrf_exempt
@api_view(['POST'])
def ask_nutritionist(request):
    q = request.data.get('question')
    if not q: return Response({"error": "No question"}, 400)
    try:
        # Prefer Google for Q&A (Faster)
        if GOOGLE_KEY:
            genai.configure(api_key=GOOGLE_KEY)
            m = genai.GenerativeModel('gemini-1.5-flash')
            resp = m.generate_content(q)
            return Response({"answer": resp.text})
        
        # Fallback to OpenRouter
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
        resp = client.chat.completions.create(
            model="google/gemini-2.0-flash-exp:free", 
            messages=[{"role": "user", "content": q}],
            extra_headers={"HTTP-Referer": SITE_URL, "X-Title": APP_NAME}
        )
        return Response({"answer": resp.choices[0].message.content})
    except: return Response({"error": "AI Error"}, 500)

@method_decorator(csrf_exempt, name='dispatch')
class ScanFoodView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        if 'image' not in request.FILES: return Response({"error": "No image"}, 400)
        img = request.FILES['image']
        b64 = encode_image(img)
        prompt = """Identify food. JSON: { "food_name": "...", "estimated_calories": 0, "protein": 0, "carbs": 0, "fat": 0 }"""
        
        # 1. Google Direct
        data, source = scan_with_google_direct(prompt, b64)
        # 2. OpenRouter Fallback
        if not data: data, source = scan_with_openrouter(prompt, b64)
        
        if data:
            try:
                j = safe_json_extract(data)
                if j:
                    FoodItem.objects.create(name=j.get('food_name','?'), calories=j.get('estimated_calories',0))
                    return Response({"message": "Success", "saved_data": j})
            except: pass
        return Response({"error": "Scan failed"}, 500)

@csrf_exempt
@api_view(['POST', 'GET'])
@authentication_classes([])
@permission_classes([])
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
@authentication_classes([])
@permission_classes([])
def generate_meal_plan(request):
    try: return Response({"meals": []}) 
    except: return Response({"error": "Error"}, status=500)

@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
def swap_meal(request):
    try: return Response({"name": "New Meal"})
    except: return Response({"error": "Error"}, status=500)