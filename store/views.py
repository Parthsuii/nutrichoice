from rest_framework.decorators import api_view
from rest_framework.response import Response
# 1. UPDATED IMPORT: Added RetrieveUpdateDestroyAPIView for Deleting
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import serializers
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

# --- CONFIGURATION ---
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY")
GROQ_KEY = os.environ.get("GROQ_API_KEY")

if GOOGLE_KEY:
    genai.configure(api_key=GOOGLE_KEY)

# --- HELPER: Convert Image to Base64 for Mistral ---
def encode_image(image_file):
    return base64.b64encode(image_file.read()).decode('utf-8')

# --- VIEWS ---

# 1. LIST & CREATE FOODS
class FoodItemList(ListCreateAPIView):
    queryset = FoodItem.objects.all()
    serializer_class = FoodItemSerializer

# 2. NEW: DELETE & UPDATE FOODS (For the Delete Button)
class FoodItemDetail(RetrieveUpdateDestroyAPIView):
    queryset = FoodItem.objects.all()
    serializer_class = FoodItemSerializer

@api_view(['POST'])
def ask_nutritionist(request):
    """
    TEXT-ONLY Endpoint: Answer questions like "Is a banana healthy?"
    """
    user_question = request.data.get('question')
    if not user_question:
        return Response({"error": "Please provide a 'question'"}, status=400)

    # ATTEMPT 1: GOOGLE GEMINI
    try:
        print("Attempting Gemini...")
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(f"You are a nutritionist. Answer briefly: {user_question}")
        return Response({"answer": response.text, "source": "Gemini"})
    except Exception as e_gemini:
        print(f"Gemini Failed: {e_gemini}")
        
        # ATTEMPT 2: MISTRAL AI
        if MISTRAL_KEY:
            try:
                print("Switching to Mistral...")
                client = Mistral(api_key=MISTRAL_KEY)
                chat_response = client.chat.complete(
                    model="mistral-tiny",
                    messages=[{"role": "system", "content": "You are a helpful nutritionist."}, {"role": "user", "content": user_question}]
                )
                return Response({"answer": chat_response.choices[0].message.content, "source": "Mistral"})
            except:
                pass
        
        # ATTEMPT 3: GROQ
        if GROQ_KEY:
            try:
                print("Switching to Groq...")
                client = Groq(api_key=GROQ_KEY)
                completion = client.chat.completions.create(
                    model="llama3-8b-8192",
                    messages=[{"role": "system", "content": "You are a helpful nutritionist."}, {"role": "user", "content": user_question}]
                )
                return Response({"answer": completion.choices[0].message.content, "source": "Groq"})
            except:
                pass

    return Response({"error": "All AI services are currently down."}, status=503)

# --- 3. CLASS-BASED VIEW FOR IMAGE SCANNING (WITH AUTO-SAVE) ---
class ScanFoodView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    serializer_class = FoodImageSerializer

    def post(self, request, *args, **kwargs):
        """
        IMAGE Endpoint: Upload a photo -> Get Calorie Count AND Save to Database
        """
        if 'image' not in request.FILES:
            return Response({"error": "No image provided"}, status=400)
        
        image_file = request.FILES['image']
        
        # Prompt for strict JSON output
        prompt = """
        Analyze this food image. Identify the food items.
        Estimate the calories and macros (Protein, Carbs, Fats).
        Your response MUST be ONLY a single, valid JSON object, without any surrounding text, markdown, or commentary.
        
        JSON Format Required:
        {
            "food_name": "...",
            "estimated_calories": integer,
            "protein": float,
            "carbs": float,
            "fat": float
        }
        """

        analysis_data = None
        source_name = None

        # Try Gemini Vision
        try:
            print("Scanning with Gemini Vision...")
            pil_image = Image.open(image_file)
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            response = model.generate_content([prompt, pil_image])
            analysis_data = response.text
            source_name = "Gemini"
        except Exception as e_gemini:
            print(f"Gemini Vision Failed: {e_gemini}")
            
            # Try Mistral Vision Fallback
            if MISTRAL_KEY:
                try:
                    print("Switching to Mistral Pixtral...")
                    image_file.seek(0)
                    base64_image = encode_image(image_file)
                    client = Mistral(api_key=MISTRAL_KEY)
                    chat_response = client.chat.complete(
                        model="pixtral-12b-2409",
                        messages=[{
                            "role": "user",
                            "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"}]
                        }]
                    )
                    analysis_data = chat_response.choices[0].message.content
                    source_name = "Mistral Pixtral"
                except Exception as e_mistral:
                    print(f"Mistral Failed: {e_mistral}")

        # Parse and Save to Database
        if analysis_data:
            try:
                clean_json_str = analysis_data.strip().replace("```json", "").replace("```", "").strip()
                parsed_data = json.loads(clean_json_str)

                new_food = FoodItem(
                    name=parsed_data.get('food_name', 'Unknown Scanned Food'),
                    calories=int(parsed_data.get('estimated_calories', 0)),
                    protein=float(parsed_data.get('protein', 0.0)),
                    carbs=float(parsed_data.get('carbs', 0.0)),
                    fat=float(parsed_data.get('fat', 0.0)),
                )
                new_food.save()

                return Response({
                    "message": "Food analyzed and saved successfully!",
                    "source": source_name,
                    "saved_data": {
                        "name": new_food.name,
                        "calories": new_food.calories
                    }
                })
            except Exception as e:
                return Response({"error": f"Save failed: {str(e)}", "raw_output": analysis_data}, status=500)
        
        return Response({"error": "Analysis failed after all attempts."}, status=500)

# --- 4. PHYSIQUE ARCHITECT (SELF-HEALING) ---
@api_view(['POST', 'GET'])
def user_profile_view(request):
    """
    Handles User Onboarding.
    GET: Retrieve profile data.
    POST: Save profile data and auto-calculate 'daily_calorie_target'.
    """
    if not User.objects.exists():
        try:
            User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        except:
            pass 

    user = User.objects.first()
    
    profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            'current_weight': 70.0,
            'height': 170,
            'goal': 'MAINTAIN',
            'activity_level': 'SEDENTARY'
        }
    )

    if request.method == 'GET':
        serializer = UserProfileSerializer(profile)
        return Response(serializer.data)

    if request.method == 'POST':
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            saved_profile = serializer.save()
            
            weight = saved_profile.current_weight
            height = saved_profile.height
            age = 25 
            
            bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
            
            multipliers = {
                'SEDENTARY': 1.2,
                'ACTIVE': 1.55,
                'ATHLETE': 1.9
            }
            tdee = bmr * multipliers.get(saved_profile.activity_level, 1.2)
            
            if saved_profile.goal == 'SHRED':
                final_target = tdee - 500
            elif saved_profile.goal == 'BULK':
                final_target = tdee + 500
            else:
                final_target = tdee
                
            saved_profile.daily_calorie_target = int(final_target)
            saved_profile.save()
            
            return Response({
                "message": "Profile updated!",
                "calculated_calories": saved_profile.daily_calorie_target,
                "goal": saved_profile.goal
            })
            
        return Response(serializer.errors, status=400)

# --- 5. NEW: CONTEXT CHEF MEAL PLANNER ---
@api_view(['POST'])
def generate_meal_plan(request):
    """
    Generates a full day's meal plan based on Goal, Calories, and Context.
    """
    user_goal = request.data.get('user_goal', 'Maintain')
    calories = request.data.get('daily_calories', 2000)
    context = request.data.get('activity_context', 'Standard Day')
    ingredients = request.data.get('available_ingredients', [])
    
    prompt = f"""
    You are an elite sports nutritionist. Create a 1-day meal plan.
    GOAL: {user_goal}
    TARGET CALORIES: {calories}
    CONTEXT: {context} (e.g. if 'Sore', add anti-inflammatory foods. If 'Exam', add brain foods).
    PANTRY: Use these if possible: {', '.join(ingredients)}
    
    Output strictly valid JSON with this structure:
    {{
        "analysis": "Brief explanation of why this plan fits the context.",
        "meals": [
            {{
                "type": "Breakfast",
                "name": "Dish Name",
                "calories": 500,
                "nutrients": {{"protein": "30g", "carbs": "40g", "fat": "15g"}},
                "ingredients": ["Egg", "Bread"],
                "recipe": ["Step 1", "Step 2"]
            }}
        ]
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(prompt)
        clean_json = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
        return Response(data)
    except Exception as e:
        print(f"AI Generation Failed: {e}")
        return Response({"error": "Failed to generate plan. AI might be busy."}, status=500)

# --- 6. NEW: MEAL SWAPPER ---
@api_view(['POST'])
def swap_meal(request):
    """
    Swaps a SINGLE meal for a new option while keeping the context.
    """
    context = request.data.get('activity_context', 'Standard Day')
    user_goal = request.data.get('user_goal', 'Maintain')
    
    prompt = f"""
    Suggest ONE alternative meal for a user with Goal: {user_goal} and Context: {context}.
    Return strictly valid JSON for a single meal object:
    {{
        "name": "New Dish Name",
        "calories": 500,
        "nutrients": {{"protein": "30g", "carbs": "40g", "fat": "15g"}},
        "ingredients": ["List", "of", "items"],
        "recipe": ["Step 1", "Step 2"]
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(prompt)
        clean_json = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
        return Response(data)
    except Exception as e:
        return Response({"error": str(e)}, status=500)