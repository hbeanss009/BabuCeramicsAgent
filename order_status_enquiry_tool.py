# order_status_enquiry_tool.py — simple LLM-based check + reply
from pathlib import Path
from typing import Any

from opentelemetry import trace as otel_trace
from openinference.instrumentation import OITracer
from openinference.instrumentation.config import TraceConfig

from client_config import client, MODEL

tracer = OITracer(
    otel_trace.get_tracer("BabuCeramicsAgent.order_status_enquiry_tool"),
    TraceConfig(),
)

_STYLE_PATH = Path(__file__).with_name("olivia_writing_style.txt")


def _style_text() -> str:
    try:
        return _STYLE_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _text(response: Any) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    return ""


@tracer.tool
def order_status_enquiry_tool(*, user_query: str, **_: Any) -> str:
    style_sample = _style_text()
    system = f"""
You assist with order status inquiries for the ceramics store. 

From the user's message, decide if they gave enough to check the status of an order: 
1) Order number 

If EITHER is missing or too vague, reply in a friendly tone and ask for what is still needed while also
reminding them to check their email for order status and spam folders for any order related status updates. 
Do not repeat their whole message; be brief.
If Order number is suffficiently provided, ask the user for order number as well and tell them we review 
returns on a case by case basis and they will get a response email within 48 hours.

Writing style:
- warm, friendly, concise
- sound like Olivia from Babu Ceramics
- keep wording natural, not corporate

Style sample:
{style_sample}
""".strip()
    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=system,
        messages=[{"role": "user", "content": user_query}],
    )
    return _text(response) or "Sorry, I could not process that order status question right now."



