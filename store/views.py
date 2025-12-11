from django.shortcuts import render
from rest_framework.generics import ListCreateAPIView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import FoodItem
from .serializers import FoodItemSerializer
import google.generativeai as genai
import os

# 1. Configure Google AI with the key from Render
# (It will look for a variable named 'GOOGLE_API_KEY')
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

# Existing View (Do not change)
class FoodItemList(ListCreateAPIView):
    queryset = FoodItem.objects.all()
    serializer_class = FoodItemSerializer

# 2. New AI View
@api_view(['POST'])
def ask_nutritionist(request):
    """
    Takes a question from the user and asks Google Gemini.
    """
    user_question = request.data.get('question')

    # Basic check: Did they actually ask something?
    if not user_question:
        return Response({"error": "Please provide a 'question'"}, status=400)

    try:
        # Create the model
        model = genai.GenerativeModel('gemini-pro')
        
        # Ask the question
        response = model.generate_content(
            f"You are an expert nutritionist. Answer this question briefly: {user_question}"
        )
        
        # Send the answer back to the App/Website
        return Response({"answer": response.text})

    except Exception as e:
        # If something goes wrong (like a bad API key), tell us why
        return Response({"error": str(e)}, status=500)