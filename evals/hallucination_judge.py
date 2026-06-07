# eval/hallucination_judge.py

import json
import sys
import os
import csv
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client_config import client, MODEL

JUDGE_PROMPT = """
You are comparing a submitted answer to an expert answer on a given question.

[BEGIN DATA]
************
[Question]: {query}
************
[Expert answer]: {expected}
************
[Submitted answer]: {output}
************
[END DATA]

Compare the factual content of the submitted answer with the expert answer.
Ignore any differences in style, grammar, tone, or punctuation.

IMPORTANT — perspective and voice:
The submitted answer is often written in first person by Olivia (the shop owner), while the expert
answer may refer to her in third person. Treat these as factually equivalent when the underlying
claim is the same — do NOT mark as disagreement (D) based on perspective alone.
Examples of equivalent phrasing:
- "I will review your return" = "Olivia will review your return"
- "I can let you know" = "Olivia can let you know"
- "my studio" = "Olivia's studio"
- "me personally" = "Olivia personally"

The submitted answer may either be a subset or superset of the expert answer,
or it may conflict with it. Determine which case applies.

Select one of the following options:
(A) The submitted answer is a subset of the expert answer and is fully consistent with it.
    Example: expert says price is $68 and material is stoneware.
             submitted says price is $68 only. Consistent but incomplete.

(B) The submitted answer is a superset with accurate additional details.
    Example: expert says $68, earthenware. Submitted adds "hand wash only" which is correct.
             Extra information that is CONSISTENT and ACCURATE = acceptable elaboration.

(C) The submitted answer contains all the same details as the expert answer.
    Example: submitted matches expert on all key facts.

(D) There is a disagreement between the submitted answer and the expert answer.
    Example: expert says $68, submitted says $75. Direct contradiction — hallucination.
    NOT a disagreement: first person vs third person (e.g. "I will" vs "Olivia will").

(E) The answers differ but these differences don't matter from the perspective of factuality.
    Example: submitted paraphrases the expert answer differently but all facts are correct.
    Example: expert says "Olivia will review it"; submitted says "I will review it" — same fact.

Return ONLY valid JSON — no markdown, no explanation outside JSON.
Put choice first. Keep reasoning to 1-3 sentences.
{{
  "choice": "A|B|C|D|E",
  "reasoning": "brief explanation"
}}
""".strip()

CHOICE_SCORES = {
    "A": 0.5,   # subset — consistent but incomplete
    "B": 1.0,   # superset with accurate details — good elaboration
    "C": 1.0,   # complete match — perfect
    "D": 0.0,   # disagreement — hallucination
    "E": 1.0,   # different phrasing, factually equivalent
}

CHOICE_LABELS = {
    "A": "Subset — consistent but incomplete",
    "B": "Superset with accurate details — good elaboration",
    "C": "Complete match",
    "D": "Disagreement — hallucination",
    "E": "Different phrasing, factually equivalent",
}

OUTCOME_TYPES = {
    "A": "Partial",
    "B": "Accurate",
    "C": "Accurate",
    "D": "Hallucination",
    "E": "Accurate",
}


def _parse_judge_response(raw: str) -> dict:
    """Parse judge response JSON, handling markdown code fences and malformed JSON."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    choice_match = re.search(r'"choice"\s*:\s*"([A-E])"', cleaned, re.IGNORECASE)
    if choice_match:
        choice = choice_match.group(1).upper()
        reasoning = ""
        reasoning_match = re.search(
            r'"reasoning"\s*:\s*"(.*)"\s*\}?\s*$',
            cleaned,
            re.DOTALL | re.IGNORECASE,
        )
        if reasoning_match:
            reasoning = reasoning_match.group(1).replace("\\n", "\n").strip()
        return {"choice": choice, "reasoning": reasoning}

    raise json.JSONDecodeError("Could not parse judge JSON", cleaned, 0)


def judge_hallucination(query: str, expected: str, output: str) -> dict:
    """
    Run hallucination judge on one query/expected/output triple.
    Returns choice, score, and reasoning.
    """
    prompt = JUDGE_PROMPT.format(
        query=query,
        expected=expected,
        output=output
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as exc:
        print(f"      ❌ Judge call failed: {exc}", flush=True)
        return {
            "choice":    "ERROR",
            "score":     0.0,
            "label":     "Judge call failed",
            "reasoning": str(exc),
        }

    raw = next(
        (
            getattr(block, "text", "")
            for block in response.content
            if getattr(block, "type", None) == "text"
        ),
        "{}",
    ).strip()

    try:
        data   = _parse_judge_response(raw)
        choice = str(data.get("choice", "")).upper().strip()
        if choice not in CHOICE_SCORES:
            return {
                "choice":    "ERROR",
                "score":     0.0,
                "label":     "Parse error",
                "reasoning": f"Invalid choice: {choice!r}",
            }
        return {
            "choice":    choice,
            "score":     CHOICE_SCORES.get(choice, 0.0),
            "label":     CHOICE_LABELS.get(choice, "Unknown"),
            "reasoning": str(data.get("reasoning", "")),
        }
    except json.JSONDecodeError:
        return {
            "choice":    "ERROR",
            "score":     0.0,
            "label":     "Parse error",
            "reasoning": raw[:500],
        }


def run(filepath: str) -> None:
    """
    Run hallucination eval on a CSV with columns: query, expected, output.
    """
    rows = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("No rows found in CSV")
        return

    results       = []
    total         = len(rows)
    skipped       = 0
    choice_counts = {k: 0 for k in CHOICE_LABELS}

    print(f"\n── Hallucination Eval ({total} cases) ───────────────────", flush=True)

    for i, row in enumerate(rows, start=1):
        query    = row.get("query", "").strip()
        expected = row.get("expected", "").strip()
        output   = row.get("output", "").strip()

        if not output:
            print(f"\nTest {i}: SKIPPED — no agent output", flush=True)
            skipped += 1
            continue

        print(f"\nTest {i}: {query[:55]}...", flush=True)
        verdict = judge_hallucination(query, expected, output)

        choice = verdict["choice"]
        score  = verdict["score"]
        label  = verdict["label"]

        if score == 1.0:
            status = "✅"
        elif score == 0.5:
            status = "⚠️ "
        else:
            status = "❌"

        if choice in choice_counts:
            choice_counts[choice] += 1

        print(f"  {status} {choice} — {label}", flush=True)
        print(f"     {verdict['reasoning'][:120]}...", flush=True)

        results.append({
            "query":     query,
            "expected":  expected,
            "output":    output[:100],
            "choice":    choice,
            "score":     score,
            "label":     label,
            "reasoning": verdict["reasoning"],
        })

    # Summary — rates use judged count so outcome buckets sum to 100%
    judged       = sum(choice_counts.values())
    skipped_rate = (skipped / total * 100) if total > 0 else 0

    type_counts = {"Accurate": 0, "Partial": 0, "Hallucination": 0}
    for choice, count in choice_counts.items():
        outcome = OUTCOME_TYPES.get(choice)
        if outcome:
            type_counts[outcome] += count

    print(f"\n── Summary ──────────────────────────────────────────", flush=True)
    print(f"  Judged: {judged}/{total}  |  Skipped: {skipped} ({skipped_rate:.1f}%)", flush=True)

    print(f"\n  By outcome type:", flush=True)
    for outcome in ("Accurate", "Partial", "Hallucination"):
        count = type_counts[outcome]
        pct   = (count / judged * 100) if judged > 0 else 0
        print(f"    {outcome:<14} {count:>2}  ({pct:5.1f}%)", flush=True)

    print(f"\n  By category:", flush=True)
    for choice in CHOICE_LABELS:
        count = choice_counts[choice]
        pct   = (count / judged * 100) if judged > 0 else 0
        outcome = OUTCOME_TYPES[choice]
        label   = CHOICE_LABELS[choice]
        print(f"    {choice} [{outcome:<13}] {count:>2}  ({pct:5.1f}%)  {label}", flush=True)

    # Save results
    output_path = filepath.replace(".csv", "_results.csv")
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys() if results else [])
        if results:
            writer.writeheader()
            writer.writerows(results)
    print(f"\nResults saved to {output_path}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        filepath = input("Path to hallucination inputs CSV: ").strip()
    else:
        filepath = sys.argv[1]
    run(filepath)