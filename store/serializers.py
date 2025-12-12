from rest_framework import serializers
from .models import FoodItem, UserProfile

# 1. Food Item Serializer
class FoodItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodItem
        fields = ['id', 'name', 'calories', 'protein', 'carbs', 'fat']

# 2. Image Upload Serializer
class FoodImageSerializer(serializers.Serializer):
    image = serializers.ImageField()

# 3. User Profile Serializer
class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['current_weight', 'height', 'goal', 'activity_level', 'daily_calorie_target']
        read_only_fields = ['daily_calorie_target']