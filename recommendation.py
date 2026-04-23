import json
from pathlib import Path
from typing import Any, Dict, List, cast

from opentelemetry import trace as otel_trace

from client_config import MODEL, client

tracer = otel_trace.get_tracer("BabuCeramicsAgent.recommendation")

_CATALOG_PATH = Path(__file__).with_name("catalog.json")
_STYLE_PATH = Path(__file__).with_name("olivia_writing_style.txt")


def _to_span_io_value(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _set_span_input(span: object, value: object) -> None:
    if span is None:
        return
    set_input = getattr(span, "set_input", None)
    if callable(set_input):
        set_input(value)
        return
    set_attribute = getattr(span, "set_attribute", None)
    if callable(set_attribute):
        set_attribute("input.value", _to_span_io_value(value))


def _set_span_output(span: object, value: object) -> None:
    if span is None:
        return
    set_output = getattr(span, "set_output", None)
    if callable(set_output):
        set_output(value)
        return
    set_attribute = getattr(span, "set_attribute", None)
    if callable(set_attribute):
        set_attribute("output.value", _to_span_io_value(value))


def _style_text() -> str:
    try:
        return _STYLE_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _extract_text(response: Any) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    return ""


def _load_catalog_items() -> List[Dict[str, Any]]:
    with _CATALOG_PATH.open(encoding="utf-8") as f:
        payload = json.load(f)
    return list(payload.get("items", []))


def _items_for_prompt(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Slim fields for the model — keeps context focused and smaller."""
    slim: List[Dict[str, Any]] = []
    for it in items:
        slim.append(
            {
                "id": it.get("id"),
                "name": it.get("name"),
                "description": it.get("description"),
                "price": it.get("price"),
                "category": it.get("category"),
                "collection": it.get("collection"),
                "collection_description": it.get("collection_description"),
            }
        )
    return slim


def recommendation(user_text: str) -> str:
    with cast(Any, tracer).start_as_current_span(
        "recommendation",
        openinference_span_kind="agent",
    ) as span:
        span_any = cast(Any, span)
        _set_span_input(span_any, user_text)

        items = _load_catalog_items()
        if not items:
            result = (
                "Our catalog is updating right now — please check back in a bit for personalized picks."
            )
        else:
            catalog_blob = json.dumps(_items_for_prompt(items), ensure_ascii=False, indent=2)
            style_sample = _style_text()
            style_block = (
                f"Writing style sample:\n{style_sample}\n\n" if style_sample else ""
            )

            system_prompt = f"""
You are Olivia from Babu Ceramics. The user wants product recommendations.

You MUST only suggest items that appear in the catalog JSON below. Do not invent products, prices, or collections.
Pick one or a few items that best match what they asked for (occasion, style, budget, category, gift ideas, their persona, potential needs, etc.).
For each suggested item, mention the name and price, and give a short, specific reason tied to their request and the item description.
For example, if a user says, "we are a newly wed couple and we are looking for some pottery for our home"
suggest the following items : "for a newly wed couple, a dinner set with 4 "Salad Plates", 4 "Dinner Plates", 4 "Soup Bowls", would be a great addition to your dining table."




Tone:
- warm, friendly, concise
- sound like Olivia from Babu Ceramics
- not corporate; natural and helpful

{style_block}Catalog (only valid items):
{catalog_blob}

Output rules:
- Reply in plain text for the customer (no JSON, no bullet labels like "Recommendation 1:" unless it reads naturally).
- If the request is vague, ask one short clarifying question and still offer 1–2 reasonable options from the catalog.
""".strip()

            response = client.messages.create(
                model=MODEL,
                max_tokens=600,
                temperature=0.4,
                system=system_prompt,
                messages=[{"role": "user", "content": user_text}],
            )

            result = _extract_text(response) or (
                "I'd love to suggest something — could you share a bit more about the occasion, budget, or style you're going for?"
            )

        _set_span_output(span_any, result)
        return result
