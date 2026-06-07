from __future__ import annotations

_FRUSTRATION_PHRASES = (
    "terrible",
    "disappointed",
    "unacceptable",
    "unhappy",
    "frustrated",
    "upset",
    "really angry",
    "so angry",
    "poor taste",
    "bad collections",
)

_ORDER_PROBLEM_PHRASES = (
    "wrong item",
    "incorrect item",
    "not what i ordered",
    "received the wrong",
    "got the wrong",
    "broken",
    "smashed",
    "cracked",
    "chipped",
    "shattered",
    "defective",
    "damaged",
    "didn't arrive",
    "did not arrive",
    "never arrived",
    "never received",
    "hasn't arrived",
    "has not arrived",
    "only received one",
    "only received",
    "missing from my order",
    "missing item",
    "want a refund",
    "full refund",
    "refund immediately",
    "speak to someone",
    "talk to someone",
)

# Store operations, finances, production secrets, launch schedules, credentials.
_BUSINESS_DETAIL_PHRASES = (
    "secret",
    "revenue",
    "profit",
    "margin",
    "% margin",
    "wholesale",
    "sell to retailers",
    "running the store",
    "running your store",
    "how long have you been running",
    "design process",
    "design ideas",
    "design inspiration",
    "where do you get your design",
    "where do you get your inspiration",
    "how often do you launch",
    "launch new collection",
    "going to be released",
    "when is your next item",
    "next item going to be released",
    "release date",
    "upcoming release",
    "admin email",
    "admin password",
    "account password",
    "email and password",
    "how much sales",
    "sales do you make",
    "make annually",
    "how many orders do you get",
    "orders do you get every",
    "cost to make",
    "cost you to make",
    "how much does it cost you to make",
    "how long does it take to make",
    "take to make an item",
    "how long have you been",
    "business model",
    "account details",
)


def is_business_details_question(query: str) -> bool:
    """True when the customer asks about internal business or operations."""
    lower = query.lower()
    return any(phrase in lower for phrase in _BUSINESS_DETAIL_PHRASES)


def should_flag_for_human_review(query: str) -> bool:
    """Deterministic pre-check matching HUMAN REVIEW rules in tool prompts."""
    lower = query.lower()
    if any(phrase in lower for phrase in _FRUSTRATION_PHRASES):
        return True
    if any(phrase in lower for phrase in _ORDER_PROBLEM_PHRASES):
        return True
    if is_business_details_question(query):
        return True
    return False


_DISCOUNT_PHRASES = (
    "discount",
    "discounted",
    "lower the price",
    "lower price",
    "reduce the price",
    "reduce price",
    "cheaper",
    "price match",
    "coupon",
    "promo code",
    "promotion",
    "bulk discount",
    "buy in bulk",
    "negotiate",
    "best price",
    "special price",
    "can you drop the price",
)


def is_discount_question(query: str) -> bool:
    """True when the customer is asking for a discount or price negotiation."""
    lower = query.lower()
    return any(phrase in lower for phrase in _DISCOUNT_PHRASES)
