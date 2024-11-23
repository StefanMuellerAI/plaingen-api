from supabase.client import create_client, Client
from dotenv import load_dotenv
import os
import logging
from pprint import pformat

# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Stelle sicher, dass der Handler das richtige Level hat
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL und SUPABASE_KEY müssen in .env gesetzt sein")

supabase: Client = create_client(supabase_url, supabase_key)

async def get_hooks_by_language(language: str):
    try:
        response = supabase.table('hooks').select('hook').eq('language', language).eq('rights', 'admin').execute()
        hooks = [item['hook'] for item in response.data]
        logger.debug(f"Retrieved {len(hooks)} hooks for language {language}")
        return hooks
    except Exception as e:
        logger.error(f"Error fetching hooks: {str(e)}")
        raise

async def get_avoid_words_by_language(language: str):
    try:
        response = supabase.table('avoid_words').select('word').eq('language', language).eq('rights', 'admin').execute()
        avoid_words = [item['word'] for item in response.data]
        logger.debug(f"Retrieved {len(avoid_words)} avoid words for language {language}")
        return avoid_words
    except Exception as e:
        logger.error(f"Error fetching avoid words: {str(e)}")
        raise

async def get_ctas_by_language(language: str):
    try:
        response = supabase.table('ctas').select('cta').eq('language', language).eq('rights', 'admin').execute()
        ctas = [item['cta'] for item in response.data]
        logger.debug(f"Retrieved {len(ctas)} CTAs for language {language}")
        return ctas
    except Exception as e:
        logger.error(f"Error fetching CTAs: {str(e)}")
        raise