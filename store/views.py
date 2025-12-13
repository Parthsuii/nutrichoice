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
from openai import OpenAI  # Standard client for OpenRouter

# --- IMPORTS FROM YOUR APP ---
from .models import FoodItem, UserProfile
from .serializers import FoodItemSerializer, UserProfileSerializer, FoodImageSerializer

# --- CONFIGURATION ---
# We now primarily rely on OpenRouter for everything!
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
SITE_URL = "https://nutrichoice.onrender.com"  # Optional, for OpenRouter rankings
APP_NAME = "NutriChoice"

# --- HELPER: Call OpenRouter ---
def call_openrouter_vision(model_name, prompt, base64_image):
    """
    Generic helper to call ANY vision model via OpenRouter.
    """
    if not OPENROUTER_API_KEY:
        raise Exception("OpenRouter API Key missing.")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

    completion = client.chat.completions.create(
        extra_headers={
            "HTTP-Referer": SITE_URL,
            "X-Title": APP_NAME,
        },
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        },
                    },
                ],
            }
        ],
    )
    return completion.choices[0].message.content

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
    """Checks if OpenRouter is working with free models."""
    results = {}

    if not OPENROUTER_API_KEY:
        return Response({"Status": "FAILED: OPENROUTER_API_KEY is missing in Render Environment."})

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

    # List of FREE models to test
    models_to_test = [
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.2-11b-vision-instruct:free",
        "mistralai/pixtral-12b:free",
        "qwen/qwen-2-vl-7b-instruct:free"
    ]

    for model in models_to_test:
        try:
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hi"}],
            )
            results[model] = "SUCCESS"
        except Exception as e:
            results[model] = f"FAILED: {str(e)}"

    return Response({"OpenRouter Status": results})

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
        # Using OpenRouter for text
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-exp:free",  # Free & Fast
            messages=[{"role": "user", "content": f"You are a nutritionist. Answer briefly: {user_question}"}]
        )
        return Response({"answer": response.choices[0].message.content, "source": "OpenRouter Gemini"})
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
        base64_img = encode_image(image_file)

        prompt = """
        Identify food. Estimate calories/macros. Return strictly valid JSON:
        { "food_name": "...", "estimated_calories": 0, "protein": 0.0, "carbs": 0.0, "fat": 0.0 }
        """
        try:
            # Using OpenRouter Vision
            response_text = call_openrouter_vision("google/gemini-2.0-flash-exp:free", prompt, base64_img)

            clean = response_text.strip().replace("```json", "").replace("```", "").strip()
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
# 4. ROSTER ANALYZER (OPENROUTER FREE CASCADE)
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
        base64_img = encode_image(image_file)

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

        # LIST OF FREE VISION MODELS ON OPENROUTER (Priority Order)
        # 1. Gemini 2.0 Flash (Best quality, Free)
        # 2. Llama 3.2 11B Vision (Fastest, Free)
        # 3. Pixtral 12B (Reliable, Free)
        # 4. Qwen 2 VL (Open Source Standard, Free)
        models_to_try = [
            "google/gemini-2.0-flash-exp:free",
            "meta-llama/llama-3.2-11b-vision-instruct:free",
            "mistralai/pixtral-12b:free",
            "qwen/qwen-2-vl-7b-instruct:free"
        ]

        for model in models_to_try:
            if analysis_data: break  # Stop if we have data

            try:
                print(f"Attempting Roster Scan with {model} via OpenRouter...")
                response_text = call_openrouter_vision(model, prompt_text, base64_img)

                if response_text:
                    analysis_data = response_text
                    source_name = f"OpenRouter {model}"
            except Exception as e:
                print(f"Failed with {model}: {e}")

        # --- FINAL PROCESSING ---
        if analysis_data:
            try:
                clean = analysis_data.strip().replace("```json", "").replace("```", "").strip()
                data = json.loads(clean)

                if 'weekly_schedule' not in data:
                    if isinstance(data, dict):
                        data = {"weekly_schedule": data}
                    else:
                        raise ValueError("Invalid JSON")

                data['ai_source'] = source_name
                return Response(data)
            except Exception as e:
                return Response({"error": f"JSON Error ({source_name}): {str(e)}", "raw": analysis_data}, status=500)

        return Response({"error": "All OpenRouter free models failed to scan the image."}, status=500)

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
    try:
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