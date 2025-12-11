from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.generics import ListCreateAPIView
from .models import FoodItem
from .serializers import FoodItemSerializer
import os

# --- AI LIBRARIES ---
import google.generativeai as genai
from mistralai import Mistral
from groq import Groq

# --- CONFIGURATION ---
# Load all keys (It's okay if some are None, we just won't use that fallback)
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY")
GROQ_KEY = os.environ.get("GROQ_API_KEY")

if GOOGLE_KEY:
    genai.configure(api_key=GOOGLE_KEY)

# --- VIEWS ---

class FoodItemList(ListCreateAPIView):
    queryset = FoodItem.objects.all()
    serializer_class = FoodItemSerializer

@api_view(['POST'])
def ask_nutritionist(request):
    user_question = request.data.get('question')
    if not user_question:
        return Response({"error": "Please provide a 'question'"}, status=400)

    # ---------------------------------------------------------
    # ATTEMPT 1: GOOGLE GEMINI (Primary)
    # ---------------------------------------------------------
    try:
        print("Attempting Gemini...")
        # Using the version you found works: 2.0 Flash Experimental
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(f"You are a nutritionist. Answer briefly: {user_question}")
        
        return Response({
            "answer": response.text, 
            "source": "Gemini"  # Tells you which AI answered
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

    # If we get here, EVERYTHING failed.
    return Response({
        "error": "All AI services are currently down. Please try again later."
    }, status=503)