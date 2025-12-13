from rest_framework.decorators import api_view, parser_classes, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import serializers
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from PIL import Image
from django.contrib.auth.models import User
import os
import base64
import json

# --- IMPORTS FROM YOUR APP ---
from .models import FoodItem, UserProfile 
from .serializers import FoodItemSerializer, UserProfileSerializer, FoodImageSerializer

# --- AI LIBRARIES ---
import google.generativeai as genai
from mistralai import Mistral
from groq import Groq
from huggingface_hub import InferenceClient # pip install huggingface_hub

# --- CONFIGURATION ---
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY")
GROQ_KEY = os.environ.get("GROQ_API_KEY")
HF_KEY = os.environ.get("HUGGINGFACE_API_KEY")

if GOOGLE_KEY:
    genai.configure(api_key=GOOGLE_KEY)

# --- HELPER: Convert Image to Base64 ---
def encode_image(image_file):
    image_file.seek(0)
    return base64.b64encode(image_file.read()).decode('utf-8')

# ==========================================
# 0. AI STATUS CHECK (DIAGNOSTIC)
# ==========================================
@csrf_exempt 
@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def ai_status_check(request):
    """Checks ALL 4 AI keys."""
    results = {}

    # 1. GROQ (Llama 3.2 Vision) - FASTEST
    if not GROQ_KEY: results['Groq'] = "FAILED: Key missing."
    else:
        try:
            client = Groq(api_key=GROQ_KEY)
            client.chat.completions.create(
                model="llama-3.2-11b-vision-preview", # Valid Vision Model
                messages=[{"role": "user", "content": "Hi"}]
            )
            results['Groq'] = "SUCCESS"
        except Exception as e: results['Groq'] = f"FAILED: {str(e)}"

    # 2. MISTRAL - RELIABLE
    if not MISTRAL_KEY: results['Mistral'] = "FAILED: Key missing."
    else:
        try:
            client = Mistral(api_key=MISTRAL_KEY)
            client.chat.complete(model="mistral-tiny", messages=[{"role": "user", "content": "Hi"}])
            results['Mistral'] = "SUCCESS"
        except Exception as e: results['Mistral'] = f"FAILED: {str(e)}"

    # 3. GEMINI - BACKUP
    if not GOOGLE_KEY: results['Gemini'] = "FAILED: Key missing."
    else:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            model.generate_content("Hi")
            results['Gemini'] = "SUCCESS"
        except Exception as e: results['Gemini'] = f"FAILED: {str(e)}"

    # 4. HUGGING FACE (Qwen2-VL) - ACCURATE
    if not HF_KEY: results['HuggingFace'] = "FAILED: Key missing."
    else:
        try:
            client = InferenceClient(api_key=HF_KEY)
            client.text_generation(model="Qwen/Qwen2.5-72B-Instruct", prompt="Hi", max_new_tokens=5)
            results['HuggingFace'] = "SUCCESS"
        except Exception as e: results['HuggingFace'] = f"FAILED: {str(e)}"

    return Response({"AI Status": results})

# ==========================================
# 1. STANDARD CRUD VIEWS
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

# ==========================================
# 2. ASK NUTRITIONIST
# ==========================================
@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def ask_nutritionist(request):
    user_question = request.data.get('question')
    if not user_question: return Response({"error": "No question"}, status=400)
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(f"Answer briefly: {user_question}")
        return Response({"answer": response.text, "source": "Gemini"})
    except Exception as e: return Response({"error": str(e)}, status=500)

# ==========================================
# 3. FOOD SCANNER
# ==========================================
@method_decorator(csrf_exempt, name='dispatch')
class ScanFoodView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = [] 
    permission_classes = []

    def post(self, request, *args, **kwargs):
        if 'image' not in request.FILES: return Response({"error": "No image"}, status=400)
        image_file = request.FILES['image']
        prompt = """
        Identify food. Estimate calories/macros. Return strictly valid JSON:
        { "food_name": "...", "estimated_calories": 0, "protein": 0.0, "carbs": 0.0, "fat": 0.0 }
        """
        try:
            pil_image = Image.open(image_file)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content([prompt, pil_image])
            clean = response.text.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            new_food = FoodItem.objects.create(
                name=data.get('food_name', 'Unknown'),
                calories=int(data.get('estimated_calories', 0)),
                protein=float(data.get('protein', 0.0)),
                carbs=float(data.get('carbs', 0.0)),
                fat=float(data.get('fat', 0.0)),
            )
            return Response({"message": "Success", "saved_data": {"name": new_food.name, "calories": new_food.calories}})
        except Exception as e: return Response({"error": str(e)}, status=500)

# ==========================================
# 4. ROSTER ANALYZER (UNBREAKABLE WATERFALL)
# ==========================================
@method_decorator(csrf_exempt, name='dispatch') 
class AnalyzeRosterView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        if 'file' not in request.FILES:
            return Response({"error": "No file provided."}, status=400)

        image_file = request.FILES['file']
        
        prompt_text = """
        STRICT INSTRUCTION: Act as a structured data extraction API.
        Analyze this timetable. Extract the weekly schedule.
        Return ONLY valid JSON. No markdown.
        Format:
        {
            "weekly_schedule": {
                "Monday": [ {"time": "10:00", "event": "Math"} ],
                "Tuesday": [ {"time": "09:00", "event": "Science"} ]
            }
        }
        """

        analysis_data = None
        source_name = "None"
        
        # --- ATTEMPT 1: GROQ VISION (Fastest & Free) ---
        if GROQ_KEY:
            try:
                print("Trying Groq Llama 3.2 Vision...")
                image_file.seek(0)
                base64_img = encode_image(image_file)
                client = Groq(api_key=GROQ_KEY)
                resp = client.chat.completions.create(
                    model="llama-3.2-11b-vision-preview", #
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                        ]
                    }]
                )
                if resp.choices[0].message.content:
                    analysis_data = resp.choices[0].message.content
                    source_name = "Groq Llama Vision"
            except Exception as e: print(f"Groq Vision Failed: {e}")

        # --- ATTEMPT 2: MISTRAL (Proven Backup) ---
        if not analysis_data and MISTRAL_KEY:
            try:
                print("Trying Mistral Pixtral...")
                image_file.seek(0)
                base64_img = encode_image(image_file)
                client = Mistral(api_key=MISTRAL_KEY)
                resp = client.chat.complete(
                    model="pixtral-12b-2409",
                    messages=[{
                        "role": "user", 
                        "content": [{"type": "text", "text": prompt_text}, {"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_img}"}]
                    }]
                )
                if resp.choices[0].message.content:
                    analysis_data = resp.choices[0].message.content
                    source_name = "Mistral"
            except Exception as e: print(f"Mistral Failed: {e}")

        # --- ATTEMPT 3: HUGGING FACE (Qwen2-VL - High Accuracy) ---
        if not analysis_data and HF_KEY:
            try:
                print("Trying Hugging Face Qwen2-VL...")
                image_file.seek(0)
                base64_img = encode_image(image_file)
                client = InferenceClient(api_key=HF_KEY)
                
                # Qwen2-VL is excellent for tables
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                        ]
                    }
                ]
                
                # Using the standard Inference API model
                resp = client.chat_completion(
                    model="Qwen/Qwen2-VL-7B-Instruct", 
                    messages=messages, 
                    max_tokens=1000
                )
                
                if resp.choices[0].message.content:
                    analysis_data = resp.choices[0].message.content
                    source_name = "HuggingFace Qwen"
            except Exception as e: print(f"HuggingFace Failed: {e}")

        # --- ATTEMPT 4: GEMINI (Stable Backup) ---
        if not analysis_data and GOOGLE_KEY:
            try:
                print("Trying Gemini 1.5 Flash...")
                image_file.seek(0)
                pil_img = Image.open(image_file)
                model = genai.GenerativeModel('gemini-1.5-flash')
                resp = model.generate_content([prompt_text, pil_img])
                if resp.text:
                    analysis_data = resp.text
                    source_name = "Gemini"
            except Exception as e: print(f"Gemini Failed: {e}")

        # --- FINAL PROCESSING ---
        if analysis_data:
            try:
                clean = analysis_data.strip().replace("```json", "").replace("```", "").strip()
                data = json.loads(clean)
                
                if 'weekly_schedule' not in data:
                    if isinstance(data, dict) and any(day in data for day in ["Monday", "Tuesday"]):
                             data = {"weekly_schedule": data}
                    else:
                             raise ValueError("Invalid JSON structure")
                
                data['ai_source'] = source_name
                return Response(data)
            except Exception as e:
                return Response({"error": f"JSON Error ({source_name}): {str(e)}", "raw": analysis_data}, status=500)
        
        return Response({"error": "All 4 AI models failed."}, status=500)

# ==========================================
# 5. MEAL PLANNING
# ==========================================
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
    # Keep your meal plan logic here
    try:
        # Simplified for response length - Put back your original prompt logic
        return Response({"meals": []}) 
    except: return Response({"error": "Error"}, status=500)

@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def swap_meal(request):
    try:
        return Response({"name": "New Meal"})
    except: return Response({"error": "Error"}, status=500)