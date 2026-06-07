from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional

from client_config import MODEL, client
from handler_result import HandlerOutcome, extract_html_suffix
from utils.helicone import helicone_headers
from utils.style_sample import CONTACT_INFO_RULE, NO_EM_DASH_RULE, sanitize_customer_output

_EMAIL_GREETING = "Hi there,"
_EMAIL_CLOSING = "Warmly,"
_EMAIL_SIGNATURE = "Olivia Babu"

_INTENT_LABELS = {
    "item_inquiry": "product / item details",
    "collection_inquiry": "collection and catalog information",
    "recommendation": "product recommendations",
    "orders": "orders, shipping, returns, or custom orders",
}


def _extract_text(response: Any) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    return ""


def _strip_html(text: str) -> str:
    if not text or "<" not in text:
        return text.strip()
    plain = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", plain)).strip()


def _format_history(messages: Optional[list]) -> str:
    if not messages:
        return "(no prior messages)"
    lines: List[str] = []
    for msg in messages:
        role = str(msg.get("role", "user")).capitalize()
        content = _strip_html(str(msg.get("content", "")))
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no prior messages)"


def merge_clarifying_questions(
    user_query: str,
    messages: Optional[list],
    blocked: Dict[str, HandlerOutcome],
) -> str:
    """Combine all blocked intent slots into one Olivia question."""
    if not blocked:
        return ""

    if len(blocked) == 1:
        outcome = next(iter(blocked.values()))
        question = str(outcome.get("clarifying_question") or "").strip()
        if question:
            return question

    slots_lines: List[str] = []
    for intent, outcome in blocked.items():
        label = _INTENT_LABELS.get(intent, intent.replace("_", " "))
        slot = outcome.get("missing_slot") or "details"
        question = str(outcome.get("clarifying_question") or "").strip()
        slots_lines.append(f"- {label} ({slot}): {question}")

    slots_block = "\n".join(slots_lines)
    history = _format_history(messages)

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        temperature=0.0,
        system=(
            "You are Olivia from Babu Ceramics.\n"
            "Write exactly ONE follow-up question for the customer.\n"
            "Rules:\n"
            "- Include EVERY missing piece of information listed below — do not omit any.\n"
            "- Use one or two connected sentences; no numbered list, no bullets.\n"
            "- Warm, natural, first-person singular (I, me, my). Never use we/us/our.\n"
            "- Do not repeat information the customer already gave in the conversation.\n"
            "- Output only the question text — no greeting, no signature.\n"
            f"- {NO_EM_DASH_RULE}"
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Customer's latest message:\n{user_query}\n\n"
                f"Conversation so far:\n{history}\n\n"
                f"Each area still needs this information:\n{slots_block}\n\n"
                "Write ONE compound question that asks for ALL of the above."
            ),
        }],
        extra_headers=helicone_headers(handler="clarification_merger", intent="orchestration"),
    )
    merged = _extract_text(response)
    if merged:
        return sanitize_customer_output(merged)

    # Fallback: join draft questions
    drafts = [
        str(o.get("clarifying_question") or "").strip()
        for o in blocked.values()
        if str(o.get("clarifying_question") or "").strip()
    ]
    return sanitize_customer_output(" ".join(drafts))


def synthesize_answers(
    user_query: str,
    answered: Dict[str, HandlerOutcome],
) -> str:
    """Combine answered intent fragments into one reply body (no questions)."""
    if not answered:
        return ""

    if len(answered) == 1:
        return str(next(iter(answered.values())).get("message") or "").strip()

    fragments = []
    for intent, outcome in answered.items():
        raw = str(outcome.get("message") or "").strip()
        if not raw:
            continue
        label = _INTENT_LABELS.get(intent, intent)
        fragments.append(f"### {label}:\n{_strip_html(raw)}")

    if not fragments:
        return ""

    combined_context = "\n\n".join(fragments)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        temperature=0.15,
        system=(
            "You are Olivia from Babu Ceramics.\n"
            "Combine the following answer fragments into one warm, natural email body.\n"
            "Rules:\n"
            "- Do NOT write a greeting or signature.\n"
            "- Do NOT ask any clarifying questions.\n"
            "- Do not use headers or bullet points.\n"
            "- First-person singular (I, me, my). Never use we/us/our.\n"
            "- Do not repeat the same information twice.\n"
            f"- {CONTACT_INFO_RULE}\n"
            f"- {NO_EM_DASH_RULE}"
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Customer asked: {user_query}\n\n"
                f"Answer fragments:\n\n{combined_context}\n\n"
                "Write the middle body paragraphs only."
            ),
        }],
        extra_headers=helicone_headers(handler="answer_synthesis", intent="orchestration"),
    )
    return sanitize_customer_output(_extract_text(response))


def _wrap_plain_email(body: str) -> str:
    text = body.strip()
    return f"{_EMAIL_GREETING}\n\n{text}\n\n{_EMAIL_CLOSING}\n{_EMAIL_SIGNATURE}"


def _reply_html(text_email: str, html_suffix: str = "") -> str:
    safe = html.escape(text_email)
    block = (
        '<div style="white-space:pre-wrap;font-family:system-ui,sans-serif;'
        'line-height:1.6;max-width:40rem;margin-bottom:1rem;">'
        f"{safe}</div>"
    )
    return block + html_suffix if html_suffix else block


def assemble_customer_reply(
    answer_body: str,
    merged_question: Optional[str] = None,
    photo_suffix: str = "",
) -> str:
    """Build the final customer-facing message."""
    answer_body = (answer_body or "").strip()
    merged_question = (merged_question or "").strip()
    if not photo_suffix:
        photo_suffix = extract_html_suffix(answer_body)

    if answer_body.startswith("<") and not merged_question:
        return sanitize_customer_output(answer_body)

    if answer_body.startswith("<") and merged_question:
        plain_answer = _strip_html(answer_body)
        body = plain_answer
        if body and merged_question:
            body = f"{body}\n\n{merged_question}"
        elif merged_question:
            body = merged_question
        return sanitize_customer_output(_reply_html(_wrap_plain_email(body), photo_suffix))

    parts: List[str] = []
    if answer_body:
        if "<" in answer_body:
            parts.append(_strip_html(answer_body))
        else:
            parts.append(answer_body)
    if merged_question:
        parts.append(merged_question)

    if not parts:
        return ""

    if len(parts) == 1 and not photo_suffix and not merged_question:
        single = parts[0]
        if single.startswith("<"):
            return sanitize_customer_output(single)
        return sanitize_customer_output(_reply_html(_wrap_plain_email(single)))

    body = _wrap_plain_email("\n\n".join(parts))
    return sanitize_customer_output(_reply_html(body, photo_suffix))


def collect_photo_suffixes(answered: Dict[str, HandlerOutcome]) -> str:
    suffixes: List[str] = []
    seen: set[str] = set()
    for outcome in answered.values():
        fragment = extract_html_suffix(str(outcome.get("message") or ""))
        if fragment and fragment not in seen:
            seen.add(fragment)
            suffixes.append(fragment)
    return "".join(suffixes)
