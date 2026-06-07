# eval/gen_hallu_agent_outputs.py
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_ground_truth import build_ground_truth
from main import run_router

EVALS_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = EVALS_DIR / "hallucination_inputs.csv"


def generate() -> None:
    """
    Generate hallucination test inputs from Supabase ground truth.
    Fetches queries from build_ground_truth, runs each through the agent,
    and saves query + expected + output to CSV.
    """
    print("[gen_hallu_agent_outputs] Loading test cases from Supabase...")
    ground_truth = build_ground_truth()

    if not ground_truth:
        print("❌ No test cases found")
        return

    print(f"✅ Loaded {len(ground_truth)} test cases\n")

    rows = []
    for i, row in enumerate(ground_truth, start=1):
        query    = row.get("query", "").strip()
        expected = row.get("expected", "").strip()

        if not query:
            print(f"  [{i}] SKIPPED — empty query")
            continue

        print(f"  [{i}] {query[:55]}...")

        try:
            result = run_router(query)
            output = result.get("reply") or ""
        except Exception as exc:
            print(f"      ❌ Agent call failed: {exc}")
            output = ""

        rows.append({
            "query":    query,
            "expected": expected,
            "output":   output,
        })

    # Write results to CSV
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["query", "expected", "output"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✅ Saved {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    generate()