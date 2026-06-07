from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import custom_order_enquiry_tool
import returns_enquiry_tool
import shipping_enquiry_tool
from client_config import MODEL, client
from dotenv import load_dotenv
from handler_result import HandlerOutcome, normalize_handler_outcome
from utils.helicone import helicone_headers
from utils.llm_json import strip_code_fence
from utils.orchestrator import merge_clarifying_questions, synthesize_answers
from utils.style_sample import CONTACT_INFO_RULE

load_dotenv()

ROUTE_HANDLERS = {
    "returns_enquiry_tool": returns_enquiry_tool.returns_enquiry_tool,
    "shipping_enquiry_tool": shipping_enquiry_tool.shipping_enquiry_tool,
    "custom_order_enquiry_tool": custom_order_enquiry_tool.custom_order_enquiry_tool,
}

_VALID_ORDER_TOOLS = frozenset(ROUTE_HANDLERS)

CLASSIFIER_SYSTEM_PROMPT = """
You are an order-related classifier for a ceramics business assistant.

Analyse the customer message and return JSON with:
1. "intents" — array of objects, each with "tool" and "confidence"
2. "primary_tool" — the single strongest tool label

Available tools:
- returns_enquiry_tool — returns, refunds, exchanges, damaged or broken pieces
- shipping_enquiry_tool — shipping times, tracking, delivery, packaging
- custom_order_enquiry_tool — custom commissions or bespoke pieces

CONFIDENCE: high | medium | low
Include every tool that applies to ANY part of the message (medium or high only).
Omit tools with low confidence.

EXAMPLES:

"I want to return my order and place a new custom one"
→ {
    "intents": [
      {"tool": "returns_enquiry_tool", "confidence": "high"},
      {"tool": "custom_order_enquiry_tool", "confidence": "high"}
    ],
    "primary_tool": "returns_enquiry_tool"
  }

"How long does shipping take?"
→ {
    "intents": [{"tool": "shipping_enquiry_tool", "confidence": "high"}],
    "primary_tool": "shipping_enquiry_tool"
  }

"Return this mug and how much is shipping?"
→ {
    "intents": [
      {"tool": "returns_enquiry_tool", "confidence": "high"},
      {"tool": "shipping_enquiry_tool", "confidence": "high"}
    ],
    "primary_tool": "returns_enquiry_tool"
  }

Return ONLY valid JSON. No markdown.
""".strip()


def _extract_text(response: Any) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "").strip()
    return ""


def fallback_order_tools(user_text: str) -> List[str]:
    text = user_text.lower()
    tools: List[str] = []
    if any(
        word in text
        for word in (
            "return",
            "refund",
            "exchange",
            "damaged",
            "damage",
            "broken",
            "crack",
            "chipped",
            "defect",
        )
    ):
        tools.append("returns_enquiry_tool")
    if any(
        word in text
        for word in ("shipping", "delivery", "ship", "tracking", "dispatch")
    ):
        tools.append("shipping_enquiry_tool")
    if any(
        word in text
        for word in ("custom", "commission", "bespoke", "made to order")
    ):
        tools.append("custom_order_enquiry_tool")
    if not tools:
        tools.append("shipping_enquiry_tool")
    return tools


def detect_order_tools(
    user_text: str,
    messages: Optional[list] = None,
) -> Tuple[List[str], Dict[str, str], str]:
    """Return (tools to run, tool -> confidence, primary_tool)."""
    classifier_messages = list(messages) if messages else []
    if not classifier_messages or classifier_messages[-1].get("content") != user_text:
        classifier_messages.append({"role": "user", "content": user_text})

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            system=CLASSIFIER_SYSTEM_PROMPT,
            messages=classifier_messages,
            temperature=0.0,
            extra_headers=helicone_headers(
                handler="order_tool_classifier",
                intent="orders",
            ),
        )
    except Exception as exc:
        print(f"[order tool fallback] Classifier failed: {exc}")
        fallback = fallback_order_tools(user_text)
        return fallback, {tool: "high" for tool in fallback}, fallback[0]

    raw = _extract_text(response)
    try:
        data = json.loads(strip_code_fence(raw))
        raw_intents = data.get("intents", [])
        primary = str(data.get("primary_tool", "")).strip().lower()

        confidence_map: Dict[str, str] = {}
        valid: List[str] = []
        for entry in raw_intents:
            if not isinstance(entry, dict):
                continue
            tool = str(entry.get("tool", "")).strip().lower()
            confidence = str(entry.get("confidence", "low")).lower()
            if tool in _VALID_ORDER_TOOLS:
                confidence_map[tool] = confidence
            if (
                tool in _VALID_ORDER_TOOLS
                and confidence in ("high", "medium")
                and tool not in valid
            ):
                valid.append(tool)

        if not valid:
            fallback = fallback_order_tools(user_text)
            return fallback, {tool: "high" for tool in fallback}, fallback[0]

        if primary not in valid:
            primary = valid[0]

        return valid, confidence_map, primary

    except Exception as exc:
        print(f"[order tool fallback] Classifier parse failed: {exc}", flush=True)
        print(f"[order tool fallback] raw: {raw[:200]!r}", flush=True)
        fallback = fallback_order_tools(user_text)
        return fallback, {tool: "high" for tool in fallback}, fallback[0]


def _outcome_to_orders_dict(outcome: HandlerOutcome) -> dict:
    return {
        "status": outcome.get("status", "answered"),
        "message": str(outcome.get("message") or ""),
        "missing_slot": outcome.get("missing_slot"),
        "clarifying_question": outcome.get("clarifying_question"),
    }


def _run_order_tool(
    tool: str,
    user_text: str,
    messages: Optional[list],
) -> HandlerOutcome:
    handler = ROUTE_HANDLERS[tool]
    raw = handler(user_query=user_text, messages=messages)
    return normalize_handler_outcome(raw)


def _synthesize_mixed_reply(
    user_text: str,
    messages: Optional[list],
    answered: Dict[str, HandlerOutcome],
    blocked: Dict[str, HandlerOutcome],
) -> str:
    body = ""
    if answered:
        if len(answered) == 1:
            body = str(next(iter(answered.values())).get("message") or "").strip()
        else:
            body = synthesize_answers(user_text, answered)

    question = merge_clarifying_questions(user_text, messages, blocked)
    if body and question:
        return f"{body}\n\n{question}"
    return body or question


def _synthesize_order_answers(
    user_text: str,
    answered: Dict[str, HandlerOutcome],
) -> str:
    if len(answered) == 1:
        return str(next(iter(answered.values())).get("message") or "").strip()
    return synthesize_answers(user_text, answered)


def orders(user_text: str, messages: Optional[list] = None) -> dict:
    tools, confidence_map, primary_tool = detect_order_tools(user_text, messages)

    print(f"Order tools: {tools}")
    print(f"Order confidence: {confidence_map}")
    print(f"Order primary: {primary_tool}")

    if len(tools) == 1:
        return _outcome_to_orders_dict(
            _run_order_tool(tools[0], user_text, messages)
        )

    outcomes: Dict[str, HandlerOutcome] = {}
    for tool in tools:
        label = confidence_map.get(tool, "medium")
        print(f"Running {tool} ({label} confidence)")
        try:
            outcomes[tool] = _run_order_tool(tool, user_text, messages)
        except Exception as exc:
            outcomes[tool] = {
                "status": "answered",
                "message": f"[Could not retrieve {tool} info: {exc}]",
                "missing_slot": None,
                "clarifying_question": None,
            }

    human = {
        tool: outcome
        for tool, outcome in outcomes.items()
        if outcome.get("status") == "needs_human"
    }
    if human:
        parts = [
            str(outcome.get("message") or "").strip()
            for outcome in human.values()
            if str(outcome.get("message") or "").strip()
        ]
        if len(parts) > 1:
            combined = _synthesize_order_answers(user_text, human)
        else:
            combined = parts[0] if parts else ""
        return _outcome_to_orders_dict({
            "status": "needs_human",
            "message": combined,
            "missing_slot": None,
            "clarifying_question": None,
        })

    blocked = {
        tool: outcome
        for tool, outcome in outcomes.items()
        if outcome.get("status") == "needs_clarification"
    }
    answered = {
        tool: outcome
        for tool, outcome in outcomes.items()
        if outcome.get("status") == "answered"
        and str(outcome.get("message") or "").strip()
    }

    if blocked and answered:
        combined = _synthesize_mixed_reply(user_text, messages, answered, blocked)
        return _outcome_to_orders_dict({
            "status": "needs_clarification",
            "message": "",
            "missing_slot": "order_details",
            "clarifying_question": combined,
        })

    if blocked:
        if len(blocked) == 1:
            return _outcome_to_orders_dict(next(iter(blocked.values())))
        question = merge_clarifying_questions(user_text, messages, blocked)
        return _outcome_to_orders_dict({
            "status": "needs_clarification",
            "message": "",
            "missing_slot": "order_details",
            "clarifying_question": question,
        })

    if answered:
        body = _synthesize_order_answers(user_text, answered)
        return _outcome_to_orders_dict({
            "status": "answered",
            "message": body,
            "missing_slot": None,
            "clarifying_question": None,
        })

    return _outcome_to_orders_dict({
        "status": "needs_clarification",
        "message": "",
        "missing_slot": "order_details",
        "clarifying_question": (
            "Could you share a bit more about what you need help with "
            "regarding your order?"
        ),
    })
