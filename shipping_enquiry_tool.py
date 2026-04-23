# shipping_enquiry_tool.py — simple LLM-based check + reply
from pathlib import Path
from typing import Any

from opentelemetry import trace as otel_trace
from openinference.instrumentation import OITracer
from openinference.instrumentation.config import TraceConfig

from client_config import client, MODEL

tracer = OITracer(
    otel_trace.get_tracer("BabuCeramicsAgent.shipping_enquiry_tool"),
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
def shipping_enquiry_tool(*, user_query: str, **_: Any) -> str:
    style_sample = _style_text()
    system = f"""
You assist with shipping related inquiries for the ceramics store. 

User might ask questions about shipping options, shipping costs, shipping times etc. 
If user asks about shipping options - tell them the only carrier we use is Fedex and 
the shipping costs are calculated based on the weight of the order and shipping destination. 

If user asks about shipping costs/time and details are missing, ask for:
- destination city + zip code
- item names + quantity

Return the shipping cost to the user and tell them it's for the "Home Delivery" service and can change
if user wants to use a different service. If they want to know the price for a different service, 
ask them to check the website for pricing. 

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
    return _text(response) or "Sorry, I could not process that question right now."



