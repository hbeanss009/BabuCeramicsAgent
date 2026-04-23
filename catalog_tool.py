import json
from pathlib import Path

from opentelemetry import trace as otel_trace
from openinference.instrumentation import OITracer
from openinference.instrumentation.config import TraceConfig

tracer = OITracer(
    otel_trace.get_tracer("BabuCeramicsAgent.catalog_tool"),
    TraceConfig(),
)

_CATALOG = Path(__file__).with_name("catalog.json")


@tracer.tool
def catalog_tool(*, collection_name: str, **_: object) -> str:
    items = json.loads(_CATALOG.read_text(encoding="utf-8")).get("items", [])
    key = collection_name.strip().lower()
    rows = [it for it in items if str(it.get("collection", "")).strip().lower() == key]
    if not rows:
        return f"No items found for collection {collection_name!r}."
    lines = [
        str(rows[0].get("collection_description", "")),
        "Items:",
    ]
    for it in rows:
        lines.append(
            f"  - {it.get('name')} ({it.get('category')}) — ${it.get('price')}: {it.get('description', '')}"
        )
    return "\n".join(lines)