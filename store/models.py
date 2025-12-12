from django.db import models
from django.contrib.auth.models import User

class FoodItem(models.Model):
    name = models.CharField(max_length=200)
    calories = models.IntegerField()
    protein = models.FloatField()
    carbs = models.FloatField(default=0.0)
    fat = models.FloatField(default=0.0)
    
    def __str__(self):
        return self.name
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    current_weight = models.FloatField(help_text="Weight in kg")
    height = models.IntegerField(help_text="Height in cm")
    
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
    
    daily_calorie_target = models.IntegerField(default=2000)

    def __str__(self):
        return f"{self.user.username} Profile"
    # Create your models here.
