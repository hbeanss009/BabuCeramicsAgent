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

import json
import os
from html import escape
import subprocess
import sys
import warnings

import collection_inquiry_tool
import item_details_tool

warnings.filterwarnings("ignore")
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional, Tuple

load_dotenv(Path(__file__).resolve().parent / ".env")

import orders
import recommendation
from client_config import MODEL, client
from flask import Flask, request
from conversation_store import create_conversation, generate_thread_id
from email_util import send_customer_reply, send_enquiry_to_owner
from handler_result import RouterResult, as_router_result
from utils.helicone import helicone_headers
from utils.llm_json import strip_code_fence
from utils.style_sample import CONTACT_INFO_RULE, NO_EM_DASH_RULE, sanitize_customer_output

warnings.filterwarnings("ignore")
_listener_proc = None


def start_gmail_listener_worker() -> None:
    global _listener_proc

    if _listener_proc is not None and _listener_proc.poll() is None:
        return

    project_root   = Path(__file__).resolve().parent
    script         = project_root / "gmail_listener.py"
    _listener_proc = subprocess.Popen(
        [sys.executable, str(script)],
        cwd=str(project_root),
        env=os.environ.copy()
    )
    print(f"Started gmail_listener.py (pid {_listener_proc.pid})", flush=True)


app = Flask(__name__)

ROUTE_HANDLERS = {
    "item_inquiry":       item_details_tool.item_details_tool,
    "collection_inquiry": collection_inquiry_tool.collection_inquiry,
    "recommendation":     recommendation.recommendation,
    "orders":             orders.orders,
}

INTENT_ALIASES = {
    "catalog":      "collection_inquiry",
    "catalog_tool": "collection_inquiry",
}

# Map qualitative labels to routing behaviour
CONFIDENCE_ROUTING = {
    "high":   "run",
    "medium": "run",
    "low":    "skip",
}


# ── Classifier prompt ──────────────────────────────────────────────────────

CLASSIFIER_SYSTEM_PROMPT = """
You are a classifier for a ceramics business assistant.

Analyse the customer message and return a JSON object with three fields:

1. "intents" — array of objects, each with intent and confidence label
2. "named_item" — specific catalog item name if mentioned, else null
3. "primary_intent" — the single strongest intent

Available intents:
- "item_inquiry"       — customer names a SPECIFIC catalog item
- "recommendation"     — customer wants suggestions, style match, gift ideas
- "collection_inquiry" — customer wants to browse items/collections OR asks
                         about a collection's story, mood, or aesthetic
- "orders"             — shipping, returns, custom orders

CONFIDENCE LABELS — assign one of three:
   high   → clear, unambiguous signal for this intent
   medium → present but alongside other stronger signals
   low    → weak or incidental signal, likely not what customer wants

ONLY include intents with medium or high confidence.
Omit intents with low confidence entirely.

PRIORITY RULES:

1. If query contains style/mood/occasion context (boho, minimalist, earthy,
   for my room, as a gift) alongside browsing language (show me, do you have)
   → recommendation gets high, collection_inquiry gets low or omitted

2. "suggest/recommend + collection name as filter" → recommendation HIGH
   The collection name is context, not a browse request.
   e.g. "suggest a mug from the Spring collection" → recommendation only

3. "show me the [collection]" / "what's in the [collection]" → collection_inquiry HIGH
   Browse language with a specific collection name = browse intent.

4. "I need/I'm looking for/I want + item type" → recommendation HIGH not collection_inquiry
   Functional set requests (dinner set, matching pieces) → recommendation HIGH

5. Named specific item anywhere in query → item_inquiry HIGH alongside primary.
   Always extract the item name into named_item.

ITEM INQUIRY DETECTION:
These phrases always signal item_inquiry HIGH when a specific named item follows:
- "tell me about [item]", "how much is [item]", "what material is [item]"
- "I love [item]", "details about [item]", "what is [item]"

RECOMMENDATION SIGNALS — recommend immediately, no question needed:
- Style words: boho, minimalist, earthy, cosy, rustic, natural, colourful
- Budget: under $100, around $50, affordable, splash out
- Occasion: gift, housewarming, wedding, birthday, thank you
- Recipient: my mum, a friend who cooks, my partner
- Room: living room, bedroom, kitchen, shelf, mantelpiece
- Item type with suggestion language: suggest a vase, I need a bowl
- Emotion: calming, joyful, peaceful, bold, luxurious
- Colour/texture: earthy tones, sage green, matte, speckled
- Use case: display, everyday use, flowers, serving
- Size: small, large, compact, statement piece
- Season: wintery, summery, autumnal, spring-inspired
- Negative preference: not too colourful, nothing too rustic
- Existing pieces/interior: goes with my Rain Song Vase, linen and wood

EXAMPLES:

"something boho for my room under $100"
→ {"intents": [{"intent": "recommendation", "confidence": "high"}],
   "named_item": null, "primary_intent": "recommendation"}

"show me all the bowls you have"
→ {"intents": [{"intent": "collection_inquiry", "confidence": "high"}],
   "named_item": null, "primary_intent": "collection_inquiry"}

"tell me about the Spring collection"
→ {"intents": [{"intent": "collection_inquiry", "confidence": "high"}],
   "named_item": null, "primary_intent": "collection_inquiry"}

"something boho for my room, show me some bowls"
→ {"intents": [{"intent": "recommendation", "confidence": "high"}],
   "named_item": null, "primary_intent": "recommendation"}

"Can you suggest a mug, something from the Spring collection maybe?"
→ {"intents": [{"intent": "recommendation", "confidence": "high"}],
   "named_item": null, "primary_intent": "recommendation"}

"how much is the Rain Song Vase?"
→ {"intents": [{"intent": "item_inquiry", "confidence": "high"}],
   "named_item": "Rain Song Vase", "primary_intent": "item_inquiry"}

"tell me about the Rain Song Vase and show me other Spring pieces"
→ {"intents": [{"intent": "item_inquiry", "confidence": "high"},
               {"intent": "collection_inquiry", "confidence": "high"}],
   "named_item": "Rain Song Vase", "primary_intent": "item_inquiry"}

"tell me about the Rain Song Vase and what's your returns policy?"
→ {"intents": [{"intent": "item_inquiry", "confidence": "high"},
               {"intent": "orders", "confidence": "high"}],
   "named_item": "Rain Song Vase", "primary_intent": "item_inquiry"}

"how long does shipping take?"
→ {"intents": [{"intent": "orders", "confidence": "high"}],
   "named_item": null, "primary_intent": "orders"}

"I want something nice"
→ {"intents": [{"intent": "recommendation", "confidence": "medium"}],
   "named_item": null, "primary_intent": "recommendation"}

"I need a dinner set"
→ {"intents": [{"intent": "recommendation", "confidence": "high"}],
   "named_item": null, "primary_intent": "recommendation"}

"I need a housewarming gift, also what's your returns policy?"
→ {"intents": [{"intent": "recommendation", "confidence": "high"},
               {"intent": "orders", "confidence": "high"}],
   "named_item": null, "primary_intent": "recommendation"}

"Suggest something boho, show me the Spring collection, and how long does shipping take?"
→ {"intents": [{"intent": "recommendation", "confidence": "high"},
               {"intent": "collection_inquiry", "confidence": "high"},
               {"intent": "orders", "confidence": "high"}],
   "named_item": null, "primary_intent": "recommendation"}

Return ONLY valid JSON. No markdown. No explanation.
""".strip()


# ── Intent classification ──────────────────────────────────────────────────

def _normalize_intent_label(label: str) -> str:
    key = str(label).strip().lower()
    return INTENT_ALIASES.get(key, key)


def fallback_intent(user_text: str) -> list[str]:
    text = user_text.lower()
    intents = []
    if any(word in text for word in ("recommend", "suggest", "best", "gift")):
        intents.append("recommendation")
    if any(word in text for word in
           ("order", "shipping", "return", "refund", "delivery", "custom")):
        intents.append("orders")
    browse = any(
        phrase in text for phrase in (
            "show me", "what do you have", "do you have any",
            "what collections", "what's in the", "what is in the",
            "pieces in the", "all the bowls", "all the mugs", "all the vases",
        )
    )
    story = any(
        phrase in text for phrase in (
            "tell me about the spring", "tell me about the fall",
            "collection story", "mood of the", "aesthetic of the",
            "what inspired the",
        )
    )
    if browse or story:
        intents.append("collection_inquiry")
    if any(word in text for word in
           ("price", "material", "size", "weight", "how much")):
        intents.append("item_inquiry")
    return intents if intents else ["item_inquiry"]


def detect_intents(user_text: str) -> Tuple[list[str], dict[str, str], str]:
    """
    Classify user intent using Claude qualitative labels.
    Falls back to keyword matching if Claude fails.

    Returns:
    - list of valid intents (high or medium confidence)
    - dict of intent -> confidence label
    - primary intent string
    """
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            temperature=0.0,
            system=CLASSIFIER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text}],
            extra_headers=helicone_headers(
                handler="intent_classifier",
                intent="classification",
            ),
        )
    except Exception as exc:
        print(f"[classifier] Claude call failed: {exc}", flush=True)
        fallback = fallback_intent(user_text)
        return fallback, {i: "high" for i in fallback}, fallback[0]

    raw = next(
        (getattr(block, "text", "")
         for block in response.content
         if getattr(block, "type", None) == "text"),
        "",
    ).strip()

    print(f"[classifier] raw: {raw}", flush=True)

    try:
        data         = json.loads(strip_code_fence(raw))
        raw_intents  = data.get("intents", [])
        named_item   = data.get("named_item")
        primary      = _normalize_intent_label(str(data.get("primary_intent", "")))

        confidence_map: dict[str, str] = {}
        valid: list[str] = []

        for entry in raw_intents:
            if not isinstance(entry, dict):
                continue
            raw_label  = str(entry.get("intent", ""))
            label      = _normalize_intent_label(raw_label)
            confidence = str(entry.get("confidence", "low")).lower()
            if label:
                confidence_map[label] = confidence
            if (
                label in ROUTE_HANDLERS
                and CONFIDENCE_ROUTING.get(confidence, "skip") == "run"
                and not (label == "item_inquiry" and not named_item)
                and label not in valid
            ):
                valid.append(label)

        if named_item and "item_inquiry" in ROUTE_HANDLERS and "item_inquiry" not in valid:
            valid.insert(0, "item_inquiry")
            confidence_map["item_inquiry"] = "high"

        if not valid:
            fallback = fallback_intent(user_text)
            return fallback, {i: "high" for i in fallback}, fallback[0]

        if primary not in valid:
            primary = valid[0]

        print(
            f"[classifier] intents={valid} confidence={confidence_map} primary={primary}",
            flush=True,
        )
        return valid, confidence_map, primary

    except Exception as exc:
        print(f"[classifier] parse failed: {exc} raw={raw[:200]!r}", flush=True)
        fallback = fallback_intent(user_text)
        return fallback, {i: "high" for i in fallback}, fallback[0]


def resolve_routed_intents(
    intents: list[str],
    confidence_map: dict[str, str],
    primary_intent: str,
) -> list[str]:
    """Return intent labels whose handlers would actually run at runtime."""
    if len(intents) <= 1:
        return list(intents)

    all_high = all(
        confidence_map.get(intent, "medium") == "high"
        for intent in intents
    )
    primary_confidence = confidence_map.get(primary_intent, "medium")

    if not all_high and primary_confidence == "high":
        if primary_intent in intents:
            return [primary_intent]
        return [intents[0]]

    return list(intents)


def detect_routed_intents(user_text: str) -> Tuple[list[str], dict[str, str], str]:
    """Classify a query and return only intents that would be routed to."""
    intents, confidence_map, primary_intent = detect_intents(user_text)
    routed = resolve_routed_intents(intents, confidence_map, primary_intent)
    return routed, confidence_map, primary_intent


# ── Router ─────────────────────────────────────────────────────────────────

def run_multi_intent_handler(
    user_text: str,
    messages:  Optional[list] = None,
) -> RouterResult:

    intents, confidence_map, primary_intent = detect_intents(user_text)
    routed_intents = resolve_routed_intents(intents, confidence_map, primary_intent)

    print(f"Intents: {intents}", flush=True)
    print(f"Confidence: {confidence_map}", flush=True)
    print(f"Primary: {primary_intent}", flush=True)
    if routed_intents != intents:
        print(f"Routed: {routed_intents}", flush=True)

    if len(routed_intents) == 1:
        handler = ROUTE_HANDLERS[routed_intents[0]]
        return as_router_result(handler(user_text, messages))

    results:      dict[str, str] = {}
    needs_review: bool           = False

    for intent in routed_intents:
        handler = ROUTE_HANDLERS[intent]
        label   = confidence_map.get(intent, "medium")
        print(f"Running {intent} ({label} confidence)", flush=True)
        try:
            routed = as_router_result(handler(user_text, messages))
            if routed["needs_human_review"]:
                needs_review = True
            reply = routed.get("reply")
            if reply:
                results[intent] = reply
        except Exception as exc:
            print(f"[{intent}] handler error: {exc}", flush=True)
            results[intent] = f"[Could not retrieve {intent} info]"

    if needs_review:
        return {"reply": None, "needs_human_review": True}

    if not results:
        return {"reply": None, "needs_human_review": False}

    # Single result after running — no synthesis needed
    if len(results) == 1:
        only_reply = next(iter(results.values()))
        cleaned    = sanitize_customer_output(only_reply)
        return {"reply": cleaned or None, "needs_human_review": False}

    # Multiple results — synthesise into one reply
    combined_context = "\n\n".join(
        f"### {intent} ({confidence_map.get(intent, 'medium')} confidence):\n{result}"
        for intent, result in results.items()
    )

    synthesis_response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=f"""You are Olivia from Babu Ceramics.
Combine the following responses into one warm natural reply.
Do not repeat information. No headers or bullet points.
{CONTACT_INFO_RULE}
{NO_EM_DASH_RULE}""",
        messages=[{
            "role":    "user",
            "content": (
                f"User asked: {user_text}\n\n"
                f"Responses:\n\n{combined_context}\n\n"
                f"Write a single natural reply."
            )
        }],
        extra_headers=helicone_headers(
            handler="multi_intent_synthesis",
            intent="orchestration"
        ),
    )

    reply = next(
        (getattr(block, "text", "")
         for block in synthesis_response.content
         if getattr(block, "type", None) == "text"),
        "I wasn't able to generate a response.",
    )
    cleaned = sanitize_customer_output(reply.strip())
    return {"reply": cleaned or None, "needs_human_review": False}


def run_router(user_text: str, messages: Optional[list] = None) -> RouterResult:
    try:
        return run_multi_intent_handler(user_text, messages)
    except Exception as exc:
        print(f"[run_router error] {exc}", flush=True)
        return {
            "reply": (
                "I hit a connection issue while processing your request. "
                "Please retry in a moment."
            ),
            "needs_human_review": False,
        }


@app.get("/")
def show_form():
    form_path = Path(__file__).with_name("form.html")
    return form_path.read_text(encoding="utf-8")


@app.post("/ask")
def submit_form():
    name  = request.form["name"]
    email = request.form["email"]
    query = request.form["query"]
    print(f"New submission from {name} ({email}): {query}", flush=True)

    thread_id = generate_thread_id()
    routed    = run_router(query)
    needs_human_review = routed["needs_human_review"]
    reply     = routed.get("reply")

    messages = [{"role": "user", "content": query}]
    if reply:
        messages.append({"role": "assistant", "content": reply})

    if not create_conversation(
        thread_id=thread_id,
        email=email,
        name=name,
        initial_query=query,
        messages=messages,
        status="needs_human_review" if needs_human_review else "active",
    ):
        print(
            "[create_conversation] failed — run supabase_conversations_policies.sql "
            "in Supabase SQL Editor (RLS blocks anon INSERT)",
            flush=True,
        )

    if needs_human_review:
        send_enquiry_to_owner(
            name,
            email,
            query,
            thread_id=thread_id,
            reason="Form submission flagged for human review",
        )
        print(
            f"[human review] thread {thread_id} flagged — owner notified",
            flush=True,
        )

    if reply:
        if not send_customer_reply(
            to=email,
            subject=f"Re: Your Babu Ceramics enquiry [ref: {thread_id}]",
            body=reply,
        ):
            print("[send_customer_reply] failed — check terminal/logs", flush=True)

    safe_name = escape(name.strip()) if name and name.strip() else ""
    safe_email = escape(email)
    if safe_name:
        message = (
            f"Thanks for your enquiry, {safe_name}. "
            f"You will receive a reply to {safe_email}. "
            "If you don't see it within 24 hrs, please check your spam folder."
        )
    else:
        message = (
            f"Thanks for your enquiry. "
            f"You will receive a reply to {safe_email}. "
            "If you don't see it within 24 hrs, please check your spam folder."
        )

    confirmation_path = Path(__file__).with_name("confirmation.html")
    return confirmation_path.read_text(encoding="utf-8").replace(
        "{{MESSAGE}}", message
    )


if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_gmail_listener_worker()
    app.run(debug=True, host="127.0.0.1", port=5000)