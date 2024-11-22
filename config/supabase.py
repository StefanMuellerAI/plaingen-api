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
    print(f"\n{'='*50}")  # Visuelle Trennung für bessere Lesbarkeit
    print(f"SUPABASE QUERY: Fetching hooks for language: {language}")
    try:
        response = supabase.table('hooks').select('hook').eq('language', language).eq('rights', 'admin').execute()
        print(f"HOOKS RESPONSE: {pformat(response.data)}")
        hooks = [item['hook'] for item in response.data]
        print(f"PROCESSED HOOKS: {pformat(hooks)}")
        print(f"{'='*50}\n")
        return hooks
    except Exception as e:
        print(f"ERROR fetching hooks: {str(e)}")
        raise

async def get_avoid_words_by_language(language: str):
    print(f"\n{'='*50}")
    print(f"SUPABASE QUERY: Fetching avoid words for language: {language}")
    try:
        response = supabase.table('avoid_words').select('word').eq('language', language).eq('rights', 'admin').execute()
        print(f"AVOID WORDS RESPONSE: {pformat(response.data)}")
        avoid_words = [item['word'] for item in response.data]
        print(f"PROCESSED AVOID WORDS: {pformat(avoid_words)}")
        print(f"{'='*50}\n")
        return avoid_words
    except Exception as e:
        print(f"ERROR fetching avoid words: {str(e)}")
        raise

async def get_ctas_by_language(language: str):
    print(f"\n{'='*50}")
    print(f"SUPABASE QUERY: Fetching CTAs for language: {language}")
    try:
        response = supabase.table('ctas').select('cta').eq('language', language).eq('rights', 'admin').execute()
        print(f"CTAS RESPONSE: {pformat(response.data)}")
        ctas = [item['cta'] for item in response.data]
        print(f"PROCESSED CTAS: {pformat(ctas)}")
        print(f"{'='*50}\n")
        return ctas
    except Exception as e:
        print(f"ERROR fetching CTAs: {str(e)}")
        raise