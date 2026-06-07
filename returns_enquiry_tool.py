# returns_enquiry_tool.py
from __future__ import annotations

import json
from typing import Any, List, Optional

from client_config import MODEL, client
from context_builder import fetch_artist_notes, fetch_faqs
from handler_result import HandlerOutcome, needs_human_outcome, outcome_from_complete_message
from utils.helicone import helicone_headers
from utils.llm_json import parse_complete_message_json
from utils.human_review import should_flag_for_human_review
from utils.orders_sources import orders_sources_missing
from utils.style_sample import CONTACT_INFO_RULE, NO_EM_DASH_RULE, load_olivia_style_sample
from utils.tool_prompts import HUMAN_REVIEW_FLAG_PROMPT, ORDERS_SOURCE_GROUNDING_PROMPT

_RETURN_FAQ_KEYWORDS = frozenset(
    {
        "return",
        "refund",
        "exchange",
        "damaged",
        "damage",
        "broken",
        "crack",
        "chipped",
        "defect",
    }
)


def _text(response: Any) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    return ""


def _parse_tool_response(raw: str) -> HandlerOutcome:
    fallback = "Sorry, I could not process that return question right now."
    complete, message = parse_complete_message_json(
        raw, fallback_message=fallback
    )
    return outcome_from_complete_message(complete, message, missing_slot="order_details")


def _filter_returns_faqs(faqs: List[Any]) -> List[Any]:
    """Prefer FAQs tagged for returns, refunds, or damage."""
    filtered: List[Any] = []
    for row in faqs:
        if not isinstance(row, dict):
            continue
        blob = json.dumps(row, ensure_ascii=False).lower()
        if any(keyword in blob for keyword in _RETURN_FAQ_KEYWORDS):
            filtered.append(row)
    return filtered if filtered else list(faqs)


def returns_enquiry_tool(
    user_query: str,
    messages: Optional[list] = None,
    **_: Any
) -> HandlerOutcome:

    if should_flag_for_human_review(user_query):
        return needs_human_outcome()

    style_sample = load_olivia_style_sample()
    all_faqs = fetch_faqs()
    artist_notes = fetch_artist_notes()
    returns_faqs = _filter_returns_faqs(all_faqs)

    if orders_sources_missing(returns_faqs, artist_notes):
        return needs_human_outcome()

    system = f"""
{HUMAN_REVIEW_FLAG_PROMPT}

{ORDERS_SOURCE_GROUNDING_PROMPT}

You assist with product return and refund requests for Babu Ceramics.

Use the RETURNS / REFUNDS FAQs and artist notes below. Do not invent policy,
timelines, or refund amounts.

Required details for processing a return with a human:
1) Item / order identification — item name, what they bought, or order number.
2) Reason for return — damaged, broken, wrong item, changed mind, etc.
3) Order number — required before a human can process the return.

=== CASE A: General returns policy (no specific damaged item report) ===
Examples: "What is your return policy?", "How long do refunds take?"
→ Set complete to false.
→ message: answer from sources only — if not in sources, flag (complete: true).

=== CASE B: Missing information ===
If (1) or (2) is missing or too vague:
→ Set complete to false.
→ message: ask only for what is missing (one question at a time).

If (1) and (2) are present but (3) order number is missing:
→ Set complete to false.
→ message: ask for the order number only.

=== CASE C: Damaged, broken, or defective piece (including refund for damage) ===
Triggers: damaged, broken, cracked, chipped, shattered, arrived broken, defective,
wrong item received, refund for a damaged piece, etc.

→ Set complete to true.
→ message: empty string (see HUMAN REVIEW rules above — a human will follow up).

=== CASE D: Return ready to hand off (non-damage) ===
If (1), (2), and (3) are all present AND the reason is NOT damage/broken/defective
(e.g. changed mind, no longer needed):
→ Set complete to true.
→ message: empty string (human will follow up with no auto-reply).

Writing style for message:
- Warm, friendly, concise — sound like Olivia from Babu Ceramics
- Natural, not corporate
- Do not repeat their whole message back to them
- Write in first-person singular as Olivia ("I", "me", "my").
- Never use "we", "us", or "our".
- {CONTACT_INFO_RULE}
- {NO_EM_DASH_RULE}

Style sample:
{style_sample}

RETURNS / REFUNDS FAQs:
{json.dumps(returns_faqs, ensure_ascii=False, indent=2)}

Artist notes:
{json.dumps(artist_notes, ensure_ascii=False, indent=2)}

Output rules:
- Return ONLY valid JSON with exactly these keys: complete (boolean), message (string).
- No markdown, no code fences, no extra keys.
""".strip()

    response = client.messages.create(
        model=MODEL,
        max_tokens=550,
        system=system,
        messages=messages or [{"role": "user", "content": user_query}],
        extra_headers=helicone_headers(handler="returns_enquiry", intent="orders"),
        temperature=0.2,
    )

    return _parse_tool_response(_text(response))
