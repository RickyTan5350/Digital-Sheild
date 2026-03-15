import joblib
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
from google.cloud import aiplatform
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
PROJECT_ID = "sheildguard"
REGION = "asia-southeast1"
ENDPOINT_ID = "1145147957398470656"
# Newly uploaded model: 2231969021966680064

# Initialize Vertex AI (Legacy/Tabular)
try:
    aiplatform.init(project=PROJECT_ID, location=REGION)
    endpoint = aiplatform.Endpoint(ENDPOINT_ID)
    print(f"Vertex AI (Tabular) initialized: {ENDPOINT_ID}")
except Exception as e:
    print(f"Failed to initialize Vertex AI Endpoint: {e}")
    endpoint = None

# Initialize Gemini using the provided API Key
try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
    genai.configure(api_key=GEMINI_API_KEY)
    gen_model = genai.GenerativeModel("gemini-2.5-flash-lite") 
    print("Gemini AI initialized using API Key.")
except Exception as e:
    print(f"Failed to initialize Gemini: {e}")
    gen_model = None

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# Load local model as fallback
try:
    model = joblib.load("fraud_model.pkl")
except Exception as e:
    print(f"Failed to load local model: {e}")
    model = None

class PredictionRequest(BaseModel):
    features: list[float]

@app.post("/predict")
def predict(request: PredictionRequest):
    fraud_score = 0.0
    source = "local"

    # 1. Try Vertex AI Tabular Endpoint
    if endpoint:
        try:
            instances = [request.features]
            response = endpoint.predict(instances=instances)
            # Extract score from response
            if response.predictions:
                prediction = response.predictions[0]
                # If it's a list (Standard XGBoost/Sklearn container often returns [prob0, prob1] or just [prob1])
                if isinstance(prediction, list):
                    fraud_score = prediction[1] if len(prediction) > 1 else prediction[0]
                # If it's a dictionary (AutoML Tabular format)
                elif isinstance(prediction, dict) and "scores" in prediction:
                    fraud_score = prediction["scores"][1]
                # If it's a single float
                else:
                    fraud_score = float(prediction)
                source = "vertex"
            else:
                source = "local"
        except Exception as e:
            print(f"Vertex AI Tabular prediction failed: {e}")

    # 2. Fallback to local model
    if source == "local" and model:
        try:
            sample = np.array(request.features).reshape(1,-1)
            fraud_score = model.predict_proba(sample)[0][1]
        except Exception as e:
            print(f"Local model prediction failed: {e}")

    # 3. Decision
    status = "Rejected" if fraud_score >= 0.05 else "Approved"

    return {
        "fraud_score": float(fraud_score),
        "transaction_status": status,
        "prediction_source": source
    }

@app.post("/shield")
def shield(request: PredictionRequest):
    """Unified endpoint to execute both Prediction and AI Analysis"""
    # 1. Get Prediction
    prediction_data = predict(request)
    fraud_score = prediction_data["fraud_score"]
    
    # 2. Get Analysis (passing the fraud score for more context)
    analysis_data = analyze_with_score(request, fraud_score)
    
    return {
        **prediction_data,
        "explanation": analysis_data["explanation"]
    }

def analyze_with_score(request, fraud_score):
    """Internal helper for Gemini analysis with fraud score context"""
    if not gen_model:
        return {"explanation": "AI Guidance is currently offline."}
    
    labels = [
        "Amount", "Hour", "Foreign Transaction", "Location Mismatch", 
        "Device Trust Score", "Velocity (24h)", "Account Age",
        "Category: Clothing", "Category: Electronics", "Category: Food", 
        "Category: Grocery", "Category: Travel"
    ]
    
    tx_summary = "\n".join([f"- {l}: {v}" for l, v in zip(labels, request.features)])
    risk_level = "High" if fraud_score > 0.5 else "Medium" if fraud_score > 0.1 else "Low"
    
    prompt = f"""
    You are 'Digital Shield AI', a security specialist.
    Analyze this transaction and provide a concise explanation + security tip.
    
    DATA:
    {tx_summary}
    
    AI RISK ASSESSMENT: {risk_level} (Score: {fraud_score:.4f})
    
    INSTRUCTIONS:
    1. Explain based on data AND the risk score.
    2. Provide a 'Security Tip'.
    3. Keep it under 60 words.
    
    Format:
    Analysis: [Why it's {risk_level.lower()} risk]
    Guidance: [Action for user]
    """
    
    try:
        response = gen_model.generate_content(prompt)
        return {"explanation": response.text.strip()}
    except Exception as e:
        print(f"Gemini error: {e}")
        return {"explanation": "Unable to generate analysis."}

@app.post("/analyze")
def analyze_endpoint(request: PredictionRequest):
    """Old endpoint for direct analysis (kept for backwards compatibility)"""
    return analyze_with_score(request, 0.5) # Default score if not provided