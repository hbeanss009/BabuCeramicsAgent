from pathlib import Path
from typing import Any

from opentelemetry import trace as otel_trace
from openinference.instrumentation import OITracer
from openinference.instrumentation.config import TraceConfig

from client_config import MODEL, client

tracer = OITracer(
    otel_trace.get_tracer("BabuCeramicsAgent.custom_order_enquiry_tool"),
    TraceConfig(),
)

_STYLE_FILE = Path(__file__).with_name("olivia_writing_style.txt")


def _style_text() -> str:
    try:
        return _STYLE_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _extract_text(response: Any) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    return ""


@tracer.tool
def custom_order_enquiry_tool(*, user_query: str, **_: Any) -> str:
    style_sample = _style_text()
    system_prompt = f"""
You are Olivia from Babu Ceramics replying to a custom order inquiry.

Your job:
1) Check if the user has provided ALL required details:
   - item details (what they want made)
   - quantity (how many pieces)
   - needed-by timeline/date
   - inspiration image link (ask for it if they have one)
2) If any detail is missing, ask only for the missing details.
3) If all details are present, send a short confirmation saying Olivia will review the request and reach out again.

Tone and writing style:
- warm, friendly, concise, creator-to-creator feel
- occasional soft enthusiasm is okay
- keep it natural and not corporate

Style examples:
{style_sample}

Output rules:
- Return only the final response message to the customer.
- Do not output analysis or checklists.
""".strip()

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": user_query}],
        temperature=0.2,
    )

    return _extract_text(response) or (
        "Thanks so much for your custom order request. "
        "Could you share the item details, quantity, needed-by date, "
        "and an inspiration image link if you have one?"
    )
