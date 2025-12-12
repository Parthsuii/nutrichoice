from django.urls import path,re_path
from . import views
from django.views.decorators.csrf import csrf_exempt


urlpatterns = [
    path('foods/', views.FoodItemList.as_view()),
    path('foods/<int:pk>/', views.FoodItemDetail.as_view()),
    path('ask-ai/', views.ask_nutritionist),
    path('scan-food/', views.ScanFoodView.as_view()),
    path('profile/', views.user_profile_view),
    path('generate-meal-plan', views.generate_meal_plan),
    path('swap-meal', views.swap_meal),
    path('scan-food/', csrf_exempt(views.ScanFoodView.as_view())),
    path('analyze-roster', views.AnalyzeRosterView.as_view(), name='analyze-roster'),
    re_path(r'^analyze-roster/?$', csrf_exempt(views.AnalyzeRosterView.as_view())),
]
