from django.urls import path
from . import views

urlpatterns = [
    path('foods/', views.FoodItemList.as_view()),
    path('foods/<int:pk>/', views.FoodItemDetail.as_view()),
    path('ask-ai/', views.ask_nutritionist),
    path('scan-food/', views.ScanFoodView.as_view()),
    path('profile/', views.user_profile_view),
]