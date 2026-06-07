from __future__ import annotations

from typing import Any, Optional

from client_config import MODEL, client
from context_builder import fetch_artist_notes, fetch_faqs
from handler_result import HandlerOutcome, needs_human_outcome, outcome_from_complete_message
from utils.helicone import helicone_headers
from utils.llm_json import parse_complete_message_json
from utils.human_review import should_flag_for_human_review
from utils.orders_sources import format_orders_sources, orders_sources_missing
from utils.style_sample import CONTACT_INFO_RULE, NO_EM_DASH_RULE, load_olivia_style_sample
from utils.tool_prompts import HUMAN_REVIEW_FLAG_PROMPT, ORDERS_SOURCE_GROUNDING_PROMPT


def _text(response: Any) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    return ""


def _parse_tool_response(raw: str) -> HandlerOutcome:
    fallback = "Thank you for your shipping inquiry. I will get back to you soon."
    complete, message = parse_complete_message_json(
        raw, fallback_message=fallback
    )
    return outcome_from_complete_message(complete, message, missing_slot="order_details")


def shipping_enquiry_tool(
    user_query: str,
    messages: Optional[list] = None,
    **_: Any
) -> HandlerOutcome:

    if should_flag_for_human_review(user_query):
        return needs_human_outcome()

    style_sample = load_olivia_style_sample()
    faqs = fetch_faqs()
    artist_notes = fetch_artist_notes()

    if orders_sources_missing(faqs, artist_notes):
        return needs_human_outcome()

    system = f"""
{HUMAN_REVIEW_FLAG_PROMPT}

{ORDERS_SOURCE_GROUNDING_PROMPT}

You are Olivia from Babu Ceramics replying to a shipping inquiry.

Use the FAQs and artist notes below to answer general shipping questions accurately
(delivery times, packaging, tracking, international shipping, etc.).

Required details for processing a specific shipping request:
1) Item details — which piece(s) they want shipped.
2) Quantity — how many pieces.
3) Needed-by timeline/date.
4) Shipping address.

Rules:
- If the customer is asking a general shipping question (cost, timing, packaging,
  tracking, international): answer using the sources. Set complete to false and
  message to your answer — but ONLY if the answer is in the sources.
- If any required detail is missing or too vague: set complete to false and ask
  only for what is missing.
- If all details are present: set complete to true and set message to an empty
  string. Do not send any reply to the customer (a human will follow up).

Writing style for message:
- Warm, friendly, concise, creator-to-creator feel
- Occasional soft enthusiasm is okay
- Natural, not corporate
- Do not repeat their whole message back to them
- Write in first-person singular as Olivia ("I", "me", "my").
- Never use "we", "us", or "our".
- {CONTACT_INFO_RULE}
- {NO_EM_DASH_RULE}

Style sample:
{style_sample}

{format_orders_sources(faqs, artist_notes)}

Output rules:
- Return ONLY valid JSON with exactly these keys: complete (boolean), message (string).
- No markdown, no code fences, no extra keys.
""".strip()

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=system,
        messages=messages or [{"role": "user", "content": user_query}],
        extra_headers=helicone_headers(handler="shipping_enquiry", intent="orders"),
        temperature=0.2,
    )

    return _parse_tool_response(_text(response))
