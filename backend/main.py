import json
import io
import time
import requests
import random
import base64
import re
import ast
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from PIL import Image

# --- 1. CONFIGURATION ---
KEYS = {
    "GEMINI": "AIzaSyAyCUAZ6wzZYpEoU5G68AL619cxR6OWFuM", 
    "GROQ": "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",
    "COHERE": "WVMMG2bBfbmNImmHV9TXWB1dz2U0ePVOL0HSXVaH",
    "MISTRAL": "jvZCWrEEw92UXOdTAISsim9eVUT1UkSL" 
}

genai.configure(api_key=KEYS["GEMINI"])

# --- HELPER: ROBUST JSON PARSER ---
def clean_and_parse_json(text):
    """
    Surgically extracts JSON from messy AI responses.
    """
    print(f"\n--- RAW AI RESPONSE START ---\n{text}\n--- RAW AI RESPONSE END ---\n")

    # 1. Regex to find the largest outer block starting with { and ending with }
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        json_str = match.group(0)
    else:
        return None

    # 2. Try standard parsing
    try:
        return json.loads(json_str)
    except:
        pass

    # 3. Last Resort: Python literal_eval
    try:
        return ast.literal_eval(json_str)
    except:
        return None

# --- 2. VISION ENGINE (Gemini -> Mistral -> Groq) ---
def generate_vision_content(prompt, image_bytes):
    # 1. Try Gemini
    try:
        model = genai.GenerativeModel('gemini-1.5-flash') 
        image = Image.open(io.BytesIO(image_bytes))
        response = model.generate_content([prompt, image])
        return response.text
    except Exception as e:
        print(f"⚠️ Gemini Vision Failed: {e}")

    # 2. Try Mistral Pixtral
    try:
        print("👁️ Trying Mistral Pixtral...")
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        headers = {"Authorization": f"Bearer {KEYS['MISTRAL']}", "Content-Type": "application/json"}
        data = {
            "model": "pixtral-12b-2409", 
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt + " Return JSON object ONLY. No conversational text."},
                        {"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"}
                    ]
                }
            ],
            "temperature": 0.1
        }
        resp = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=data)
        if resp.status_code == 200: 
            return resp.json()['choices'][0]['message']['content']
        else: 
            print(f"⚠️ Mistral Error: {resp.text}")
    except Exception as e:
        print(f"⚠️ Mistral Vision Failed: {e}")

    # 3. Try Groq Vision
    try:
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        headers = {"Authorization": f"Bearer {KEYS['GROQ']}", "Content-Type": "application/json"}
        data = {
            "model": "llama-3.2-11b-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ]
        }
        resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
        if resp.status_code == 200: return resp.json()['choices'][0]['message']['content']
    except:
        pass

    return None

# --- 3. TEXT ENGINE ---
def generate_text_with_failover(user_prompt, system_instruction=""):
    # 1. Gemini
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-lite')
        return model.generate_content(f"{system_instruction}\n{user_prompt}").text
    except: pass

    # 2. Groq
    try:
        headers = {"Authorization": f"Bearer {KEYS['GROQ']}", "Content-Type": "application/json"}
        data = {"messages": [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_prompt}], "model": "llama3-8b-8192"}
        resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
        if resp.status_code == 200: return resp.json()['choices'][0]['message']['content']
    except: pass

    # 3. Mistral
    try:
        headers = {"Authorization": f"Bearer {KEYS['MISTRAL']}", "Content-Type": "application/json"}
        data = {"messages": [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_prompt}], "model": "open-mistral-nemo"}
        resp = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=data)
        if resp.status_code == 200: return resp.json()['choices'][0]['message']['content']
    except: pass

    return None

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---
class MealPlanRequest(BaseModel):
    user_goal: str
    daily_calories: int
    dietary_preference: str = "Indian"
    available_ingredients: List[str] = [] 
    activity_context: str = "Standard Day"

class WorkoutRequest(BaseModel):
    context: str

class MealLogRequest(BaseModel):
    meal_description: str 

class PriceRequest(BaseModel):
    item_name: str

# --- ENDPOINTS ---

@app.post("/snap-meal")
async def log_meal_image(file: UploadFile = File(...), user_goal: str = Form("Maintain")):
    try:
        contents = await file.read()
        
        prompt = f"""
        Analyze the food in this image based on the User Goal: {user_goal}.
        
        TASKS:
        1. Identify the specific food items visible (e.g., "Paneer", "Spinach", "Roti").
        2. Estimate calories and macros.
        3. Determine if this fits the goal "{user_goal}".
        
        RETURN JSON ONLY (No markdown):
        {{
            "estimated_calories": 0,
            "macros": {{ "protein": "0g", "carbs": "0g", "fat": "0g" }},
            "ingredients": ["Item 1", "Item 2", "Item 3"],
            "diet_fit": "Fits Goal" or "Does Not Fit",
            "advice": "1 sentence explanation."
        }}
        """
        raw_text = generate_vision_content(prompt, contents)
        
        if raw_text:
            data = clean_and_parse_json(raw_text)
            if data: return data
            else: raise Exception("Parse Failed")
        else: 
            raise Exception("All AIs Failed")

    except Exception as e:
        print(f"Snap Error: {e}")
        return {
            "estimated_calories": 0, 
            "macros": {"protein": "0g", "carbs": "0g", "fat": "0g"}, 
            "ingredients": ["Scan Failed"], 
            "diet_fit": "Unknown",
            "advice": "Could not analyze image."
        }

@app.post("/analyze-roster")
async def analyze_roster(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        prompt = "Extract weekly schedule to JSON. Keys=Days, Values=List of {time, event}. RAW JSON ONLY."
        
        raw_text = generate_vision_content(prompt, contents)
        if raw_text:
            data = clean_and_parse_json(raw_text)
            if data: return data
            
        raise Exception("Parse Error")
    except:
        return {"weekly_schedule": {"Error": [{"time": "00:00", "event": "AI Offline"}]}}

@app.post("/generate-meal-plan")
def generate_meal_plan(request: MealPlanRequest):
    sys = "Nutritionist. JSON Only."
    user = f"Create 1-day meal plan. Goal: {request.user_goal}, {request.daily_calories} cal. JSON Structure: {{ 'analysis': 'str', 'meals': [ {{ 'type': 'Breakfast', 'name': 'str', 'calories': int, 'nutrients': {{ 'protein': 'str' }}, 'recipe': ['step1'] }} ] }}"
    res = generate_text_with_failover(user, sys)
    if res:
        data = clean_and_parse_json(res)
        if data: return data
    return {"analysis": "Offline Plan", "meals": []}

@app.post("/generate-workout")
def generate_workout(request: WorkoutRequest):
    sys = "Trainer. JSON Only."
    user = f"Workout: {request.context}. JSON Structure: {{ 'advice': 'str', 'exercises': [ {{ 'name': 'str', 'sets': 'str', 'reps': 'str' }} ] }}"
    res = generate_text_with_failover(user, sys)
    if res:
        data = clean_and_parse_json(res)
        if data: return data
    return {"advice": "Offline Routine", "exercises": []}

@app.post("/log-meal")
def log_meal_text(meal_log: MealLogRequest):
    sys = "JSON Only."
    user = f"Analyze: {meal_log.meal_description}. JSON Structure: {{ 'estimated_calories': int, 'macros': {{ 'protein': 'str', 'carbs': 'str', 'fat': 'str' }}, 'ingredients': ['str'] }}"
    res = generate_text_with_failover(user, sys)
    if res:
        data = clean_and_parse_json(res)
        if data: return data
    return {"estimated_calories": 0}

@app.post("/compare-prices")
def compare_prices(request: PriceRequest):
    base = 100
    blinkit = base + random.randint(-15, 10)
    zepto = base + random.randint(-15, 10)
    return {
        "item": request.item_name,
        "results": [
            { "store": "Blinkit", "price": blinkit, "currency": "₹", "link": f"[https://blinkit.com/s/?q=](https://blinkit.com/s/?q=){request.item_name}", "is_cheapest": blinkit < zepto },
            { "store": "Zepto", "price": zepto, "currency": "₹", "link": f"[https://www.google.com/search?q=](https://www.google.com/search?q=){request.item_name}+zepto", "is_cheapest": zepto < blinkit }
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)