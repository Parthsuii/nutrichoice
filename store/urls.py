from django.urls import path
from . import views

urlpatterns = [
    path('foods/', views.FoodItemList.as_view()),
]