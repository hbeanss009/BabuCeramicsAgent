import json
from pathlib import Path
from typing import Any, Optional

from opentelemetry import trace as otel_trace
from openinference.instrumentation import OITracer
from openinference.instrumentation.config import TraceConfig

from client_config import MODEL, client

tracer = OITracer(
    otel_trace.get_tracer("BabuCeramicsAgent.pricing_tool"),
    TraceConfig(),
)

_CATALOG_PATH = Path(__file__).with_name("catalog.json")


def _extract_text(response: Any) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    return ""


def _load_items() -> list[dict[str, Any]]:
    with _CATALOG_PATH.open(encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("items", [])


def _normalize_name(value: str) -> str:
    return value.strip().lower()


def _parse_item_name_input(item_name: Optional[str]) -> list[str]:
    if not item_name or not item_name.strip():
        return []
    return [
        name.strip()
        for name in item_name.replace(" and ", ",").split(",")
        if name.strip()
    ]


def _extract_names_from_query(user_query: Optional[str], known_names: list[str]) -> list[str]:
    if not user_query:
        return []
    lowered_query = user_query.lower()
    matched = [name for name in known_names if name.lower() in lowered_query]
    if matched:
        return matched

    response = client.messages.create(
        model=MODEL,
        max_tokens=50,
        temperature=0,
        system=(
            "Extract all item names mentioned in the user's pricing question. "
            "Return a comma-separated list of item names. "
            "If no item is mentioned, return exactly: MISSING"
        ),
        messages=[{"role": "user", "content": user_query}],
    )
    extracted = _extract_text(response)
    if extracted.upper() == "MISSING":
        return []
    return [name.strip() for name in extracted.split(",") if name.strip()]


@tracer.tool
def pricing_tool(
    *, item_name: Optional[str] = None, user_query: Optional[str] = None, **_: Any
) -> str:
    items = _load_items()
    known_names = sorted(
        {str(it.get("name", "")).strip() for it in items if it.get("name")}
    )
    requested_names = _parse_item_name_input(item_name)
    if not requested_names:
        requested_names = _extract_names_from_query(user_query, known_names)

    if not requested_names:
        return (
            "Could you share the item name(s) so I can check the exact price for you?"
        )

    items_by_name: dict[str, dict[str, Any]] = {}
    for it in items:
        name = str(it.get("name", "")).strip()
        if name and _normalize_name(name) not in items_by_name:
            items_by_name[_normalize_name(name)] = it

    found_lines: list[str] = []
    missing: list[str] = []
    for requested in requested_names:
        match = items_by_name.get(_normalize_name(requested))
        if not match:
            missing.append(requested)
            continue
        found_lines.append(f"- {match.get('name')}: ${match.get('price')}")

    if not found_lines:
        available = ", ".join(known_names)
        return (
            f"I couldn't find these item(s): {', '.join(missing)}. "
            f"Available items: {available}."
        )

    if missing:
        return (
            "Here are the prices I found:\n"
            + "\n".join(found_lines)
            + f"\n\nI couldn't find: {', '.join(missing)}."
        )

    if len(found_lines) == 1:
        return "The price is:\n" + found_lines[0]
    return "Here are the prices:\n" + "\n".join(found_lines)

