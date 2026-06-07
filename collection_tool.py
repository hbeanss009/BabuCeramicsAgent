import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from opentelemetry import trace as otel_trace
from openinference.instrumentation import OITracer
from openinference.instrumentation.config import TraceConfig

tracer = OITracer(
    otel_trace.get_tracer("BabuCeramicsAgent.collection_tool"),
    TraceConfig(),
)

_CATALOG = Path(__file__).with_name("catalog.json")


def _load_items() -> List[Dict[str, Any]]:
    with _CATALOG.open(encoding="utf-8") as f:
        return json.load(f).get("items", [])


def _group_by_collection(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for row in items:
        name = str(row.get("collection") or "Other").strip()
        if name not in groups:
            groups[name] = {
                "description": str(row.get("collection_description", "")),
                "items": [],
            }
        groups[name]["items"].append(row)
    return groups


@tracer.tool
def collection_tool(
    *,
    user_query: Optional[str] = None,
    collection_name: Optional[str] = None,
    **_: Any,
) -> str:
    """Used for view_collection (user_query) and view_catalog_items (collection_name)."""
    items = _load_items()
    if not items:
        return "No catalog data available."

    groups = _group_by_collection(items)

    if collection_name:
        target = collection_name.strip().lower()
        match = next((k for k in groups if k.lower() == target), None)
        if not match:
            return f"No collection {collection_name!r}. Available: {', '.join(sorted(groups))}."
        g = groups[match]
        lines = [f"{match}", g["description"], "Items:"]
        for it in g["items"]:
            lines.append(
                f"  - {it.get('name')} ({it.get('category')}) — ${it.get('price')}"
            )
        return "\n".join(lines)

    # Overview: list every collection and its items (user_query is optional context for the model)
    parts = []
    for coll in sorted(groups):
        g = groups[coll]
        item_names = ", ".join(str(it.get("name", "")) for it in g["items"])
        parts.append(f"{coll}\n{g['description']}\nItems: {item_names}")
    return "\n\n".join(parts)
