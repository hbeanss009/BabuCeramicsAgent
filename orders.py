from dotenv import load_dotenv
from opentelemetry import trace as otel_trace
from typing import Any, cast
import json

import custom_order_enquiry_tool
import order_status_enquiry_tool
import other_item_related_enquiry_tool
import returns_enquiry_tool
import shipping_enquiry_tool
from client_config import client, MODEL

load_dotenv()
tracer = otel_trace.get_tracer("BabuCeramicsAgent.orders")


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
ROUTE_HANDLERS = {
    "order_status_enquiry_tool": order_status_enquiry_tool.order_status_enquiry_tool,
    "returns_enquiry_tool": returns_enquiry_tool.returns_enquiry_tool,
    "shipping_enquiry_tool": shipping_enquiry_tool.shipping_enquiry_tool,
    "custom_order_enquiry_tool": custom_order_enquiry_tool.custom_order_enquiry_tool,
    "other_item_related_enquiry_tool": other_item_related_enquiry_tool.other_item_related_enquiry_tool,
}

CLASSIFIER_SYSTEM_PROMPT = """
You are an order related classifier for a ceramics business assistant.
Return exactly one label and nothing else based on the user's question.
- order_status_enquiry_tool
- returns_enquiry_tool
- shipping_enquiry_tool
- custom_order_enquiry_tool
- other_item_related_enquiry_tool

Choose:
- order_status_enquiry_tool if user asks anything related to the order status.
- returns_enquiry_tool if user asks anything related to returns.
- shipping_enquiry_tool if user asks anything related to shipping.
- custom_order_enquiry_tool if user asks anything related to placing a custom order.
- other_item_related_enquiry_tool if user asks anything related to other item related inquiries.
"""

def orders(user_text: str) -> str:
    with cast(Any, tracer).start_as_current_span(
        "orders_router", openinference_span_kind="chain"
    ) as span:
        span_any = cast(Any, span)
        _set_span_input(span_any, user_text)

        response = client.messages.create(
            model=MODEL,
            max_tokens=100,
            system=CLASSIFIER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text}],
            temperature=0.0,
        )

        label = next(
            (
                getattr(block, "text", "")
                for block in response.content
                if getattr(block, "type", None) == "text"
            ),
            "",
        ).strip().lower()

        if label not in ROUTE_HANDLERS:
            label = "order_status_enquiry_tool"

        with cast(Any, tracer).start_as_current_span(
            "route_handler",
            openinference_span_kind="tool",
        ) as route_span:
            route_any = cast(Any, route_span)
            _set_span_input(route_any, label)
            handler = ROUTE_HANDLERS[label]
            _set_span_output(route_any, {"handler": handler.__name__})
            result = handler(user_query=user_text)

        _set_span_output(
            span_any,
            {"intent": label, "handler": handler.__name__, "response": result},
        )

        return result
