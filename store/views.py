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

# --- HELPER: Robust JSON Extraction ---
def safe_json_extract(text):
    """Finds the first '{' and last '}' to isolate JSON from AI chatter."""
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
        raise ValueError("No valid JSON found in AI response")

# =========================================================================
# LAYER 1: OPENROUTER SWARM (Chat VLMs)
# =========================================================================
def scan_with_openrouter(prompt, base64_img):
    if not OPENROUTER_KEY: return None, None
    
    # Priority List
    models = [
        "google/gemini-2.0-flash-exp:free",      
        "qwen/qwen-2.5-vl-72b-instruct:free",    
        "google/gemini-1.5-flash:free",          
        "meta-llama/llama-3.2-11b-vision-instruct:free",
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
            print(f"OpenRouter {model} failed: {e}")
            time.sleep(0.5)
            continue 
            
    return None, None

# =========================================================================
# LAYER 2: HUGGING FACE CHAT (Qwen 2-VL)
# =========================================================================
def scan_with_hf_chat(prompt, base64_img):
    if not HF_KEY: return None, None
    
    # Use Qwen2-VL (older stable version) to fix 404 errors
    model_id = "Qwen/Qwen2-VL-7B-Instruct"
    client = InferenceClient(api_key=HF_KEY)

    for attempt in range(2): 
        try:
            print(f"Trying Layer 2 (HF Chat): {model_id} (Attempt {attempt+1})...")
            completion = client.chat_completion(
                model=model_id,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_img}"
                        }}
                    ]
                }],
                max_tokens=800
            )
            return completion.choices[0].message.content, f"HuggingFace {model_id}"
        except Exception as e:
            print(f"Layer 2 failed (Attempt {attempt+1}): {e}")
            time.sleep(1)

    return None, None

# =========================================================================
# LAYER 3: SPECIALIZED VISION (Florence-2 / Moondream)
# =========================================================================
def scan_with_specialized_vision(prompt, base64_img):
    if not HF_KEY: return None, None
    client = InferenceClient(api_key=HF_KEY)
    
    # 1. Florence-2
    try:
        print("Trying Layer 3 (Florence-2)...")
        florence_prompt = "<MORE_DETAILED_CAPTION>" 
        result = client.image_to_text(
            model="microsoft/Florence-2-large",
            image=base64.b64decode(base64_img),
            prompt=florence_prompt
        )
        return json.dumps({"raw_text": result, "note": "Parsed by Florence-2"}), "HF Florence-2"
    except Exception as e:
        print(f"Florence-2 failed: {e}")

    # 2. Moondream2
    try:
        print("Trying Layer 3 (Moondream2)...")
        answer = client.visual_question_answering(
            image=base64.b64decode(base64_img),
            question="Read the text in this image and describe the schedule.",
            model="vikhyatk/moondream2"
        )
        final_text = answer[0]['answer'] if answer else "No text found"
        return json.dumps({"raw_text": final_text, "note": "Parsed by Moondream"}), "HF Moondream2"
    except Exception as e:
        print(f"Moondream2 failed: {e}")

    return None, None

# ==========================================
# 1. DIAGNOSTIC ENDPOINT (SMARTER)
# ==========================================
@csrf_exempt 
@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def ai_status_check(request):
    results = {}
    
    # OpenRouter Check
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
            # 429 means "Busy" but authenticated -> Success for setup
            if "429" in str(e):
                results["OpenRouter"] = "SUCCESS (Rate Limited but Connected)"
            else:
                results["OpenRouter"] = f"Warning: {str(e)[:50]}"
    else: results["OpenRouter"] = "MISSING KEY"

    # HF Check (Using Flan-T5 - Always Online)
    if HF_KEY:
        try:
            client = InferenceClient(api_key=HF_KEY)
            client.text_generation(model="google/flan-t5-small", prompt="Hi", max_new_tokens=2)
            results["HuggingFace"] = "SUCCESS"
        except Exception as e: results["HuggingFace"] = f"FAILED: {str(e)[:50]}"
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

        # LAYER 1: OpenRouter
        data, source = scan_with_openrouter(prompt, base64_img)
        
        # LAYER 2: HF Chat
        if not data:
            data, source = scan_with_hf_chat(prompt, base64_img)

        # LAYER 3: Specialized Vision
        if not data:
            data, source = scan_with_specialized_vision(prompt, base64_img)

        # Process Result
        if data:
            try:
                json_data = safe_json_extract(data)
                json_data['ai_source'] = source
                return Response(json_data)
            except:
                return Response({
                    "weekly_schedule": {"Note": "Raw text extracted (Layer 3)"},
                    "raw_text": data,
                    "ai_source": source
                })

        return Response({"error": "All AI models (Layers 1, 2, & 3) failed."}, status=500)

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
        
        data, source = scan_with_openrouter(prompt, b64)
        if not data: data, source = scan_with_hf_chat(prompt, b64)
        
        if data:
            try:
                j = safe_json_extract(data)
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
@permission_classes([])
def swap_meal(request):
    try: return Response({"name": "New Meal"})
    except: return Response({"error": "Error"}, status=500)