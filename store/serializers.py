from rest_framework import serializers
from .models import FoodItem,UserProfile


class FoodItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodItem
        fields = ['id', 'name', 'calories', 'protein']
        class UserProfileSerializer(serializers.ModelSerializer):
         class Meta:
          model = UserProfile
          fields = ['current_weight', 'height', 'goal', 'activity_level', 'daily_calorie_target']
          read_only_fields = ['daily_calorie_target']