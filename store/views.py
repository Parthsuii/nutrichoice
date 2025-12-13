from rest_framework.decorators import api_view, parser_classes, authentication_classes, permission_classes
from rest_framework.response import Response
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

# =========================================================================
# LAYER 1: OPENROUTER SWARM (Chat VLMs)
# =========================================================================
def scan_with_openrouter(prompt, base64_img):
    if not OPENROUTER_KEY: return None, None
    
    # Priority List including QWEN 2.5 VL (High Accuracy)
    models = [
        "google/gemini-2.0-flash-exp:free",      
        "qwen/qwen-2.5-vl-72b-instruct:free",    # <--- NEW: High Accuracy!
        "meta-llama/llama-3.2-11b-vision-instruct:free",
        "google/gemini-1.5-flash:free",          
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
# LAYER 2: HUGGING FACE CHAT (Qwen 2.5 VL 7B)
# =========================================================================
def scan_with_hf_chat(prompt, base64_img):
    if not HF_KEY: return None, None
    
    # Qwen 2.5 VL 7B is the best "Free" Chat VLM on Hugging Face
    model_id = "Qwen/Qwen2.5-VL-7B-Instruct"
    
    client = InferenceClient(api_key=HF_KEY)

    try:
        print(f"Trying Layer 2 (HF Chat): {model_id}...")
        completion = client.chat_completion(
            model=model_id,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                ]
            }],
            max_tokens=1000
        )
        return completion.choices[0].message.content, f"HuggingFace {model_id}"
    except Exception as e:
        print(f"Layer 2 failed: {e}")
        return None, None

# =========================================================================
# LAYER 3: SPECIALIZED VISION (Florence-2 / Moondream)
# =========================================================================
def scan_with_specialized_vision(prompt, base64_img):
    """
    Uses Florence-2 or Moondream. These are NOT chat models.
    They are specialized 'Image-to-Text' models.
    """
    if not HF_KEY: return None, None
    client = InferenceClient(api_key=HF_KEY)
    
    # 1. Florence-2 (Microsoft) - The OCR King
    # We use the '<OCR>' or '<MORE_DETAILED_CAPTION>' task prompts
    try:
        print("Trying Layer 3 (Florence-2)...")
        # Florence requires a specific task prompt. 
        # Since we want a schedule, we ask for detailed text.
        florence_prompt = "<MORE_DETAILED_CAPTION>" 
        
        result = client.image_to_text(
            model="microsoft/Florence-2-large",
            image=base64.b64decode(base64_img),
            prompt=florence_prompt
        )
        # Result is like: "The image shows a timetable..."
        return json.dumps({"raw_text": result, "note": "Parsed by Florence-2"}), "HF Florence-2"
    except Exception as e:
        print(f"Florence-2 failed: {e}")

    # 2. Moondream2 (Vikhyat) - The Tiny Giant
    try:
        print("Trying Layer 3 (Moondream2)...")
        # Moondream is a VQA model
        answer = client.visual_question_answering(
            image=base64.b64decode(base64_img),
            question="Read the text in this image and describe the schedule.",
            model="vikhyatk/moondream2"
        )
        # VQA returns a list of answers
        final_text = answer[0]['answer'] if answer else "No text found"
        return json.dumps({"raw_text": final_text, "note": "Parsed by Moondream"}), "HF Moondream2"
    except Exception as e:
        print(f"Moondream2 failed: {e}")

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
    
    # Check OpenRouter
    if OPENROUTER_KEY:
        try:
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
            client.chat.completions.create(
                model="google/gemini-1.5-flash:free",
                messages=[{"role": "user", "content": "Hi"}]
            )
            results["OpenRouter"] = "SUCCESS"
        except Exception as e: results["OpenRouter"] = f"Warning: {str(e)[:50]}"
    else: results["OpenRouter"] = "MISSING KEY"

    # Check Hugging Face (Florence-2 Check)
    if HF_KEY:
        try:
            client = InferenceClient(api_key=HF_KEY)
            # Use gpt2 for connection check, safe and fast
            client.text_generation(model="gpt2", prompt="Hi", max_new_tokens=2)
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

        # LAYER 1: OpenRouter (Best Quality)
        data, source = scan_with_openrouter(prompt, base64_img)
        
        # LAYER 2: HF Chat (Qwen 2.5)
        if not data:
            data, source = scan_with_hf_chat(prompt, base64_img)

        # LAYER 3: Specialized Vision (Florence/Moondream)
        # Note: These return raw text/captions, not perfect JSON
        if not data:
            data, source = scan_with_specialized_vision(prompt, base64_img)

        # Process Result
        if data:
            try:
                # Try to parse as JSON (Layers 1 & 2)
                clean = data.strip().replace("```json", "").replace("```", "").strip()
                json_data = json.loads(clean)
                json_data['ai_source'] = source
                return Response(json_data)
            except:
                # If Layer 3 returned raw text or JSON parsing failed
                return Response({
                    "weekly_schedule": {"Note": "Raw text extracted (Layer 3)"},
                    "raw_text": data,
                    "ai_source": source
                })

        return Response({"error": "All AI models (Layers 1, 2, & 3) failed."}, status=500)

# ==========================================
# 3. STANDARD VIEWS (Unchanged)
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
        if not data: data, source = scan_with_hf_chat(prompt, b64)
        
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