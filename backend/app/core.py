import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is required")

GEMINI_MODEL_VERSION = os.getenv("GEMINI_MODEL_VERSION", "gemini-3.1-flash-lite-preview")
GEMINI_LIVE_MODEL_VERSION = os.getenv("GEMINI_LIVE_MODEL_VERSION", "gemini-3.1-flash-live-preview")
