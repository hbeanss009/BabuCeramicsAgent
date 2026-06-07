#!/usr/bin/env python3
"""Run run_router for a batch of test queries and print structured results."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import run_router

QUERIES_RAW = r"""
How much is the Rain Song Vase?
My order arrived completely broken, I'm really upset
I'd like to place a custom order for 2 mugs in sage green
Tell me about the Spring collection
Can I put the Robin's Call Mug in the dishwasher?
I love the Rain Song Vase, it's so beautiful
How much is the Citrus Zest Plate and can I put it in the dishwasher?
What material is the Brook Whisper Bowl and what collection is it from?
How long does shipping take and do you ship internationally?
Tell me about the Rain Song Vase and suggest something similar under $60
I'd like a custom order for 2 mugs — how long will it take and how much will it cost?
What's your returns policy and how do I start a return?
I want something nice
I need a gift
I want something for my home
Something boho for my room under $100
I need a housewarming gift under $70
Something earthy and natural for my living room shelf
I'm looking for a gift for my mum who loves gardening
Turn 1: I want something nice / Turn 2: For my living room
Something boho and earthy for my shelf
Something minimalist and clean for my desk
Something warm and cosy for my kitchen
I need a housewarming gift around $70
A wedding gift for a couple who love cooking
Something under $50
I want to splash out, something special around $90
I need a dinner set for entertaining
Turn 1: Tell me about the Rain Song Vase / Turn 2: Does it come in other sizes?
Turn 1: I'm looking for something for a boho room / Turn 2: What about something for under $50?
Turn 1: I'd like to place a custom order / Turn 2: 2 bowls in terracotta, needed by end of August
Turn 1: Tell me about the Spring collection / Turn 2: Which piece would you recommend for a gift?
Turn 1: Something boho under $100 / Turn 2: I like it but want something with more colour
Turn 1: How much is the Copperleaf Vase? / Turn 2: Is it dishwasher safe?
Turn 1: I want something for my mum's birthday / Turn 2: She loves nature and earthy things, budget around $70
Something nice for my friend
I need a dinner set and what's your returns policy?
Turn 1: Suggest something boho / Turn 2: What about something under $50?
Tell me about the Rain Song Vase and suggest something similar but cheaper
I'd like 2 custom mugs in sage green, needed by July, here's my inspiration: [link]
""".strip()


def parse_cases(raw: str) -> list:
    cases = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(
            r"Turn\s*1:\s*(.+?)\s*/\s*Turn\s*2:\s*(.+)",
            line,
            re.IGNORECASE,
        )
        if m:
            cases.append({
                "label": line[:80],
                "turns": [m.group(1).strip(), m.group(2).strip()],
            })
        else:
            cases.append({"label": line, "turns": [line]})
    return cases


def strip_html(text: str) -> str:
    if not text:
        return ""
    plain = re.sub(r"<[^>]+>", " ", text)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain


def main() -> None:
    cases = parse_cases(QUERIES_RAW)
    print(f"Running {len(cases)} cases ({sum(len(c['turns']) for c in cases)} turns)...\n")

    for i, case in enumerate(cases, 1):
        print("=" * 80)
        print(f"[{i}/{len(cases)}] {case['label']}")
        print("=" * 80)

        messages = []
        for t, turn in enumerate(case["turns"], 1):
            if len(case["turns"]) > 1:
                print(f"\n--- Turn {t} ---")
                print(f"User: {turn}")

            result = run_router(turn, messages if messages else None)
            flagged = result.get("needs_human_review", False)
            reply = result.get("reply")

            if flagged:
                out = "[FLAGGED FOR HUMAN REVIEW — no auto-reply]"
            elif reply:
                out = strip_html(reply)
                if len(out) > 2000:
                    out = out[:2000] + "..."
            else:
                out = "[No reply generated]"

            print(f"Human review: {flagged}")
            print(f"Olivia: {out}")

            messages.append({"role": "user", "content": turn})
            if reply and not flagged:
                messages.append({"role": "assistant", "content": strip_html(reply)})

        print()


if __name__ == "__main__":
    main()
