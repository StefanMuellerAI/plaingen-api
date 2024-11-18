import os
from dotenv import load_dotenv

# Disable OpenTelemetry before other imports
os.environ["OTEL_PYTHON_DISABLED"] = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"



# Dann erst die restlichen Imports
from fastapi import FastAPI, HTTPException, Security, Depends, Request
from fastapi.security.api_key import APIKeyHeader, APIKey
from fastapi.middleware.cors import CORSMiddleware
from starlette.status import HTTP_403_FORBIDDEN
from pydantic import BaseModel, Field
import yaml
from typing import Dict, Any, Optional, Annotated
from pathlib import Path
import logging
from crew import LatestAiDevelopmentCrew
from dotenv import load_dotenv
from models import TextTransformRequest, TextTransformResponse
import re
from openai import OpenAI
from datetime import datetime
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Lade Umgebungsvariablen
load_dotenv()

# Logging Setup
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API Setup mit Limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="AI Research API", version="1.0.0")
app.state.limiter = limiter

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI Client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# API Key Setup
API_KEY = os.getenv('API_KEY')
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(
    api_key_header: str = Depends(api_key_header)
) -> str:
    if not api_key_header or api_key_header != API_KEY:
        logger.warning("Ungültiger API-Key-Versuch")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, 
            detail="Ungültiger oder fehlender API-Key"
        )
    return api_key_header

class TopicRequest(BaseModel):
    topic: str = Field(
        ..., 
        min_length=1, 
        max_length=500,
        description="Das zu recherchierende Thema"
    )
    language: str = Field(
        ..., 
        min_length=2, 
        max_length=2,
        description="Der Sprachcode (z.B. DE, EN)",
        pattern="^[A-Z]{2}$"
    )

@app.post("/task/{task_name}")
@limiter.limit("100/minute")
async def execute_task(
    request: Request,
    task_name: str, 
    request_data: TopicRequest,  
    api_key: APIKey = Depends(get_api_key)
):
    """Führt einen spezifischen Task aus"""
    try:
        # Task Validierung
        tasks_file = Path("tasks.yaml")
        if tasks_file.exists():
            with open(tasks_file, "r") as f:
                tasks = yaml.safe_load(f)
                if task_name not in tasks:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Task '{task_name}' nicht gefunden"
                    )
        
        # Crew Ausführung
        crew = LatestAiDevelopmentCrew()
        crew.verbose = False
        result = crew.crew().kickoff(inputs={"topic": request_data.topic, "language": request_data.language})
        
        if hasattr(result, 'json_dict') and result.json_dict and 'posts' in result.json_dict:
            return {"posts": result.json_dict["posts"]}
        
        raise HTTPException(
            status_code=500, 
            detail="Keine Posts im Output gefunden"
        )
    
    except Exception as e:
        logger.error(f"Fehler bei der Task-Ausführung: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "api_version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "openai": "healthy" if os.getenv('OPENAI_API_KEY') else "not configured"
        }
    }

def load_prompt(transformation: str, text: str) -> str:
    """Lädt den entsprechenden Prompt aus der MD-Datei und fügt den Text ein"""
    prompts_file = Path("config/prompts.md")
    if not prompts_file.exists():
        raise FileNotFoundError("prompts.md nicht gefunden")
        
    content = prompts_file.read_text()
    pattern = rf"## {transformation}\n(.*?)\n\n|## {transformation}\n(.*?)$"
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        raise ValueError(f"Prompt für '{transformation}' nicht gefunden")
        
    prompt_template = next(group for group in match.groups() if group is not None).strip()
    return prompt_template.replace("{text}", text)



@app.post("/transform-text", response_model=TextTransformResponse)
@limiter.limit("100/minute")
async def transform_text(
    request: Request,
    text_request: TextTransformRequest,
    api_key: APIKey = Depends(get_api_key)
):
    """Transformiert einen Text basierend auf der gewünschten Operation"""
    try:
        prompt = load_prompt(text_request.transformation, text_request.text)

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Du bist ein Experte für Textoptimierung."},
                {"role": "user", "content": prompt}
            ]
        )
        
        transformed_text = completion.choices[0].message.content.strip()
        return TextTransformResponse(transformed_text=transformed_text)
        
    except Exception as e:
        logger.error(f"Fehler bei der Texttransformation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))