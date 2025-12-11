from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.generics import ListCreateAPIView
from .models import FoodItem
from .serializers import FoodItemSerializer
import google.generativeai as genai
import os

# Configure the API
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

# 1. Food List View
class FoodItemList(ListCreateAPIView):
    queryset = FoodItem.objects.all()
    serializer_class = FoodItemSerializer

# 2. AI Nutritionist (Using Gemini 2.0 Flash Experimental)
@api_view(['POST'])
def ask_nutritionist(request):
    user_question = request.data.get('question')
    if not user_question:
        return Response({"error": "Please provide a 'question'"}, status=400)

    try:
        # Using the Gemini 2.0 Experimental model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        response = model.generate_content(
            f"You are an expert nutritionist. Answer briefly: {user_question}"
        )
        return Response({"answer": response.text})

    except Exception as e:
        # If even this fails, we will see the specific error from the 2.0 model
        return Response({"error": str(e)}, status=500)