from django.urls import path
from . import views

urlpatterns = [
    # --- 1. CORE AI ENDPOINTS ---
    # This single view handles BOTH Image Uploads (Camera) and Text Search
    path('scan-food/', views.ScanFoodView.as_view(), name='scan-food'),
    
    # Roster/Timetable Scanner
    path('analyze-roster/', views.AnalyzeRosterView.as_view(), name='analyze-roster'),
    
    # AI Chat/Q&A
    path('ask-ai/', views.ask_nutritionist, name='ask-nutritionist'),
    
    # Diagnostic (Check if Google/OpenRouter keys are working)
    path('ai-check/', views.ai_status_check, name='ai-status-check'),

    # --- 2. DATA ENDPOINTS ---
    path('foods/', views.FoodItemList.as_view(), name='food-list'),
    path('foods/<int:pk>/', views.FoodItemDetail.as_view(), name='food-detail'),
    
    # --- 3. USER ENDPOINTS ---
    path('profile/', views.user_profile_view, name='user-profile'),
    path('generate-meal-plan/', views.generate_meal_plan, name='generate-meal-plan'),
    path('swap-meal/', views.swap_meal, name='swap-meal'),
]
