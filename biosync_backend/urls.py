"""
URL configuration for biosync_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from app import views  # <--- Import your views from the 'app' folder

urlpatterns = [
    path('admin/', admin.site.urls),

    # --- API Endpoints (Matches your Flutter App) ---
    path('analyze-roster/', views.analyze_roster, name='analyze_roster'),
    path('log-meal', views.log_meal, name='log_meal'),
    path('snap-meal', views.snap_meal, name='snap_meal'),
    path('calculate-score', views.calculate_score, name='calculate_score'),
    path('compare-prices', views.compare_prices, name='compare_prices'),
    path('generate-meal-plan', views.generate_meal_plan, name='generate_meal_plan'),
    path('swap-meal', views.swap_meal, name='swap_meal'),
    path('generate-workout', views.generate_workout, name='generate_workout'),
    path('admin/', admin.site.urls),
    path('api/', include('store.urls')),
]