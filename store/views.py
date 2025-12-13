from rest_framework.decorators import api_view, parser_classes, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.models import User
import os
import base64
import json
import time

# --- HYBRID LIBRARIES ---
from openai import OpenAI  # For OpenRouter
from huggingface_hub import InferenceClient  # For Hugging Face

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

# --- STRATEGY 1: OPENROUTER SWARM (5 Layers of Backup) ---
def scan_with_openrouter(prompt, base64_img):
    if not OPENROUTER_KEY: return None, None
    
    # PRIORITY LIST (Verified Free Models):
    # If one is busy (429) or missing (404), it tries the next.
    models = [
        "google/gemini-2.0-flash-exp:free",       # 1. Best Vision (Fast)
        "google/gemini-1.5-flash:free",           # 2. Most Reliable Backup
        "meta-llama/llama-3.2-11b-vision-instruct:free", # 3. Meta's Free Vision
        "qwen/qwen-2.5-vl-7b-instruct:free",      # 4. Open Source Vision
        "microsoft/phi-3.5-vision-instruct:free"  # 5. Microsoft's Compact Vision
    ]

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)

    for model in models:
        try:
            print(f"Trying OpenRouter: {model}...")
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
            print(f"OpenRouter {model} failed: {e}")
            time.sleep(0.5) # Short pause before retry
            continue 
            
    return None, None

# --- STRATEGY 2: HUGGING FACE FALLBACK ---
def scan_with_huggingface(prompt, base64_img):
    if not HF_KEY: return None, None
    
    # Corrected Model ID: The 7B version is free. 
    # If Qwen fails, we try Llama.
    hf_models = [
        "Qwen/Qwen2-VL-7B-Instruct",             # Standard Free Vision
        "meta-llama/Llama-3.2-11B-Vision-Instruct" # Backup
    ]
    
    client = InferenceClient(api_key=HF_KEY)

    for model_id in hf_models:
        try:
            print(f"Switching to Hugging Face: {model_id}...")
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                ]
            }]
            
            completion = client.chat_completion(
                model=model_id,
                messages=messages,
                max_tokens=1000
            )
            return completion.choices[0].message.content, f"HuggingFace {model_id}"
        except Exception as e:
            print(f"Hugging Face {model_id} failed: {e}")
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
    """Checks Health of Both Providers."""
    results = {}
    
    # Check OpenRouter (Loops until one works)
    if OPENROUTER_KEY:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
        models_to_test = [
            "google/gemini-2.0-flash-exp:free",
            "google/gemini-1.5-flash:free",
            "meta-llama/llama-3.2-11b-vision-instruct:free"
        ]
        status = "FAILED (All busy/offline)"
        for model in models_to_test:
            try:
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Hi"}]
                )
                status = f"SUCCESS ({model})"
                break
            except: continue
        results["OpenRouter"] = status
    else: results["OpenRouter"] = "MISSING KEY"

    # Check Hugging Face (Simple Text Check)
    if HF_KEY:
        try:
            client = InferenceClient(api_key=HF_KEY)
            # 'gpt2' is a tiny model that is always free/online
            client.text_generation(model="gpt2", prompt="Hi", max_new_tokens=2)
            results["HuggingFace"] = "SUCCESS"
        except Exception as e: results["HuggingFace"] = f"FAILED: {str(e)[:50]}..."
    else: results["HuggingFace"] = "MISSING KEY"

    return Response(results)

# ==========================================
# 2. HYBRID ROSTER SCANNER
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
        Extract the weekly schedule from this timetable image.
        Return ONLY valid JSON.
        Format: { "weekly_schedule": { "Monday": [{"time": "...", "event": "..."}] } }
        """

        # 1. Try The Swarm (OpenRouter)
        data, source = scan_with_openrouter(prompt, base64_img)
        
        # 2. If ALL OpenRouter Models Fail, Try Hugging Face
        if not data:
            data, source = scan_with_huggingface(prompt, base64_img)

        # 3. Process Result
        if data:
            try:
                clean = data.strip().replace("```json", "").replace("```", "").strip()
                json_data = json.loads(clean)
                if 'weekly_schedule' not in json_data:
                    if isinstance(json_data, dict): json_data = {"weekly_schedule": json_data}
                    else: raise ValueError("Invalid JSON")
                
                json_data['ai_source'] = source
                return Response(json_data)
            except Exception as e:
                return Response({"error": "JSON Parse Error", "raw": data}, status=500)

        return Response({"error": "All 7 AI models failed. Please try again later."}, status=500)

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
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
        resp = client.chat.completions.create(
            model="google/gemini-2.0-flash-exp:free",
            messages=[{"role": "user", "content": q}]
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
        
        data, source = scan_with_openrouter(prompt, b64)
        if not data: data, source = scan_with_huggingface(prompt, b64)
        
        if data:
            try:
                clean = data.strip().replace("```json", "").replace("```", "").strip()
                j = json.loads(clean)
                FoodItem.objects.create(name=j.get('food_name','?'), calories=j.get('estimated_calories',0))
                return Response({"message": "Success", "saved_data": j})
            except: pass
        return Response({"error": "Scan failed"}, 500)

@csrf_exempt
@api_view(['POST', 'GET'])
@authentication_classes([])
@permission_classes([])
def user_profile_view(request):
    if not User.objects.exists():
        try: User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        except: pass 
    user = User.objects.first()
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
@permission_classes([])
def swap_meal(request):
    try: return Response({"name": "New Meal"})
    except: return Response({"error": "Error"}, status=500)