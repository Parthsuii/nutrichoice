from django.shortcuts import render
from rest_framework.generics import ListCreateAPIView
from .models import FoodItem
from .serializers import FoodItemSerializer

class FoodItemList(ListCreateAPIView):
    queryset = FoodItem.objects.all()
    serializer_class = FoodItemSerializer

# Create your views here.
