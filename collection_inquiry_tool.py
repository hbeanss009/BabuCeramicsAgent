from __future__ import annotations

import html
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import Client, create_client

from client_config import MODEL, client as anthropic_client
from context_builder import fetch_artist_notes, fetch_collection_stories, fetch_faqs, fetch_items
from handler_result import HandlerOutcome, answered_outcome, needs_human_outcome, outcome_from_complete_message
from utils.catalog_sources import format_catalog_sources
from utils.helicone import helicone_headers
from utils.human_review import should_flag_for_human_review
from utils.llm_json import parse_complete_message_json
from utils.style_sample import CONTACT_INFO_RULE, NO_EM_DASH_RULE, load_olivia_style_sample
from utils.tool_prompts import (
    CATALOG_SOURCE_GROUNDING_PROMPT,
    HUMAN_REVIEW_FLAG_PROMPT,
    HUMAN_REVIEW_INTENT_GATE_PROMPT,
)

_ENV_PATH = Path(__file__).resolve().parent / ".env"

load_dotenv(_ENV_PATH)

logger = logging.getLogger(__name__)

_COLLECTION_NAME_KEYS = ("collection_name", "name", "collection", "title")
_STORY_TEXT_KEYS = (
    "story",
    "description",
    "collection_description",
    "mood",
    "aesthetic",
    "notes",
)
_IMAGE_KEYS = ("photo_url", "image_url", "picture_url", "photo", "image")
_VALID_QUERY_TYPES = frozenset({
    "collection_story",
    "list_collections",
    "items_in_collection",
    "items_by_category",
    "items_in_collection_by_category",
    "full_catalog",
})
_BROWSE_PHOTO_QUERY_TYPES = frozenset({
    "items_by_category",
    "items_in_collection",
    "items_in_collection_by_category",
})

CollectionInquiryResult = HandlerOutcome


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


def _row_collection_name(row: Dict[str, Any]) -> str:
    for key in _COLLECTION_NAME_KEYS:
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _item_collection_name(row: Dict[str, Any]) -> str:
    val = row.get("collection_name")
    if val is not None and str(val).strip():
        return str(val).strip()
    return ""


def _load_catalog_rows() -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    items = [row for row in (fetch_items() or []) if isinstance(row, dict)]
    stories = [row for row in (fetch_collection_stories() or []) if isinstance(row, dict)]
    return items, stories


def _known_collection_names(
    stories: List[Dict[str, Any]],
    items: List[Dict[str, Any]],
) -> List[str]:
    names: List[str] = []
    seen: set[str] = set()
    for row in stories:
        label = _row_collection_name(row)
        if not label:
            continue
        key = label.lower()
        if key not in seen:
            seen.add(key)
            names.append(label)
    for row in items:
        label = _item_collection_name(row)
        if not label:
            continue
        key = label.lower()
        if key not in seen:
            seen.add(key)
            names.append(label)
    return names


def _known_categories(items: List[Dict[str, Any]]) -> List[str]:
    categories: List[str] = []
    seen: set[str] = set()
    for row in items:
        label = str(row.get("category", "")).strip()
        if not label:
            continue
        key = label.lower()
        if key not in seen:
            seen.add(key)
            categories.append(label)
    return categories


def _items_summary(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "name": row.get("name"),
            "price": row.get("price"),
            "category": row.get("category"),
            "collection": _item_collection_name(row),
            "description": row.get("description"),
        }
        for row in items
    ]


def _match_collection(name: str, known: List[str]) -> str:
    key = name.strip().lower()
    if not key:
        return ""
    for label in known:
        if label.lower() == key:
            return label
    for label in known:
        lower = label.lower()
        if key in lower or lower in key:
            return label
    return name.strip()


def _match_category(name: str, known: List[str]) -> str:
    key = name.strip().lower().rstrip("s")
    if not key:
        return ""
    for label in known:
        lower = label.lower()
        if lower == key or lower.rstrip("s") == key or key in lower:
            return label
    return name.strip()


def _extract_category_from_query(
    user_query: str,
    known_categories: List[str],
) -> str:
    """Match a known catalog category mentioned in the customer's words."""
    text = user_query.lower()
    best_label = ""
    best_len = 0
    for label in known_categories:
        stem = label.lower().rstrip("s")
        if not stem:
            continue
        if re.search(rf"\b{re.escape(stem)}s?\b", text):
            if len(stem) > best_len:
                best_label = label
                best_len = len(stem)
    return best_label


def _refine_browse_classification(
    user_query: str,
    query_type: str,
    collection_name: str,
    category: str,
    known_categories: List[str],
) -> tuple[str, str, str]:
    """Correct common LLM mislabels (e.g. full_catalog for a category browse)."""
    inferred = _extract_category_from_query(user_query, known_categories)
    if inferred and (
        query_type == "full_catalog"
        or (query_type == "items_by_category" and not category)
    ):
        return (
            "items_by_category",
            collection_name,
            _match_category(inferred, known_categories),
        )
    return query_type, collection_name, category


def _filter_items(
    items: List[Dict[str, Any]],
    query_type: str,
    collection_name: str,
    category: str,
) -> List[Dict[str, Any]]:
    if query_type in ("full_catalog", "list_collections"):
        return items

    filtered = items
    if query_type in ("items_in_collection", "items_in_collection_by_category") and collection_name:
        collection_key = collection_name.strip().lower()
        filtered = [
            row for row in filtered
            if _item_collection_name(row).lower() == collection_key
        ]
    if query_type in ("items_by_category", "items_in_collection_by_category") and category:
        category_key = category.strip().lower().rstrip("s")
        filtered = [
            row for row in filtered
            if category_key in str(row.get("category", "")).strip().lower()
            or str(row.get("category", "")).strip().lower().rstrip("s") == category_key
        ]
    return filtered


def _assess_collection_query_intent(user_query: str) -> Optional[HandlerOutcome]:
    if should_flag_for_human_review(user_query):
        return needs_human_outcome()

    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=50,
        temperature=0.0,
        system=(
            f"{HUMAN_REVIEW_INTENT_GATE_PROMPT}\n\n"
            "You judge whether a customer message has a clear collection-related intent "
            "for a ceramics shop.\n"
            "Clear intent: browsing collections or item types, listing items in a "
            "collection, asking what the shop carries, or asking about a collection's "
            "story, mood, inspiration, or aesthetic.\n"
            "Unclear intent: off-topic, angry complaint, asking about one specific "
            "named product only, or you cannot tell what they want.\n\n"
            f"- {NO_EM_DASH_RULE}\n\n"
            'Return ONLY valid JSON: {"intent_clear": true} or {"intent_clear": false}.\n'
            "No markdown or code fences."
        ),
        messages=[{"role": "user", "content": user_query}],
        extra_headers=helicone_headers(
            handler="collection_inquiry_intent_gate", intent="collection_inquiry"
        ),
    )
    raw = _extract_text(response)
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        return needs_human_outcome()
    if not isinstance(data, dict) or not data.get("intent_clear", True):
        return needs_human_outcome()
    return None


def _classify_collection_request(
    user_query: str,
    known_collections: List[str],
    known_categories: List[str],
    messages: Optional[list] = None,
) -> Dict[str, Any]:
    extractor_messages = list(messages) if messages else []
    if not extractor_messages or extractor_messages[-1].get("content") != user_query:
        extractor_messages.append({"role": "user", "content": user_query})

    collections_hint = ", ".join(known_collections) if known_collections else "(none listed)"
    categories_hint = ", ".join(known_categories) if known_categories else "(none listed)"

    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=200,
        temperature=0.0,
        system=(
            "Classify what the customer wants regarding ceramics collections.\n"
            f"Known collections: {collections_hint}\n"
            f"Known item categories: {categories_hint}\n\n"
            "Return ONLY valid JSON with these keys:\n"
            '  "query_type": one of '
            '"collection_story", "list_collections", "items_in_collection", '
            '"items_by_category", "items_in_collection_by_category", "full_catalog"\n'
            '  "collection_name": string or null\n'
            '  "category": string or null (e.g. bowl, mug, vase, plate, platter)\n\n'
            "Guidance:\n"
            '- story/mood/inspiration/aesthetic of a named collection → collection_story\n'
            '- "tell me about the Spring collection" (story) → collection_story\n'
            '- "what collections do you have" → list_collections\n'
            '- "what\'s in Spring collection" (list items) → items_in_collection\n'
            '- "show me all bowls" / "do you have mugs" / "do you have any platters" → items_by_category + category\n'
            '- "bowls in Spring collection" → items_in_collection_by_category + both\n'
            '- "show me everything" / "show me all your pieces" → full_catalog\n'
            '- NEVER use full_catalog when the customer asks for a specific item type\n'
            f"- {NO_EM_DASH_RULE}\n"
            "Use conversation history when the latest message is a short follow-up.\n"
            "No markdown or code fences."
        ),
        messages=extractor_messages,
        extra_headers=helicone_headers(
            handler="collection_inquiry_classifier", intent="collection_inquiry"
        ),
    )
    raw = _extract_text(response)
    try:
        data = json.loads(raw.strip())
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {"query_type": "full_catalog", "collection_name": None, "category": None}


def _clarification_for_classification(
    query_type: str,
    collection_name: str,
    category: str,
) -> Optional[CollectionInquiryResult]:
    if query_type == "collection_story" and not collection_name:
        return {
            "status": "needs_clarification",
            "message": "",
            "missing_slot": "collection_name",
            "clarifying_question": (
                "Could you share which collection you're asking about? "
                "For example, the Spring or Fall collection."
            ),
        }
    if query_type == "items_in_collection" and not collection_name:
        return {
            "status": "needs_clarification",
            "message": "",
            "missing_slot": "catalog_collection",
            "clarifying_question": (
                "Which collection would you like to browse, for example, "
                "Spring or Fall?"
            ),
        }
    if query_type == "items_by_category" and not category:
        return {
            "status": "needs_clarification",
            "message": "",
            "missing_slot": "catalog_category",
            "clarifying_question": (
                "What type of piece are you looking for, bowls, mugs, vases, "
                "plates, or something else?"
            ),
        }
    if query_type == "items_in_collection_by_category":
        missing: List[str] = []
        if not collection_name:
            missing.append("which collection (e.g. Spring or Fall)")
        if not category:
            missing.append("what type of piece (e.g. bowls or mugs)")
        if missing:
            return {
                "status": "needs_clarification",
                "message": "",
                "missing_slot": "catalog_filters",
                "clarifying_question": (
                    "Could you share "
                    + " and ".join(missing)
                    + " so I can show you the right pieces?"
                ),
            }
    return None


def _find_collection_story(
    collection_name: str,
    stories: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    key = collection_name.strip().lower()
    for row in stories:
        if _row_collection_name(row).lower() == key:
            return row
    for row in stories:
        row_key = _row_collection_name(row).lower()
        if row_key and (key in row_key or row_key in key):
            return row
    return None


def _items_in_collection(
    collection_name: str,
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    key = collection_name.strip().lower()
    return [
        row for row in items
        if _item_collection_name(row).lower() == key
    ]


def _story_payload_for_llm(story: Dict[str, Any]) -> Dict[str, Any]:
    hidden = set(_IMAGE_KEYS)
    return {k: v for k, v in story.items() if k not in hidden}


def _items_summary_for_llm(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "name": item.get("name"),
            "price": item.get("price"),
            "category": item.get("category"),
            "description": item.get("description"),
        }
        for item in items
    ]


def _photo_markup(item: Dict[str, Any]) -> str:
    raw = item.get("photo_url")
    if not isinstance(raw, str) or not raw.strip():
        return ""
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        return ""
    name = html.escape(str(item.get("name", "Product")))
    price = html.escape(str(item.get("price", "")))
    safe_url = html.escape(url)
    return (
        f'<p><strong>{name}</strong>, {price}<br>'
        f'<img src="{safe_url}" alt="{name}" loading="lazy" '
        f'style="max-width:400px;height:400px;border-radius:8px;" /></p>'
    )


def _collection_image_markup(story: Dict[str, Any], fallback_name: str) -> str:
    raw = ""
    for key in _IMAGE_KEYS:
        val = story.get(key)
        if isinstance(val, str) and val.strip():
            raw = val.strip()
            break
    if not raw.startswith(("http://", "https://")):
        return ""
    label = html.escape(_row_collection_name(story) or fallback_name or "Collection")
    safe_url = html.escape(raw)
    return (
        f'<p><img src="{safe_url}" alt="{label}" loading="lazy" '
        'style="max-width:400px;height:400px;border-radius:8px;" /></p>'
    )


_EMAIL_GREETING = "Hi there,"
_EMAIL_CLOSING = "Warmly,"
_EMAIL_SIGNATURE = "Olivia Babu"


def _wrap_olivia_email(body: str) -> str:
    text = body.strip()
    return f"{_EMAIL_GREETING}\n\n{text}\n\n{_EMAIL_CLOSING}\n{_EMAIL_SIGNATURE}"


def _reply_html(text_email: str, photo_fragment: str) -> str:
    safe = html.escape(text_email)
    block = (
        '<div style="white-space:pre-wrap;font-family:system-ui,sans-serif;'
        'line-height:1.6;max-width:40rem;margin-bottom:1rem;">'
        f"{safe}</div>"
    )
    return block + photo_fragment if photo_fragment else block


def _parse_browse_response(raw: str, *, fallback_message: str) -> HandlerOutcome:
    complete, message = parse_complete_message_json(
        raw, fallback_message=fallback_message
    )
    return outcome_from_complete_message(complete, message, missing_slot="catalog_filters")


def _respond_collection_story(
    user_query: str,
    collection_name: str,
    stories: List[Dict[str, Any]],
    items: List[Dict[str, Any]],
    messages: Optional[list] = None,
) -> CollectionInquiryResult:
    story_row = _find_collection_story(collection_name, stories)
    collection_items = _items_in_collection(collection_name, items)

    if not story_row and not collection_items:
        return {
            "status": "needs_clarification",
            "message": "",
            "missing_slot": "collection_name",
            "clarifying_question": (
                f"I couldn't find a collection named {collection_name}. "
                "Could you double-check the name?"
            ),
        }

    display_name = (
        _row_collection_name(story_row)
        if story_row
        else _item_collection_name(collection_items[0]) or collection_name
    )
    style_sample = load_olivia_style_sample()
    query_context = user_query.strip() or f"Tell me about the {display_name} collection"

    system_prompt = f"""You are Olivia from Babu Ceramics.

You write ONLY the middle section of an email: the body paragraphs that answer the customer.

Rules:
- Do NOT write a greeting (no "Hi there", no "Dear").
- Do NOT write a closing or signature (no "Thank you", no "Olivia").
- One or two short paragraphs maximum. Warm and concise.
- Write in first-person singular as Olivia ("I", "me", "my").
- Never use "we", "us", or "our".
- Describe the collection's mood, story, and aesthetic using the collection story data.
- Mention a few representative pieces from the item list (names and prices) when relevant.
- Do not invent collections, pieces, or prices not present in the data.
- Do not include image links, photo URLs, or raw https:// addresses.

For collection stories:
- Tell the story in Olivia's voice (warm, personal)
- Limit to 3 sentences maximum
- Do NOT invent details about designs or production process

CRITICAL CONSTRAINTS:
- Keep all responses under 150 words
- Do NOT add descriptive details not in the catalog below
- Do NOT invent design features, colors, or inspiration
- Sound warm and personal, but stay factual and concise
- If unsure about a detail, say "I'd have to check on that"

- {CONTACT_INFO_RULE}
- {NO_EM_DASH_RULE}"""

    story_block = (
        json.dumps(_story_payload_for_llm(story_row), ensure_ascii=False)
        if story_row
        else "null"
    )
    items_block = json.dumps(
        _items_summary_for_llm(collection_items), ensure_ascii=False
    )

    claude_messages = messages or [{"role": "user", "content": query_context}]
    last_user_content = (
        f"User query: {query_context}\n\n"
        f"Collection name: {display_name}\n\n"
        f"Collection story: {story_block}\n\n"
        f"Items in this collection: {items_block}\n\n"
        f"Style sample (tone only):\n{style_sample}\n\n"
        "Write ONLY the email body paragraphs, nothing before or after them."
    )

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
        extra_headers=helicone_headers(
            handler="collection_inquiry", intent="collection_inquiry"
        ),
    )

    body_text = _extract_text(response)
    if not body_text and story_row:
        for key in _STORY_TEXT_KEYS:
            val = story_row.get(key)
            if val:
                body_text = str(val).strip()
                break
    if not body_text:
        body_text = (
            f"The {display_name} collection includes "
            f"{len(collection_items)} piece(s) in our catalog."
        )

    full_email = _wrap_olivia_email(body_text)
    photo_html = _collection_image_markup(story_row or {}, display_name)
    return {
        "status": "answered",
        "message": _reply_html(full_email, photo_html),
        "missing_slot": None,
        "clarifying_question": None,
    }


def _respond_browse(
    user_query: str,
    query_type: str,
    collection_name: str,
    category: str,
    items: List[Dict[str, Any]],
    stories: List[Dict[str, Any]],
    known_categories: List[str],
    messages: Optional[list] = None,
) -> CollectionInquiryResult:
    matched_items = _filter_items(items, query_type, collection_name, category)
    if query_type != "list_collections" and not matched_items:
        import recommendation

        logger.info(
            "collection_inquiry: no catalog matches for query_type=%s, "
            "falling back to recommendation",
            query_type,
        )
        return recommendation.recommendation(user_query, messages)

    collections_overview = [
        {
            "name": _row_collection_name(story) or str(story.get("collection", "")),
            "description": story.get("description") or story.get("story"),
        }
        for story in stories
        if _row_collection_name(story) or story.get("collection")
    ]
    if not collections_overview:
        seen: set[str] = set()
        for row in items:
            label = _item_collection_name(row)
            if label and label.lower() not in seen:
                seen.add(label.lower())
                collections_overview.append({"name": label, "description": None})

    style_sample = load_olivia_style_sample()
    query_context = user_query.strip() or "Help me browse the catalog."

    catalog_payload = {
        "query_type": query_type,
        "collection_filter": collection_name or None,
        "category_filter": category or None,
        "collections": collections_overview,
        "items": _items_summary(matched_items),
        "all_categories": known_categories,
    }

    faqs = fetch_faqs()
    artist_notes = fetch_artist_notes()

    system_prompt = f"""
{HUMAN_REVIEW_FLAG_PROMPT}

{CATALOG_SOURCE_GROUNDING_PROMPT}

You are Olivia from Babu Ceramics replying to a collection or catalog inquiry.

Writing rules for message (when complete is false):
- Write ONLY the middle section of an email: body paragraphs.
- Do NOT write a greeting or signature.
- One or two short paragraphs maximum. Warm and concise.
- Write in first-person singular as Olivia ("I", "me", "my").
- Never use "we", "us", or "our".
- List relevant pieces by exact catalog name and price when showing items.
- For collection listings, name each collection briefly.
- Do not include image links or raw https:// addresses.

CRITICAL CONSTRAINTS:
- Keep all responses under 150 words
- Do NOT add descriptive details not in the catalog below
- Do NOT invent design features, colors, or inspiration
- Sound warm and personal, but stay factual and concise
- If unsure about a detail, say "I'd have to check on that"

- {CONTACT_INFO_RULE}
- {NO_EM_DASH_RULE}

Style sample (tone only):
{style_sample}

{format_catalog_sources(catalog_payload, faqs, artist_notes)}

Output rules:
- Return ONLY valid JSON with exactly these keys: complete (boolean), message (string).
- No markdown, no code fences, no extra keys.
""".strip()

    claude_messages = messages or [{"role": "user", "content": query_context}]
    last_user_content = (
        f"User query: {query_context}\n\n"
        "Write the customer reply in message, or set complete to true with an empty "
        "message if the query cannot be answered from the sources above."
    )

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
        max_tokens=600,
        temperature=0.15,
        system=system_prompt,
        messages=claude_messages,
        extra_headers=helicone_headers(
            handler="collection_inquiry", intent="collection_inquiry"
        ),
    )

    fallback = (
        f"I currently have these collections: {', '.join(c['name'] for c in collections_overview if c.get('name'))}."
        if query_type == "list_collections"
        else "Here are the pieces that match your browse request."
    )
    outcome = _parse_browse_response(_extract_text(response), fallback_message=fallback)

    if outcome.get("status") == "needs_human":
        return outcome

    body_text = str(outcome.get("message") or outcome.get("clarifying_question") or "").strip()
    if not body_text:
        if query_type == "list_collections":
            names = ", ".join(c["name"] for c in collections_overview if c.get("name"))
            body_text = f"I currently have these collections: {names}."
        else:
            lines = [
                f"- {row.get('name')} ({row.get('price')})"
                for row in matched_items[:12]
            ]
            body_text = "Here are the pieces that match:\n" + "\n".join(lines)

    if outcome.get("status") == "needs_clarification":
        return outcome

    if query_type in _BROWSE_PHOTO_QUERY_TYPES:
        photo_html = "".join(
            _photo_markup(item)
            for item in matched_items[:4]
            if item.get("photo_url")
        )
    else:
        photo_html = ""
    full_email = _wrap_olivia_email(body_text)

    return {
        "status": "answered",
        "message": _reply_html(full_email, photo_html),
        "missing_slot": None,
        "clarifying_question": None,
    }


def collection_inquiry(
    user_query: str,
    messages: Optional[list] = None,
) -> CollectionInquiryResult:
    if not _get_supabase_client():
        return answered_outcome(
            "I can't access collection details right now because "
            "SUPABASE_URL or SUPABASE_KEY is missing."
        )

    unclear = _assess_collection_query_intent(user_query)
    if unclear:
        return unclear

    items, stories = _load_catalog_rows()
    if not items:
        return {
            "status": "needs_human",
            "message": "",
            "missing_slot": None,
            "clarifying_question": None,
        }

    known_collections = _known_collection_names(stories, items)
    known_categories = _known_categories(items)
    classification = _classify_collection_request(
        user_query, known_collections, known_categories, messages
    )

    query_type = str(classification.get("query_type") or "full_catalog").strip()
    if query_type not in _VALID_QUERY_TYPES:
        query_type = "full_catalog"

    raw_collection = str(classification.get("collection_name") or "").strip()
    raw_category = str(classification.get("category") or "").strip()
    collection_name = _match_collection(raw_collection, known_collections) if raw_collection else ""
    category = _match_category(raw_category, known_categories) if raw_category else ""

    query_type, collection_name, category = _refine_browse_classification(
        user_query, query_type, collection_name, category, known_categories
    )

    clarification = _clarification_for_classification(
        query_type, collection_name, category
    )
    if clarification:
        return clarification

    if query_type == "collection_story":
        return _respond_collection_story(
            user_query, collection_name, stories, items, messages
        )

    return _respond_browse(
        user_query,
        query_type,
        collection_name,
        category,
        items,
        stories,
        known_categories,
        messages,
    )
