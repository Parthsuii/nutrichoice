from django.db import models

class FoodItem(models.Model):
    name = models.CharField(max_length=200)
    calories = models.IntegerField()
    protein = models.FloatField()
    carbs = models.FloatField(default=0.0)
    fat = models.FloatField(default=0.0)
    
    def __str__(self):
        return self.name
# Create your models here.
