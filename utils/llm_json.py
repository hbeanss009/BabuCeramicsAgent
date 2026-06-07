from __future__ import annotations

import json
from typing import Tuple


def strip_code_fence(raw: str) -> str:
    """Remove optional ```json ... ``` (or similar) wrapping from model output."""
    text = raw.strip()
    if not text.startswith("`"):
        return text
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_complete_message_json(
    raw: str,
    *,
    fallback_message: str,
) -> Tuple[bool, str]:
    """
    Parse {"complete": bool, "message": str} from LLM output.
    Returns (complete, message). On failure uses fallback_message, not raw output.
    """
    stripped = strip_code_fence(raw)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return False, fallback_message
    if not isinstance(data, dict):
        return False, fallback_message
    complete = bool(data.get("complete"))
    message = str(data.get("message", "")).strip() or fallback_message
    return complete, message
