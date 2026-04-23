# brain of the project
"""
BabuCeramicsAgent/
├── main.py                    ← Entry point + LLM (router) 
├── tools_registry.py          ← Tool schemas + function map
├── item_inquiry.py            ← Item inquiry (router)
├── pricing_tool.py            ← Pricing tool (skill)
├── quality_tool.py            ← Quality tool (skill)
├── collection_tool.py         ← Collection tool (skill)
├── recommendation.py          ← Recommendation (LLM)
├── orders.py                  ← Orders route (router)
├── item_inquiry_data.json     ← Shared data source
├── requirements.txt
└── .env
"""
import warnings
warnings.filterwarnings('ignore')
from dotenv import load_dotenv
from contextlib import nullcontext
import json
import item_inquiry
import recommendation
import orders
from client_config import client, MODEL

tracer = None
trace_provider = None

load_dotenv()


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

try:
    import importlib
    import os
    from urllib.parse import urlparse

    px = importlib.import_module("phoenix")
    register = importlib.import_module("phoenix.otel").register
    otel_trace = importlib.import_module("opentelemetry.trace")

    configured_endpoint = (
        os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
        or os.getenv("PHOENIX_ENDPOINT")
        or "http://127.0.0.1:6006"
    ).rstrip("/")
    parsed_endpoint = urlparse(configured_endpoint)

    if (
        parsed_endpoint.hostname in {"127.0.0.1", "localhost"}
        and not configured_endpoint.endswith("/v1/traces")
    ):
        px.launch_app()

    if configured_endpoint.endswith("/v1/traces"):
        collector_endpoint = configured_endpoint
    else:
        collector_endpoint = f"{configured_endpoint}/v1/traces"

    if (
        parsed_endpoint.hostname == "app.phoenix.arize.com"
        and not parsed_endpoint.path.startswith("/s/")
    ):
        print(
            "[tracing warning] PHOENIX cloud endpoint usually needs "
            "'/s/<space-name>/v1/traces'."
        )

    phoenix_project_name = os.getenv("PHOENIX_PROJECT_NAME", "BabuCeramicsAgent")

    trace_provider = register(
        project_name=phoenix_project_name,
        endpoint=collector_endpoint,
        api_key=os.getenv("PHOENIX_API_KEY"),
        protocol="http/protobuf",
        set_global_tracer_provider=True,
    )
    tracer = otel_trace.get_tracer("BabuCeramicsAgent.main")
except Exception as exc:
    # Tracing is optional; continue running the router if Phoenix is unavailable.
    print(f"[tracing disabled] Phoenix init failed: {exc}")
    tracer = None

ROUTE_HANDLERS = {
    "item_inquiry": item_inquiry.item_inquiry,
    "recommendation": recommendation.recommendation,
    "orders": orders.orders,
}

CLASSIFIER_SYSTEM_PROMPT = """
You are an intent classifier for a ceramics business assistant.
Return exactly one label and nothing else based on the user's question.
- item_inquiry
- recommendation
- orders
Choose:
- item_inquiry if user asks anything related to the catalog, item details, price, care, collection, stock.
- recommendation if user asks for suggestions/recommendations.
- orders if users asks anything related to shipping, returns, placing a custom order.
"""


def fallback_intent(user_text: str) -> str:
    text = user_text.lower()
    if any(word in text for word in ("recommend", "suggest", "best", "gift")):
        return "recommendation"
    if any(
        word in text
        for word in ("order", "shipping", "return", "refund", "delivery", "custom")
    ):
        return "orders"
    return "item_inquiry"


def detect_intent(user_text: str) -> str:
    span_ctx = (
        tracer.start_as_current_span("detect_intent", openinference_span_kind="agent")

        if tracer is not None
        else nullcontext()
    )
    with span_ctx as span:
        _set_span_input(span, user_text)
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=100,
                system=CLASSIFIER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_text}],
                temperature=0.0,
            )
        except Exception as exc:
            print(f"[intent fallback] Classifier request failed: {exc}")
            return fallback_intent(user_text)

        label = next(
            (
                getattr(block, "text", "")
                for block in response.content
                if getattr(block, "type", None) == "text"
            ),
            "",
        ).strip().lower()

        _set_span_output(span, {"label": label})
        if label not in ROUTE_HANDLERS:
            return "item_inquiry"
        return label


def run_router(user_text: str) -> str:
    span_ctx = (
        tracer.start_as_current_span("run_router", openinference_span_kind="chain")
        if tracer is not None
        else nullcontext()
    )
    with span_ctx as span:
        _set_span_input(span, user_text)
        intent = detect_intent(user_text)
        handler = ROUTE_HANDLERS[intent]
        _set_span_output(span, {"routed_to_handler": handler.__name__})
        try:
            result = handler(user_text)
            _set_span_output(
                span,
                {"routed_to_handler": handler.__name__, "response": result},
            )
            return result
        except Exception as exc:
            return (
                "I hit a network connection issue while processing your request. "
                f"Please retry in a moment. Details: {exc}"
            )


if __name__ == "__main__":
    user_input = input("How can I help you today? Tell me what you are looking for? ")
    print(run_router(user_input))
