import html
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv
from postgrest.exceptions import APIError
from supabase import Client, create_client

from client_config import MODEL, client as anthropic_client
from context_builder import fetch_care_guides, fetch_collection_stories
from handler_result import HandlerOutcome, answered_outcome, needs_human_outcome
from utils.helicone import helicone_headers
from utils.human_review import is_discount_question, should_flag_for_human_review
from utils.style_sample import CONTACT_INFO_RULE, NO_EM_DASH_RULE, load_olivia_style_sample
from utils.tool_prompts import HUMAN_REVIEW_INTENT_GATE_PROMPT

_ENV_PATH = Path(__file__).resolve().parent / ".env"

load_dotenv(_ENV_PATH)

logger = logging.getLogger(__name__)


def _normalize_supabase_url(url: str) -> str:
    normalized = url.strip().rstrip("/")
    if normalized.endswith("/rest/v1"):
        normalized = normalized[: -len("/rest/v1")]
    return normalized


def _get_supabase_client() -> Optional[Client]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None
    return create_client(_normalize_supabase_url(url), key)


def _extract_text(response: Any) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    return ""


def _resolve_item_name(
    user_query: Optional[str],
    messages: Optional[list] = None,
) -> str:
    if not user_query or not user_query.strip():
        return ""

    extractor_messages = list(messages) if messages else []
    if not extractor_messages or extractor_messages[-1].get("content") != user_query:
        extractor_messages.append({"role": "user", "content": user_query})

    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=120,
        temperature=0,
        system=(
            "Extract the catalog item / product name from the customer's messages.\n"
            "Rules:\n"
            "- Return ONLY the product title as a customer would say it (plain text, no quotes).\n"
            "- Include the full multi-word name (e.g. \"Rain Song Vase\", not \"Rain\" or \"Vase\" alone).\n"
            "- If several items appear, return the one the user is primarily asking about.\n"
            "- Use the full conversation if the latest message only gives the name as a follow-up.\n"
            "- Ignore the shop's own prompts (e.g. \"share the item name\") — they are not product names.\n"
            "- If no specific item is mentioned anywhere, return exactly: MISSING"
        ),
        messages=extractor_messages,
    )
    extracted = _extract_text(response)
    if extracted.upper() == "MISSING" or not extracted:
        return ""
    return extracted.strip()


def _assess_item_query_intent(user_query: str) -> Optional[HandlerOutcome]:
    """If intent is unclear, flag for human review with no customer message."""
    if should_flag_for_human_review(user_query) or is_discount_question(user_query):
        return needs_human_outcome()

    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=50,
        temperature=0.0,
        system=(
            f"{HUMAN_REVIEW_INTENT_GATE_PROMPT}\n\n"
            "You judge whether a customer message has a clear item-related intent "
            "for a ceramics shop.\n"
            "Clear intent: asking about a specific product, price, size, materials, "
            "care, stock, collection, the story or inspiration behind a piece, "
            "how it was made, what inspired it, or the artist's process.\n"
            "Unclear intent: too vague, off-topic, multiple unrelated asks, "
            "discount or price negotiation requests (e.g. lower the price, bulk discount), "
            "or you cannot tell what they want.\n\n"
            'Return ONLY valid JSON: {"intent_clear": true} or '
            '{"intent_clear": false}.\n'
            "No markdown or code fences."
        ),
        messages=[{"role": "user", "content": user_query}],
    )
    raw = _extract_text(response)
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        return needs_human_outcome()
    if not isinstance(data, dict) or not data.get("intent_clear", True):
        return needs_human_outcome()
    return None


def _find_item_details(item_name: str) -> Optional[Dict[str, Any]]:
    sb = _get_supabase_client()
    if not sb:
        return None
    table = os.environ.get("SUPABASE_ITEMS_TABLE", "Items")
    key   = item_name.strip().lower()
    try:
        resp = sb.table(table).select("*").execute()
    except APIError:
        return None
    except (httpx.ConnectError, httpx.NetworkError, OSError) as exc:
        raise RuntimeError(
            "Could not connect to Supabase. Open your Supabase project → "
            "Settings → API, copy the Project URL into .env as SUPABASE_URL "
            f"(format: https://YOUR_PROJECT_REF.supabase.co). "
            f"The current host could not be reached ({exc})."
        ) from exc
    for row in resp.data or []:
        if isinstance(row, dict):
            if str(row.get("name", "")).strip().lower() == key:
                return row
    return None


def _item_photo_markup(item: Dict[str, Any], fallback_name: str) -> str:
    raw = item.get("photo_url")
    if not isinstance(raw, str) or not raw.strip():
        return ""
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        return ""
    label    = html.escape(str(item.get("name") or fallback_name or "Product"))
    safe_url = html.escape(url)
    return (
        f'<p><img src="{safe_url}" alt="{label}" loading="lazy" '
        'style="max-width:400px;height:400px;border-radius:8px;" /></p>'
    )


_ITEM_KEYS_HIDDEN_FROM_LLM = frozenset(
    {"photo_url", "image_url", "picture_url", "photo", "image"}
)


def _item_payload_for_llm(item: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in item.items() if k not in _ITEM_KEYS_HIDDEN_FROM_LLM}


_EMAIL_GREETING  = "Hi there,"
_EMAIL_CLOSING   = "Warmly,"
_EMAIL_SIGNATURE = "Olivia Babu"


def _wrap_olivia_email(body: str) -> str:
    text = body.strip()
    return f"{_EMAIL_GREETING}\n\n{text}\n\n{_EMAIL_CLOSING}\n{_EMAIL_SIGNATURE}"


def _reply_html(text_email: str, photo_fragment: str) -> str:
    safe  = html.escape(text_email)
    block = (
        '<div style="white-space:pre-wrap;font-family:system-ui,sans-serif;'
        'line-height:1.6;max-width:40rem;margin-bottom:1rem;">'
        f"{safe}</div>"
    )
    return block + photo_fragment if photo_fragment else block


def item_details_tool(
    user_query: str,
    messages: Optional[list] = None,
) -> HandlerOutcome:

    if not _get_supabase_client():
        return answered_outcome(
            "I can't access item details right now because SUPABASE_URL or SUPABASE_KEY is missing."
        )

    unclear = _assess_item_query_intent(user_query)
    if unclear:
        return unclear

    resolved_item_name = _resolve_item_name(user_query, messages).title()
    if not resolved_item_name:
        return {
            "status": "needs_clarification",
            "message": "",
            "missing_slot": "item_name",
            "clarifying_question": (
                "Could you share the item name so I can pull the right details for you?"
            ),
        }

    try:
        item = _find_item_details(resolved_item_name)
    except RuntimeError as exc:
        return answered_outcome(str(exc))

    if not item:
        return {
            "status": "needs_clarification",
            "message": "",
            "missing_slot": "item_name",
            "clarifying_question": (
                f"I couldn't find an item named {resolved_item_name}. "
                "Could you double-check the name?"
            ),
        }

    # Fetch unstructured context
    care_guides        = fetch_care_guides()
    collection_stories = fetch_collection_stories()
    style_sample       = load_olivia_style_sample()
    query_context      = user_query.strip() or f"Give me all the details of the item {resolved_item_name}"

    system_prompt = f"""You are Olivia from Babu Ceramics.

You write ONLY the middle section of an email: the body paragraphs that answer the customer.

Rules:
- Do NOT write a greeting (no "Hi there", no "Dear").
- Do NOT write a closing or signature (no "Thank you", no "Olivia").
- One or two short paragraphs maximum. Warm and concise.
- Write in first-person singular as Olivia ("I", "me", "my").
- Never use "we", "us", or "our".
- Use the item details, care guides, and collection stories to answer fully.
- If the query is about care or cleaning, use the care guides.
- If the query is about the collection or style, use the collection stories.
- Do not include image links, photo URLs, or raw https:// addresses.

For item queries:
- State the name, price, material, and collection in conversational prose
- One sentence maximum of warm personal context (e.g., why you love it)
- Do NOT add design details, colors, or inspiration stories unless documented

Example:
"The Robin's Call Mug is $42, earthenware, part of the Spring collection.
I'm so glad you asked about this one."

For care questions:
- State the material and care instructions conversationally
- Example: "Earthenware is delicate — hand wash only to keep the glaze beautiful."

CRITICAL CONSTRAINTS:
- Keep all responses under 150 words
- Do NOT add descriptive details not in the catalog below
- Do NOT invent design features, colors, or inspiration
- Sound warm and personal, but stay factual and concise
- If unsure about a detail, say "I'd have to check on that"

- {CONTACT_INFO_RULE}
- {NO_EM_DASH_RULE}"""

    # Build messages — use full history if available, otherwise just current query
    claude_messages = messages or [{"role": "user", "content": query_context}]  # ← ADDED

    # Inject item context into the last user message
    last_user_content = (
        f"User query: {query_context}\n\n"
        f"Item details: {json.dumps(_item_payload_for_llm(item), ensure_ascii=False)}\n\n"
        f"Care guides: {json.dumps(care_guides, ensure_ascii=False)}\n\n"
        f"Collection stories: {json.dumps(collection_stories, ensure_ascii=False)}\n\n"
        f"Style sample (tone only):\n{style_sample}\n\n"
        "Write ONLY the email body paragraphs — nothing before or after them."
    )

    # Replace or append the final user turn with the enriched context
    if claude_messages and claude_messages[-1]["role"] == "user":
        claude_messages = claude_messages[:-1] + [
            {"role": "user", "content": last_user_content}
        ]
    else:
        claude_messages = claude_messages + [
            {"role": "user", "content": last_user_content}
        ]

    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=500,
        temperature=0.15,
        system=system_prompt.strip(),
        messages=claude_messages, 
        extra_headers=helicone_headers(handler="item_details", intent="item_inquiry") # ← CHANGED — full history passed
    )

    body_text = _extract_text(response)
    if not body_text:
        body_text = (
            f"Here are the details for {item.get('name', resolved_item_name)}: "
            f"{item.get('description', 'No description available')}."
        )

    full_email = _wrap_olivia_email(body_text)
    photo_html = _item_photo_markup(item, resolved_item_name)
    return {
        "status": "answered",
        "message": _reply_html(full_email, photo_html),
        "missing_slot": None,
        "clarifying_question": None,
    }


# Alias for the item_inquiry route in main.py
item_inquiry_tool = item_details_tool