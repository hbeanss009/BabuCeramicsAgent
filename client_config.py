import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError(
        "ANTHROPIC_API_KEY is not set. Add it to .env or export it in your shell."
    )

MODEL = "claude-haiku-4-5-20251001"

client = Anthropic(api_key=ANTHROPIC_API_KEY)
