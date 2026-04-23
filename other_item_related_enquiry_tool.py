import json
from pathlib import Path
from typing import Any, Dict, Optional

from opentelemetry import trace as otel_trace
from openinference.instrumentation import OITracer
from openinference.instrumentation.config import TraceConfig

from client_config import MODEL, client

tracer = OITracer(
    otel_trace.get_tracer("BabuCeramicsAgent.other_item_related_enquiry_tool"),
    TraceConfig(),
)

knowledge_base: Dict[str, str] = {
    "details": "Hand-glazed in her studio with gorgeous glaze variations that make each piece truly unique. Crafted of durable, glazed stoneware.",
    "care": "Durable stoneware that is dishwasher, microwave, and oven safe up to 450°",
    "materials": "Made with 35% pre-consumer recycled clay and 65% virgin clay.",
    "usage": "Designed to mix and match across glaze collections for endless combinations",
}

_STYLE_FILE = Path(__file__).with_name("olivia_writing_style.txt")


def _extract_text(response: Any) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    return ""


def _style_text() -> str:
    try:
        return _STYLE_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


@tracer.tool
def other_item_related_enquiry_tool(
    *, user_query: str, knowledge_base_override: Optional[Dict[str, Any]] = None, **_: Any
) -> str:
    kb = knowledge_base_override or knowledge_base
    style = _style_text()

    system_prompt = f"""
You are Olivia from Babu Ceramics.
Answer the user's item-related question using ONLY the provided knowledge base.
If the answer is not in the knowledge base, say that briefly and ask a short follow-up question.

Tone requirements:
- warm, friendly, conversational
- concise but helpful
- mirror Olivia's style in the sample text

Knowledge base:
{json.dumps(kb, ensure_ascii=False, indent=2)}

Style sample:
{style}

Output only the message to the customer.
""".strip()

    response = client.messages.create(
        model=MODEL,
        max_tokens=250,
        temperature=0.2,
        system=system_prompt,
        messages=[{"role": "user", "content": user_query}],
    )

    return _extract_text(response) or (
        "Thanks so much for your question! Could you share a little more detail so I can help better?"
    )
