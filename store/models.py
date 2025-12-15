from django.db import models
from django.contrib.auth.models import User

# --- 1. USER PROFILE (Enhanced) ---
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    
    # Physical Stats
    current_weight = models.FloatField(help_text="Weight in kg", default=70.0)
    height = models.IntegerField(help_text="Height in cm", default=170)
    
    # Goals & Activity
    GOAL_CHOICES = [
        ('SHRED', 'Shred (Fat Loss)'),
        ('BULK', 'Bulk (Muscle Gain)'),
        ('MAINTAIN', 'Maintain'),
    ]
    goal = models.CharField(max_length=10, choices=GOAL_CHOICES, default='MAINTAIN')
    
    ACTIVITY_CHOICES = [
        ('SEDENTARY', 'Sedentary (Office Job)'),
        ('ACTIVE', 'Active (Daily Exercise)'),
        ('ATHLETE', 'Athlete (Physical Job/Sport)'),
    ]
    activity_level = models.CharField(max_length=10, choices=ACTIVITY_CHOICES, default='SEDENTARY')
    
    # Nutrition Targets (Calculated based on Goal)
    daily_calorie_target = models.IntegerField(default=2000)
    protein_goal = models.IntegerField(default=150)
    carb_goal = models.IntegerField(default=250)
    fat_goal = models.IntegerField(default=70)

    def __str__(self):
        return f"{self.user.username} Profile"

# --- 2. GLOBAL KNOWLEDGE BASE (NEW - The "Brain") ---
# This stores the "Golden Copy" of food data.
# 1. Normalizes food names (e.g. "butter paneer" -> "Paneer Butter Masala")
# 2. Stores rich data (Ingredients, Confidence)
# 3. Saves API costs (0 calls if found here)
class FoodKnowledge(models.Model):
    name = models.CharField(max_length=200, unique=True, db_index=True) # Unique & Indexed for speed
    ingredients = models.JSONField(default=list) # Stores ["paneer", "butter", "cream"]
    
    # Nutrition per Serving
    calories = models.IntegerField()
    protein = models.FloatField()
    carbs = models.FloatField()
    fat = models.FloatField()
    
    # AI Metadata
    confidence_score = models.IntegerField(default=80)
    source = models.CharField(max_length=50, default="AI") # "AI", "Manual", "Cache"
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.calories} kcal)"

# --- 3. DAILY LOGS (What User Ate) ---
class FoodItem(models.Model):
    # Link to specific user (Crucial for multi-user app)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    name = models.CharField(max_length=200)
    calories = models.IntegerField()
    protein = models.FloatField(default=0.0)
    carbs = models.FloatField(default=0.0)
    fat = models.FloatField(default=0.0)
    
    # Optional: Link back to the master knowledge base
    knowledge_source = models.ForeignKey(FoodKnowledge, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True) # For sorting by "Recent"

    def __str__(self):
        return f"{self.name} ({self.calories} kcal)"