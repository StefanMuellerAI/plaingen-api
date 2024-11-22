import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.security.api_key import APIKeyHeader, APIKey
from fastapi.middleware.cors import CORSMiddleware
from starlette.status import HTTP_403_FORBIDDEN
from pydantic import BaseModel, Field
import yaml
from typing import List, Literal
from pathlib import Path
import logging
from crew import LatestAiDevelopmentCrew
from models import TextTransformRequest, TextTransformResponse
import re
from openai import OpenAI, OpenAIError
from datetime import datetime
from slowapi import Limiter
from slowapi.util import get_remote_address
import json
import asyncio
from async_timeout import timeout
from fastapi.responses import JSONResponse
import functools
from concurrent.futures import ThreadPoolExecutor
from config.supabase import get_hooks_by_language, get_avoid_words_by_language, get_ctas_by_language
import sys

# Lade Umgebungsvariablen
load_dotenv()

# Logging Setup am Anfang der Datei
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('api.log')
    ]
)
logger = logging.getLogger(__name__)

# Stelle sicher, dass alle Handler das richtige Level haben
for handler in logger.handlers:
    handler.setLevel(logging.INFO)

# Debug-Nachricht zum Testen des Loggings
logger.info("API Server started")

# API Setup mit Limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="AI Research API", version="1.0.0")
app.state.limiter = limiter

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://plaingen-nxmo9x6qp-stefan-ai.vercel.app",
        "https://easiergen.de",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600,
)

# OpenAI Client
openai_api_key = os.getenv('OPENAI_API_KEY')
if not openai_api_key:
    logger.error("OPENAI_API_KEY ist nicht gesetzt")
    raise ValueError("OPENAI_API_KEY ist nicht gesetzt")
client = OpenAI(api_key=openai_api_key)

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

class LinkedInPost(BaseModel):
    titel: str
    text: str

class LinkedInResearchOutput(BaseModel):
    posts: List[LinkedInPost]

class TextTransformRequest(BaseModel):
    text: str = Field(
        ..., 
        min_length=1, 
        description="Der zu transformierende Text"
    )
    transformation: Literal["extend", "shorten", "rephrase"] = Field(
        ..., 
        description="Art der gewünschten Transformation"
    )

class TextTransformResponse(BaseModel):
    transformed_text: str = Field(..., description="Der transformierte Text")

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
    address: str = Field(
        ..., 
        min_length=8, 
        max_length=10,
        description="Du oder Sie Ansprache"
    )
    mood: str = Field(
        ..., 
        min_length=6, 
        max_length=15,
        description="Stimmung des Posts"
    )
    perspective: str = Field(
        ..., 
        min_length=2, 
        max_length=2,
        description="Perspektive des Schreibers"
    )

# Lade avoid_words und prompts beim Start und cache sie
avoid_words = []
ctas = []
hooks = []
prompts = {}
crew_instance = None

@app.on_event("startup")
async def startup_event():
    global avoid_words, hooks, ctas, prompts, crew_instance
    
    try:            
        prompts_file = Path("config/prompts.md")
        if prompts_file.exists():
            content = prompts_file.read_text()
            transformations = ["extend", "shorten", "rephrase"]
            for transformation in transformations:
                pattern = rf"## {transformation}\n(.*?)\n\n|## {transformation}\n(.*?)$"
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    prompt_template = next(group for group in match.groups() if group is not None).strip()
                    prompts[transformation] = prompt_template
                    logger.info(f"Prompt für '{transformation}' erfolgreich geladen")
                else:
                    logger.warning(f"Prompt für '{transformation}' nicht gefunden")
        else:
            logger.warning("prompts.md nicht gefunden")
        
        # Initialize CrewAI once
        crew_instance = LatestAiDevelopmentCrew()
        crew_instance.verbose = False
        logger.info("CrewAI erfolgreich initialisiert")

    except Exception as e:
        logger.error(f"Fehler beim Laden der Konfiguration: {str(e)}")

# Asynchrone Ausführunng der CrewAI-Aufgabe
async def execute_crew_task(crew, inputs):
    return await asyncio.to_thread(
        lambda: crew.crew().kickoff(inputs=inputs)
    )

# Timeout für externe Anfragen
DEFAULT_TIMEOUT = 300  # 5 Minuten

# Globaler ThreadPool für CPU-intensive Operationen
thread_pool = ThreadPoolExecutor(max_workers=4)

# Semaphore für gleichzeitige Anfragen
MAX_CONCURRENT_REQUESTS = 10
request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

@app.post("/task/{task_name}")
@limiter.limit("100/minute")
async def execute_task(
    request: Request,
    task_name: str, 
    request_data: TopicRequest,  
    api_key: APIKey = Depends(get_api_key)
):
    logger.info(f"Incoming request - Task: {task_name}, Language: {request_data.language}")
    
    try:
        async with timeout(DEFAULT_TIMEOUT):
            tasks_file = Path("config/tasks.yaml")
            if not tasks_file.exists():
                logger.error("tasks.yaml nicht gefunden")
                raise HTTPException(status_code=500, detail="tasks.yaml nicht gefunden")
            
            # Lade sprachabhängige Daten aus Supabase
            try:
                hooks = await get_hooks_by_language(request_data.language)
                avoid_words = await get_avoid_words_by_language(request_data.language)
                ctas = await get_ctas_by_language(request_data.language)
                
                logger.info("\n=== Geladene Hooks ===")
                for idx, hook in enumerate(hooks, 1):
                    logger.info(f"{idx}. {hook}")
                logger.info("===================\n")
                
                logger.info("\n=== Geladene Avoid Words ===")
                for idx, word in enumerate(avoid_words, 1):
                    logger.info(f"{idx}. {word}")
                logger.info("===================\n")
                
                logger.info("\n=== Geladene CTAs ===")
                for idx, cta in enumerate(ctas, 1):
                    logger.info(f"{idx}. {cta}")
                logger.info("===================\n")
                
                if not hooks:
                    logger.warning(f"Keine Hooks für Sprache {request_data.language} gefunden")
                    hooks = []
                
                if not avoid_words:
                    logger.warning(f"Keine Avoid Words für Sprache {request_data.language} gefunden")
                    avoid_words = []
                    
                if not ctas:
                    logger.warning(f"Keine CTAs für Sprache {request_data.language} gefunden")
                    ctas = []
                    
            except Exception as e:
                logger.error(f"Fehler beim Laden der Supabase-Daten: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Fehler beim Laden der Sprachdaten: {str(e)}"
                )

            result = await execute_crew_task(
                crew_instance,
                {
                    "topic": request_data.topic, 
                    "language": request_data.language,
                    "avoid_words": avoid_words,
                    "hooks": hooks,
                    "ctas": ctas,  # Neue CTAs werden übergeben
                    "address": request_data.address,
                    "mood": request_data.mood,
                    "perspective": request_data.perspective
                }
            )
            
            # Neue Verarbeitung der Antwort
            if isinstance(result, str):
                try:
                    result_dict = json.loads(result)
                    if "posts" in result_dict:
                        return result_dict
                except json.JSONDecodeError:
                    pass
                    
            if hasattr(result, 'json_dict') and result.json_dict and 'posts' in result.json_dict:
                return {"posts": result.json_dict["posts"]}
            
            logger.error("Keine Posts im Output gefunden")
            raise HTTPException(
                status_code=500, 
                detail="Keine Posts im Output gefunden"
            )
    
    except asyncio.TimeoutError:
        logger.error("Request Timeout")
        raise HTTPException(
            status_code=504,
            detail="Request Timeout - Die Anfrage dauerte zu lange"
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
            "openai": "healthy" if openai_api_key else "not configured"
        }
    }

@app.post("/transform-text", response_model=TextTransformResponse)
@limiter.limit("100/minute")
async def transform_text(
    request: Request,
    text_request: TextTransformRequest,
    api_key: APIKey = Depends(get_api_key)
):
    """Transformiert einen Text basierend auf der gewünschten Operation"""
    try:
        prompt_template = prompts.get(text_request.transformation)
        if not prompt_template:
            logger.warning(f"Ungültige Transformation: {text_request.transformation}")
            raise HTTPException(status_code=400, detail="Ungültige Transformation")

        prompt = prompt_template.format(text=text_request.text)

        # Asynchroner OpenAI-Aufruf
        completion = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Du bist ein Experte für Textoptimierung."},
                    {"role": "user", "content": prompt}
                ]
            )
        )
        
        transformed_text = completion.choices[0].message.content.strip()
        logger.info("Text erfolgreich transformiert")
        return TextTransformResponse(transformed_text=transformed_text)
        
    except OpenAIError as e:
        logger.error(f"OpenAI Fehler: {str(e)}")
        raise HTTPException(status_code=500, detail="Fehler bei der Texttransformation")
    except Exception as e:
        logger.error(f"Fehler bei der Texttransformation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Am Anfang der Datei
# Initialisiere wichtige Komponenten beim Start
@functools.lru_cache(maxsize=1)
def initialize_crew():
    return LatestAiDevelopmentCrew()

# Initialisiere beim Startup
crew = initialize_crew()

# Endpoint anpassen
@app.post("/research", response_model=LinkedInResearchOutput)
@limiter.limit("10/minute")
async def research_topic(request: Request, topic_request: TopicRequest, background_tasks: BackgroundTasks):
    async with request_semaphore:  # Kontrolliere gleichzeitige Anfragen
        try:
            async with timeout(DEFAULT_TIMEOUT):
                try:
                    # Verwende den ThreadPool für CPU-intensive Operationen
                    loop = asyncio.get_event_loop()
                    crew = LatestAiDevelopmentCrew()
                    result = await loop.run_in_executor(
                        thread_pool,
                        lambda: asyncio.run(crew.crew.run())
                    )
                    
                    # Cleanup im Hintergrund
                    background_tasks.add_task(cleanup_resources)
                    
                    return result
                except Exception as e:
                    logger.error(f"Error in research_topic: {str(e)}", exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail=f"Internal server error: {str(e)}"
                    )
        except asyncio.TimeoutError:
            logger.error("Request timed out after %s seconds", DEFAULT_TIMEOUT)
            raise HTTPException(
                status_code=504,
                detail="Request timed out"
            )
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred"
            )

async def cleanup_resources():
    """Cleanup-Funktion für Ressourcen nach der Anfrage"""
    try:
        # Hier können wir Cleanup-Operationen durchführen
        await asyncio.sleep(0)  # Yield control
    except Exception as e:
        logger.error(f"Error in cleanup: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)