import google.generativeai as genai
import os

# 🔑 REPLACE WITH YOUR ACTUAL KEY
GOOGLE_API_KEY = "AIzaSyAyCUAZ6wzZYpEoU5G68AL619cxR6OWFuM"
genai.configure(api_key=GOOGLE_API_KEY)

print("--- AVAILABLE MODELS ---")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)