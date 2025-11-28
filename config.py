import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден! Проверьте файл .env")

if not OPENAI_API_KEY:
    print("⚠️ OPENAI_API_KEY не найдены! AI функции будут недоступны")