import os
import anthropic
from anthropic import Anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is not set.")

HELICONE_API_KEY = os.getenv("HELICONE_API_KEY")
if not HELICONE_API_KEY:
    raise RuntimeError("HELICONE_API_KEY is not set.")

MODEL = "claude-haiku-4-5-20251001"

client = Anthropic(
    api_key=ANTHROPIC_API_KEY,
    base_url="https://anthropic.helicone.ai",
    default_headers={
        "Helicone-Auth": f"Bearer {HELICONE_API_KEY}"
    }
)
