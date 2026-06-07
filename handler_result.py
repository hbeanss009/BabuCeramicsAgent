from __future__ import annotations

import re
from typing import Any, Literal, Optional, Tuple, TypedDict

from utils.style_sample import sanitize_customer_output

HandlerStatus = Literal["answered", "needs_clarification", "needs_human"]


class HandlerOutcome(TypedDict, total=False):
    status: HandlerStatus
    message: str
    missing_slot: Optional[str]
    clarifying_question: Optional[str]


class RouterResult(TypedDict):
    reply: Optional[str]
    needs_human_review: bool


def _sanitize_outcome(outcome: HandlerOutcome) -> HandlerOutcome:
    message = str(outcome.get("message") or "")
    question = str(outcome.get("clarifying_question") or "")
    if message:
        outcome = {**outcome, "message": sanitize_customer_output(message)}
    if question:
        outcome = {
            **outcome,
            "clarifying_question": sanitize_customer_output(question),
        }
    return outcome


def needs_human_outcome() -> HandlerOutcome:
    return {
        "status": "needs_human",
        "message": "",
        "missing_slot": None,
        "clarifying_question": None,
    }


def answered_outcome(message: str) -> HandlerOutcome:
    return _sanitize_outcome({
        "status": "answered",
        "message": message,
        "missing_slot": None,
        "clarifying_question": None,
    })


def clarification_outcome(question: str, missing_slot: str) -> HandlerOutcome:
    return _sanitize_outcome({
        "status": "needs_clarification",
        "message": "",
        "missing_slot": missing_slot,
        "clarifying_question": question,
    })


_CLARIFY_HINTS = (
    "could you",
    "can you share",
    "would you share",
    "which collection",
    "which piece",
    "which item",
    "double-check",
    "share the item",
    "share which",
    "bit more about",
    "looking for a gift",
    "for your own space",
)

_SLOT_FROM_MESSAGE = (
    (("which collection you're asking", "share which collection"), "collection_name"),
    (("collection", "spring", "fall"), "catalog_collection"),
    (("bowl", "mug", "vase", "plate", "type of piece"), "catalog_category"),
    (("item name", "piece", "which item", "which piece", "share the item"), "item_name"),
    (("gift", "budget", "style", "occasion", "own space"), "recommendation_context"),
    (("shipping", "return", "refund", "custom order", "order number"), "order_details"),
)


def _infer_missing_slot(message: str) -> str:
    lower = message.lower()
    for keywords, slot in _SLOT_FROM_MESSAGE:
        if any(kw in lower for kw in keywords):
            return slot
    return "details"


def _looks_like_clarifying_question(message: str) -> bool:
    if not message.strip():
        return False
    lower = message.lower()
    if "?" in message:
        return any(hint in lower for hint in _CLARIFY_HINTS) or len(message) < 400
    return any(hint in lower for hint in _CLARIFY_HINTS)


def outcome_from_complete_message(
    complete: bool,
    message: str,
    *,
    missing_slot: str = "order_details",
) -> HandlerOutcome:
    """Map LLM {complete, message} JSON to Format B."""
    if complete:
        return needs_human_outcome()
    text = message.strip()
    if _looks_like_clarifying_question(text):
        return clarification_outcome(text, missing_slot)
    return answered_outcome(text)


def _explicit_outcome(result: dict) -> Optional[HandlerOutcome]:
    status = result.get("status")
    if status not in ("answered", "needs_clarification", "needs_human"):
        return None
    message = str(result.get("message") or "").strip()
    missing_slot = result.get("missing_slot")
    clarifying_question = str(result.get("clarifying_question") or "").strip() or None
    if status == "needs_clarification" and not clarifying_question and message:
        clarifying_question = message
        message = ""
    return {
        "status": status,
        "message": message,
        "missing_slot": missing_slot or (
            _infer_missing_slot(clarifying_question or "") if status == "needs_clarification" else None
        ),
        "clarifying_question": clarifying_question,
    }


def normalize_handler_outcome(result: Any) -> HandlerOutcome:
    """Map handler output to answered / needs_clarification / needs_human."""
    if isinstance(result, dict):
        explicit = _explicit_outcome(result)
        if explicit:
            return _sanitize_outcome(explicit)

        if "needs_human_review" in result:
            needs_review = bool(result["needs_human_review"])
            text = str(result.get("reply") or result.get("message") or "").strip()
            if needs_review and not text:
                return needs_human_outcome()
            if needs_review:
                return _sanitize_outcome({
                    "status": "needs_human",
                    "message": text,
                    "missing_slot": None,
                    "clarifying_question": None,
                })
            if text and _looks_like_clarifying_question(text):
                return clarification_outcome(text, _infer_missing_slot(text))
            return answered_outcome(text)

        if "complete" in result:
            complete = bool(result.get("complete"))
            message = str(result.get("message", "")).strip()
            clarifying_question = str(result.get("clarifying_question") or "").strip()

            if complete and not message:
                return needs_human_outcome()
            if complete:
                return _sanitize_outcome({
                    "status": "needs_human",
                    "message": message,
                    "missing_slot": None,
                    "clarifying_question": None,
                })
            if clarifying_question or _looks_like_clarifying_question(message):
                question = clarifying_question or message
                return clarification_outcome(
                    question,
                    str(result.get("missing_slot") or _infer_missing_slot(question)),
                )
            return answered_outcome(message)

    text = str(result).strip() if result is not None else ""
    if not text:
        return needs_human_outcome()
    return answered_outcome(text)


def normalize_handler_result(result: Any) -> Tuple[Optional[str], bool]:
    """
    Unify tool outputs into (customer_reply, needs_human_review).
    Handler message is preserved for logging; as_router_result drops reply when flagged.
    """
    outcome = normalize_handler_outcome(result)
    status = outcome.get("status", "answered")
    message = str(outcome.get("message") or "").strip()
    question = str(outcome.get("clarifying_question") or "").strip()

    if status == "needs_human":
        return (message or None), True
    if status == "needs_clarification":
        return (question or message or None), False
    return (message or None), False


def as_router_result(result: Any) -> RouterResult:
    reply, needs_human_review = normalize_handler_result(result)
    if reply:
        reply = sanitize_customer_output(reply)
    if needs_human_review:
        return {"reply": None, "needs_human_review": True}
    return {"reply": reply, "needs_human_review": False}


def clarification_only(result: Any) -> bool:
    outcome = normalize_handler_outcome(result)
    return outcome.get("status") == "needs_clarification"


def extract_html_suffix(message: str) -> str:
    """Return trailing HTML fragments (e.g. product images) from a handler message."""
    if not message or "<" not in message:
        return ""
    idx = message.find("<p><img")
    if idx == -1:
        idx = message.find("<p><strong>")
    if idx == -1:
        return ""
    return message[idx:].strip()
