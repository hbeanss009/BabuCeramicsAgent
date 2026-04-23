import json
from pathlib import Path
from typing import Any, Dict, Optional

from opentelemetry import trace as otel_trace
from openinference.instrumentation import OITracer
from openinference.instrumentation.config import TraceConfig

from client_config import MODEL, client
from other_item_related_enquiry_tool import other_item_related_enquiry_tool

tracer = OITracer(
    otel_trace.get_tracer("BabuCeramicsAgent.item_details_tool"),
    TraceConfig(),
)

_CATALOG_PATH = Path(__file__).with_name("catalog.json")
_STYLE_PATH = Path(__file__).with_name("olivia_writing_style.txt")


def _extract_text(response: Any) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    return ""


def _load_items() -> list[dict[str, Any]]:
    with _CATALOG_PATH.open(encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("items", [])


def _style_text() -> str:
    try:
        return _STYLE_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _resolve_item_name(item_name: Optional[str], user_query: Optional[str]) -> str:
    if item_name and item_name.strip():
        return item_name.strip()
    if not user_query:
        return ""

    response = client.messages.create(
        model=MODEL,
        max_tokens=30,
        temperature=0,
        system=(
            "Extract the item name from the user's request. "
            "Return only the item name text. "
            "If no item is mentioned, return exactly: MISSING"
        ),
        messages=[{"role": "user", "content": user_query}],
    )
    extracted = _extract_text(response)
    if extracted.upper() == "MISSING":
        return ""
    return extracted


def _find_item(item_name: str, items: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    normalized = item_name.strip().lower()
    # Exact match first
    for item in items:
        if str(item.get("name", "")).strip().lower() == normalized:
            return item
    # Then relaxed contains check
    for item in items:
        if normalized and normalized in str(item.get("name", "")).strip().lower():
            return item
    return None


@tracer.tool
def item_details_tool(
    *, item_name: Optional[str] = None, user_query: Optional[str] = None, **_: Any
) -> str:
    items = _load_items()
    resolved_item_name = _resolve_item_name(item_name, user_query)

    if not resolved_item_name:
        return "Could you share the item name so I can pull the right details for you?"

    item = _find_item(resolved_item_name, items)
    query_context = user_query or f"Tell me about {resolved_item_name}"

    if not item:
        # Fallback path: let other_item_related_enquiry_tool answer in Olivia's style.
        return other_item_related_enquiry_tool(user_query=query_context)

    style_sample = _style_text()
    item_payload: Dict[str, Any] = {
        "name": item.get("name"),
        "description": item.get("description"),
        "price": item.get("price"),
        "dimensions": item.get("dimensions"),
        "weight": item.get("weight"),
        "category": item.get("category"),
        "collection": item.get("collection"),
        "collection_description": item.get("collection_description"),
    }

    response = client.messages.create(
        model=MODEL,
        max_tokens=250,
        temperature=0.2,
        system=(
            "You are Olivia from Babu Ceramics. "
            "Respond in a warm, concise tone similar to the style sample. "
            "Use only the provided item details and answer the user's request clearly."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"User query: {query_context}\n\n"
                    f"Item details: {json.dumps(item_payload, ensure_ascii=False)}\n\n"
                    f"Style sample: {style_sample}\n\n"
                    "Write a customer-ready response."
                ),
            }
        ],
    )

    return _extract_text(response) or (
        f"Here are the details for {item.get('name', resolved_item_name)}: "
        f"{item.get('description', 'No description available')}."
    )
