from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.generics import ListCreateAPIView
from rest_framework.views import APIView  # <--- Needed for the UI fix
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import serializers    # <--- Needed for the input form
from PIL import Image
from .models import FoodItem
from .serializers import FoodItemSerializer
import os
import base64

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
    """
    Mistral requires images to be sent as Base64 strings.
    This helper converts the uploaded file into that format.
    """
    return base64.b64encode(image_file.read()).decode('utf-8')

# --- 1. SERIALIZER FOR IMAGE UPLOAD (Fixes the UI button) ---
class FoodImageSerializer(serializers.Serializer):
    image = serializers.ImageField()

# --- VIEWS ---

class FoodItemList(ListCreateAPIView):
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

    # ---------------------------------------------------------
    # ATTEMPT 1: GOOGLE GEMINI (Primary)
    # ---------------------------------------------------------
    try:
        print("Attempting Gemini...")
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(f"You are a nutritionist. Answer briefly: {user_question}")
        
        return Response({
            "answer": response.text, 
            "source": "Gemini"
        })

    except Exception as e_gemini:
        print(f"Gemini Failed: {e_gemini}")

        # ---------------------------------------------------------
        # ATTEMPT 2: MISTRAL AI (Fallback #1)
        # ---------------------------------------------------------
        if MISTRAL_KEY:
            try:
                print("Switching to Mistral...")
                client = Mistral(api_key=MISTRAL_KEY)
                chat_response = client.chat.complete(
                    model="mistral-tiny",
                    messages=[
                        {"role": "system", "content": "You are a helpful nutritionist."},
                        {"role": "user", "content": user_question},
                    ]
                )
                return Response({
                    "answer": chat_response.choices[0].message.content,
                    "source": "Mistral"
                })
            except Exception as e_mistral:
                print(f"Mistral Failed: {e_mistral}")
        
        # ---------------------------------------------------------
        # ATTEMPT 3: GROQ (Fallback #2)
        # ---------------------------------------------------------
        if GROQ_KEY:
            try:
                print("Switching to Groq...")
                client = Groq(api_key=GROQ_KEY)
                completion = client.chat.completions.create(
                    model="llama3-8b-8192",
                    messages=[
                        {"role": "system", "content": "You are a helpful nutritionist."},
                        {"role": "user", "content": user_question}
                    ]
                )
                return Response({
                    "answer": completion.choices[0].message.content,
                    "source": "Groq"
                })
            except Exception as e_groq:
                print(f"Groq Failed: {e_groq}")

    return Response({"error": "All AI services are currently down."}, status=503)

# --- 2. CLASS-BASED VIEW FOR IMAGE SCANNING (Fixes the UI button) ---
class ScanFoodView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    serializer_class = FoodImageSerializer

    def post(self, request, *args, **kwargs):
        """
        IMAGE Endpoint: Upload a photo -> Get Calorie Count
        """
        if 'image' not in request.FILES:
            return Response({"error": "No image provided"}, status=400)
        
        image_file = request.FILES['image']
        
        # Define the Prompt
        prompt = """
        Analyze this food image. Identify the food items.
        Estimate the calories and macros (Protein, Carbs, Fats).
        Return the answer in this JSON format:
        {
            "food_name": "...",
            "estimated_calories": "...",
            "protein": "...",
            "carbs": "...",
            "fat": "..."
        }
        """

        # ---------------------------------------------------------
        # ATTEMPT 1: GOOGLE GEMINI VISION (Primary)
        # ---------------------------------------------------------
        try:
            print("Scanning with Gemini Vision...")
            pil_image = Image.open(image_file)
            
            # Use Gemini 2.0 Flash (Supports Images)
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            response = model.generate_content([prompt, pil_image])
            
            return Response({"analysis": response.text, "source": "Gemini"})

        except Exception as e_gemini:
            print(f"Gemini Vision Failed: {e_gemini}")

            # ---------------------------------------------------------
            # ATTEMPT 2: MISTRAL PIXTRAL (Fallback)
            # ---------------------------------------------------------
            if MISTRAL_KEY:
                try:
                    print("Switching to Mistral Pixtral...")
                    
                    # IMPORTANT: Reset file pointer so Mistral can read it from start
                    image_file.seek(0)
                    base64_image = encode_image(image_file)

                    client = Mistral(api_key=MISTRAL_KEY)

                    chat_response = client.chat.complete(
                        model="pixtral-12b-2409",  # Mistral's Vision Model
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"}
                                ]
                            }
                        ]
                    )
                    
                    return Response({
                        "analysis": chat_response.choices[0].message.content,
                        "source": "Mistral Pixtral"
                    })

                except Exception as e_mistral:
                    print(f"Mistral Pixtral Failed: {e_mistral}")
                    return Response({"error": f"Both AIs failed. Mistral Error: {str(e_mistral)}"}, status=500)

        return Response({"error": "Analysis failed"}, status=500)