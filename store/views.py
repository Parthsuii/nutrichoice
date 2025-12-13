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

# --- IMPORTS FROM YOUR APP ---
from .models import FoodItem, UserProfile 
from .serializers import FoodItemSerializer, UserProfileSerializer

# --- CONFIGURATION ---
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
HF_KEY = os.environ.get("HUGGINGFACE_API_KEY")
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
# THE VISION SWARM (OpenRouter Only - Reliable Free Tier)
# =========================================================================
def scan_with_openrouter(prompt, base64_img):
    if not OPENROUTER_KEY: 
        print("CRITICAL ERROR: OPENROUTER_API_KEY is missing from environment variables!")
        return None, None
    
    # Expanded "Swarm" List (6 Models)
    # The code will loop through these until one works.
    models = [
        "google/gemini-2.0-flash-exp:free",      # 1. Best (Google)
        "google/gemini-1.5-flash:free",          # 2. Reliable Backup (Google)
        "qwen/qwen-2.5-vl-72b-instruct:free",    # 3. High Accuracy (Alibaba)
        "qwen/qwen-2-vl-7b-instruct:free",       # 4. Faster/Smaller Qwen
        "meta-llama/llama-3.2-11b-vision-instruct:free", # 5. Llama (Meta)
        "microsoft/phi-3.5-vision-instruct:free" # 6. Phi (Microsoft) - Very reliable
    ]

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)

    for model in models:
        try:
            print(f"Trying Vision Model: {model}...")
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
            # If we get here, it worked!
            return completion.choices[0].message.content, f"OpenRouter {model}"
        except Exception as e:
            err_str = str(e)
            print(f"Model {model} failed. Reason: {err_str}")
            
            # IMPROVEMENT 1: Specific Error Handling
            if "401" in err_str:
                print("STOPPING: Your API Key is Invalid (401). Please check .env settings.")
                break # Stop trying models if the key is wrong
            
            if "429" in err_str:
                print(f"RATE LIMIT (429) on {model}. Switching to next model...")

            time.sleep(0.5)
            continue 
            
    return None, None

# ==========================================
# 1. DIAGNOSTIC ENDPOINT (Health Check)
# ==========================================
@csrf_exempt 
@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def ai_status_check(request):
    results = {}
    
    # 1. Check OpenRouter (Network & Key)
    if OPENROUTER_KEY:
        try:
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
            client.chat.completions.create(
                model="google/gemini-2.0-flash-exp:free", 
                messages=[{"role": "user", "content": "Hi"}],
                extra_headers={"HTTP-Referer": SITE_URL, "X-Title": APP_NAME}
            )
            results["OpenRouter"] = "SUCCESS"
        except Exception as e:
            # 429 means "Busy" but Key is Valid -> SUCCESS
            if "429" in str(e): results["OpenRouter"] = "SUCCESS (Rate Limited but Connected)"
            else: results["OpenRouter"] = f"Warning: {str(e)[:50]}"
    else: results["OpenRouter"] = "MISSING KEY"

    # 2. Check Hugging Face (Account Validation ONLY)
    if HF_KEY:
        try:
            headers = {"Authorization": f"Bearer {HF_KEY}"}
            # 'whoami' is the only guaranteed free endpoint
            r = requests.get("https://huggingface.co/api/whoami-v2", headers=headers, timeout=5)
            if r.status_code == 200: results["HuggingFace"] = "SUCCESS"
            elif r.status_code == 401: results["HuggingFace"] = "FAILED: Invalid API Key"
            else: results["HuggingFace"] = f"FAILED: {r.status_code}"
        except Exception as e: results["HuggingFace"] = "FAILED: Connection Error"
    else: results["HuggingFace"] = "MISSING KEY"

    return Response(results)

# ==========================================
# 2. ROSTER SCANNER (Stable - OpenRouter Only)
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
        Format:
        {
          "weekly_schedule": {
            "Monday": [{"time": "HH:MM", "event": "Class Name"}]
          }
        }
        Use 24-hour format (e.g. 14:00) if possible.
        If unsure, list detected classes under Monday.
        """

        print("--- STARTING SCAN ---")

        # ONLY use OpenRouter (Reliable Vision Swarm)
        data, source = scan_with_openrouter(prompt, base64_img)

        print(f"DEBUG: Source used: {source}")
        
        # If ALL models failed (Network or Rate Limits)
        if not data:
             return Response({"error": "AI Service Busy. Please try again in 1 minute."}, status=503)

        # Process Success
        try:
            json_data = safe_json_extract(data)
            
            # Ensure valid structure for Frontend
            if json_data:
                if "weekly_schedule" not in json_data:
                    json_data = {"weekly_schedule": json_data}
                
                # Normalize keys (Monday-Sunday) to be safe
                days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                for d in days:
                    if d not in json_data["weekly_schedule"]:
                        json_data["weekly_schedule"][d] = []
                
                # IMPROVEMENT 2: Sort events by time
                for day, events in json_data["weekly_schedule"].items():
                    if isinstance(events, list):
                        try:
                            # Sorts "09:00" before "10:00"
                            events.sort(key=lambda x: x.get("time", ""))
                        except Exception:
                            pass

                json_data['ai_source'] = source
                return Response(json_data)

            # Fallback: Text found but JSON parsing failed
            clean_text = str(data)[:200].replace('"', '')
            return Response({
                "weekly_schedule": {
                    "Monday": [{"time": "See Details", "event": f"Raw: {clean_text}..."}],
                    "Tuesday": [], "Wednesday": [], "Thursday": [], "Friday": [], "Saturday": [], "Sunday": []
                },
                "ai_source": f"{source} (Raw Mode)"
            })

        except Exception as e:
            print(f"Parsing Error: {e}")
            return Response({"error": "Failed to parse timetable."}, status=500)

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
        # Use simple text model for Q&A
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
        
        # Use OpenRouter Swarm
        data, source = scan_with_openrouter(prompt, b64)
        
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