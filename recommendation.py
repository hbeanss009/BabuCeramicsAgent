from __future__ import annotations

import re
import html
import json
from typing import Any, Optional, TypedDict

from client_config import MODEL, client
from context_builder import (
    fetch_items,
    fetch_collection_stories,
    fetch_editorial_picks,
)
from handler_result import (
    HandlerOutcome,
    clarification_outcome,
    needs_human_outcome,
    answered_outcome,
)
from utils.helicone import helicone_headers
from utils.llm_json import strip_code_fence
from utils.human_review import should_flag_for_human_review
from utils.style_sample import CONTACT_INFO_RULE, NO_EM_DASH_RULE, load_olivia_style_sample
from utils.tool_prompts import HUMAN_REVIEW_FLAG_PROMPT


class _ParsedRecommendationResult(TypedDict, total=False):
    complete: bool
    message: str
    recommended_items: list[str]


def _extract_text(response: Any) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    return ""


def _normalize_item_name(name: str) -> str:
    """Lowercase name with punctuation removed for fuzzy catalog matching."""
    return re.sub(r"[^\w\s]", "", name.lower()).strip()


def _resolve_items_by_name(names: list[str], items: list) -> list:
    """Map exact catalog names to item rows; preserves LLM order, dedupes."""
    catalog: dict[str, dict] = {}
    for item in items:
        label = str(item.get("name", "")).strip()
        if label:
            catalog[_normalize_item_name(label)] = item

    resolved: list[dict] = []
    seen_ids: set[str] = set()
    for raw in names:
        key = _normalize_item_name(str(raw).strip())
        if not key:
            continue
        match = catalog.get(key)
        if not match:
            continue
        item_id = str(match.get("item_id") or match.get("name") or "")
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        resolved.append(match)
    return resolved


def _extract_recommended_items_from_message(message: str, items: list) -> list:
    """Fallback: infer recommended items from message text (max 3, longest names first)."""
    clean_message = _normalize_item_name(message.replace("**", ""))
    matched: list[dict] = []
    seen_ids: set[str] = set()

    candidates = sorted(
        (item for item in items if str(item.get("name", "")).strip()),
        key=lambda row: len(str(row["name"])),
        reverse=True,
    )
    for item in candidates:
        if len(matched) >= 3:
            break
        name = str(item.get("name", "")).strip()
        if _normalize_item_name(name) in clean_message:
            item_id = str(item.get("item_id") or name)
            if item_id not in seen_ids:
                seen_ids.add(item_id)
                matched.append(item)
    return matched


def _photo_markup(item: dict) -> str:
    """Return HTML img tag for an item, or empty string if no photo."""
    raw = item.get("photo_url", "")
    if not isinstance(raw, str) or not raw.strip():
        return ""
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        return ""
    name     = html.escape(str(item.get("name", "Product")))
    price    = html.escape(str(item.get("price", "")))
    safe_url = html.escape(url)
    return (
        f'<p><strong>{name}</strong>, {price}<br>'
        f'<img src="{safe_url}" alt="{name}" loading="lazy" '
        f'style="max-width:400px;height:400px;border-radius:8px;" /></p>'
    )


def _is_recommendation_question(message: str) -> bool:
    if not message.strip() or "?" not in message:
        return False
    lower = message.lower()
    if re.search(r"\$\d", message):
        return False
    if any(
        phrase in lower
        for phrase in ("i would suggest", "i'd suggest", "i suggest", "recommend the")
    ):
        return False
    return True


def _parse_tool_response(raw: str) -> _ParsedRecommendationResult:
    stripped = strip_code_fence(raw)

    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            raw_names = data.get("recommended_items")
            recommended_items: list[str] = []
            if isinstance(raw_names, list):
                recommended_items = [
                    str(name).strip()
                    for name in raw_names
                    if str(name).strip()
                ][:3]
            return {
                "complete": bool(data.get("complete")),
                "message": str(data.get("message", "")).strip(),
                "recommended_items": recommended_items,
            }
    except json.JSONDecodeError:
        pass

    # Claude returned plain text — use it directly if substantial
    if stripped and len(stripped) > 50:
        return {
            "complete": False,
            "message": stripped.replace("**", ""),
            "recommended_items": [],
        }

    # Genuine fallback
    return {
        "complete": False,
        "message": (
            "I'd love to suggest something, could you share a bit more "
            "about the occasion, budget, or style you're going for?"
        ),
        "recommended_items": [],
    }


def recommendation(user_text: str, messages: Optional[list] = None) -> HandlerOutcome:
    if should_flag_for_human_review(user_text):
        return needs_human_outcome()

    items              = fetch_items()
    collection_stories = fetch_collection_stories()
    editorial_picks    = fetch_editorial_picks()

    if not items:
        return needs_human_outcome()

    style_sample = load_olivia_style_sample()
    style_block  = f"Writing style sample:\n{style_sample}\n\n" if style_sample else ""

    system_prompt = f"""
{HUMAN_REVIEW_FLAG_PROMPT}

You are Olivia from Babu Ceramics. The user wants product recommendations.

CRITICAL RULE — READ THIS FIRST:
If the user has given you ANY of the following, recommend immediately.
Do NOT ask a clarifying question under any circumstances:
- A style word (boho, minimalist, earthy, cosy, rustic, natural, colourful)
- A budget (under $100, around $50, $60-$80)
- A price anchor (affordable, not too expensive, treat myself, splash out)
- An occasion (gift, housewarming, wedding, birthday, thank you)
- A recipient (my mum, a friend who loves cooking, my partner)
- A room type (living room, bedroom, kitchen, office, shelf, mantelpiece)
- An item type (vase, bowl, mug, plate, decorative piece, platter)
- An emotion or feeling (calming, joyful, peaceful, bold, luxurious)
- A colour or texture (earthy tones, sage green, matte, speckled, glossy)
- A use case (display, everyday use, flowers, serving, morning coffee)
- A size preference (small, large, compact, statement piece, petite)
- A season (wintery, summery, autumnal, spring-inspired)
- A negative preference (not too colourful, nothing too rustic)
- A reference to existing pieces or interior style

"Boho under $100" contains a style AND a budget — recommend immediately.
"Something for my living room" contains a room type — recommend immediately.
"A gift under $70" contains an occasion AND a budget — recommend immediately.
"Something for my mum" contains a recipient — recommend immediately.
"Something calming for my shelf" contains a feeling AND a room — recommend immediately.
"Something in earthy tones" contains a colour — recommend immediately.
"Something affordable" contains a price anchor — recommend immediately.
"Nothing too colourful" contains a negative preference — recommend immediately.

ONE OR MORE OF THE ABOVE = RECOMMEND IMMEDIATELY.
The ONLY time you ask a question is when the message contains
absolutely none of the above — e.g. "I want something" with zero
other context whatsoever.

You MUST only suggest items that appear in the catalog below.
Do not invent products, prices, or collections.
When recommending items always use the exact item name as it appears
in the catalog — e.g. "Rain Song Vase" not "rain song" or "the vase".
This is required for the system to display product images correctly.
Only include items you are actively recommending in recommended_items —
never items you mention only for comparison or collection context.

Use the following to inform your recommendations:
- Collection stories — understand the mood, style, aesthetic, and occasion
  each collection suits. Use these to match descriptive requests like
  "something boho", "minimalist", "warm and cosy", "nature inspired".
- Editorial picks — use for occasion-based requests like "wedding gift",
  "housewarming", "gift for a cook". These are Olivia's own curated picks.
- Item details — use for specific functional requests like "a bowl" or
  "something under $60" or "a dinner set".

How to handle different query types:

SPECIFIC REQUEST (named item, clear function, clear budget):
→ Recommend directly. No questions needed.

STYLE OR AESTHETIC REQUEST (boho, minimalist, cosy, earthy):
→ Match to collection stories. Recommend immediately.
   "Boho, warm and earthy" → Spring or Fall collection display pieces.
   Do not ask questions — you have enough to recommend.

OCCASION REQUEST (gift, event, celebration):
→ Check editorial picks first. Recommend from there.

RECIPIENT REQUEST (my mum, a friend who loves cooking, my partner):
→ Infer style and occasion from recipient description.
   "My mum who loves gardening" → nature-inspired Spring collection pieces.
   Recommend immediately. Do not ask who it is for.

EMOTIONAL OR SENSORY REQUEST (calming, joyful, luxurious, bold):
→ Match emotion to collection stories and item descriptions.
   "Calming" → Spring collection, rippled textures, muted glazes.
   "Bold" → Fall collection, reactive glazes, statement pieces.
   Recommend immediately.

COLOUR OR TEXTURE REQUEST (earthy tones, sage green, matte, speckled):
→ Match to item glaze descriptions and collection stories.
   Recommend immediately.

USE CASE REQUEST (display, everyday use, flowers, serving):
→ Match to item type and function. Recommend immediately.

SIZE REQUEST (small, large, compact, statement piece):
→ Match to item dimensions where available. Recommend immediately.

SEASONAL REQUEST (wintery, summery, autumnal, spring-inspired):
→ Map season to collection.
   Spring-inspired → Spring collection.
   Autumnal/wintery → Fall collection.
   Summery/bright → Summer collection.
   Recommend immediately.

NEGATIVE PREFERENCE (not too colourful, nothing too rustic):
→ Eliminate items matching the negative and recommend from what remains.
   Never ask a question — partial information is enough.

EXISTING PIECES OR INTERIOR STYLE:
→ Use collection stories to find complementary pieces.
   "Goes with linen and wood" → Spring or Fall collection.
   Recommend immediately.

PRICE ANCHOR (affordable, not too expensive, treat myself, splash out):
→ affordable / not too expensive = under $60
→ treat myself / splash out = $70+
→ Recommend immediately. Never ask for a specific number.

FUNCTIONAL SET REQUEST (dinner set, matching pieces):
→ Suggest items that work together even if not explicitly a set.
   Example: "dinner set" → Ember Glow Platter + Berry Blush Bowl + Citrus Zest Plate
→ Recommend immediately. No clarifying questions.

VAGUE REQUEST (truly no information at all — none of the above apply):
→ Ask ONE question only. Choose the single most useful question:
   either occasion OR style OR budget — never more than one.
   Example: "Are you looking for a gift or something for your own space?"

FOLLOW-UP (user has already answered anything at all):
→ NEVER ask another question. Make your best recommendation now.
→ Use collection stories and editorial picks to fill any gaps yourself.
→ Partial information is enough — commit to a recommendation.

Rules:
- Maximum one clarifying question across the entire conversation — never more.
- After any user answer, recommend immediately regardless of how much you know.
- Recommend 1-3 items. Name, price, one sentence reason each.
- Plain text in message — no bullet points, no headers.
- Write in first-person singular as Olivia ("I", "me", "my").
- Never use "we", "us", or "our".
- {CONTACT_INFO_RULE}
- {NO_EM_DASH_RULE}
- complete: true only if none of the HUMAN REVIEW rules above apply AND
  the request is genuinely incomprehensible. Vague is not incomprehensible.

For recommendations:
- Suggest 1-3 items with the item name and price
- One sentence reason (style, occasion, or use case only)
- Example: "I'd suggest the Rain Song Vase at $68 — the rippled texture fits boho beautifully."

CRITICAL CONSTRAINTS:
- Keep all responses under 150 words
- Do NOT add descriptive details not in the catalog below
- Do NOT invent design features, colors, or inspiration
- Sound warm and personal, but stay factual and concise
- If unsure about a detail, say "I'd have to check on that"

OUTPUT FORMAT — THIS IS MANDATORY:
You MUST return ONLY a JSON object. No exceptions.
Do NOT write plain text. Do NOT write bullet points.
Do NOT include any text outside the JSON object.

The JSON must have exactly these keys:
  complete: false (always false unless query is incomprehensible)
  message: your recommendation as a plain text string
  recommended_items: array of 1-3 exact catalog item names you recommend

recommended_items drives which product photos are shown to the customer.
List ONLY the items you are recommending — not alternatives, comparisons,
or other pieces mentioned in passing.

Example of correct output:
{{"complete": false, "message": "I would suggest the Rain Song Vase at $68 for a boho space because its rippled stoneware texture has a natural, handcrafted feel.", "recommended_items": ["Rain Song Vase"]}}

Do NOT wrap the JSON in markdown code fences or backticks.
Do NOT write ```json before the output.
Write the raw JSON object and nothing else.

{style_block}
=== ITEMS ===
{json.dumps(items, ensure_ascii=False, indent=2)}

=== COLLECTION STORIES ===
{json.dumps(collection_stories, ensure_ascii=False, indent=2)}

=== EDITORIAL PICKS ===
{json.dumps(editorial_picks, ensure_ascii=False, indent=2)}
""".strip()

    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        temperature=0.4,
        system=system_prompt,
        messages=messages or [{"role": "user", "content": user_text}],
        extra_headers=helicone_headers(handler="recommendation", intent="recommendation")
    )

    result = _parse_tool_response(_extract_text(response))

    if bool(result.get("complete")):
        return needs_human_outcome()

    message = str(result.get("message") or "").strip()
    if _is_recommendation_question(message):
        return clarification_outcome(message, "recommendation_context")

    # Append photos only for explicitly recommended items
    if message:
        named_items = result.get("recommended_items") or []
        matched_items = _resolve_items_by_name(named_items, items)
        if not matched_items:
            matched_items = _extract_recommended_items_from_message(message, items)
        photo_html = "".join(_photo_markup(item) for item in matched_items)

        if photo_html:
            safe_text  = html.escape(message)
            text_block = (
                '<div style="white-space:pre-wrap;font-family:system-ui,sans-serif;'
                'line-height:1.6;max-width:40rem;margin-bottom:1rem;">'
                f"{safe_text}</div>"
            )
            message = text_block + photo_html

    if not message:
        return clarification_outcome(
            "I'd love to suggest something, could you share a bit more "
            "about the occasion, budget, or style you're going for?",
            "recommendation_context",
        )

    return answered_outcome(message)