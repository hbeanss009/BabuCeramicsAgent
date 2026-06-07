# eval/run_eval.py
import csv
import sys
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_judge_criteria import judge

_QUERY_KEYS = (
    "query",
    "question",
    "user_question",
    "user question",
    "input",
    "prompt",
    "customer_query",
)
_RESPONSE_KEYS = (
    "response",
    "reply",
    "output",
    "answer",
    "agent_response",
    "ai_answer",
    "ai answer",
)


def _resolve_filepath(filepath: str) -> Path:
    path = Path(filepath).expanduser()
    if path.is_file():
        return path.resolve()
    evals_candidate = Path(__file__).parent / filepath
    if evals_candidate.is_file():
        return evals_candidate.resolve()
    raise FileNotFoundError(f"CSV not found: {filepath}")


def _field(row: Dict[str, str], keys: Tuple[str, ...]) -> Optional[str]:
    for key in keys:
        norm_key = key.strip().lower().replace(" ", "_")
        value = row.get(norm_key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def load_csv(filepath: str) -> List[Dict[str, Any]]:
    """Load query and response pairs from a CSV file."""
    path = _resolve_filepath(filepath)
    rows: List[Dict[str, Any]] = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"{path.name} has no header row.")

        for i, row in enumerate(reader, start=1):
            normalized = {
                (key or "").strip().lower().replace(" ", "_"): (value or "")
                for key, value in row.items()
            }
            query = _field(normalized, _QUERY_KEYS)
            response = _field(normalized, _RESPONSE_KEYS)
            if not query or not response:
                raise ValueError(
                    f"{path.name} row {i}: need query/response columns. "
                    f"Found headers: {list(reader.fieldnames)}"
                )
            rows.append({
                "id":       i,
                "query":    query,
                "response": response,
            })
    return rows


def _result_fieldnames(rows: List[Dict[str, Any]]) -> List[str]:
    """Union of all keys across rows, with id/query/response first."""
    preferred = ("id", "query", "response")
    all_keys: set[str] = set()
    for row in rows:
        all_keys.update(row.keys())
    ordered = [key for key in preferred if key in all_keys]
    ordered.extend(sorted(all_keys - set(ordered)))
    return ordered


def run(filepath: str):
    golden_set = load_csv(filepath)
    results: List[Dict[str, Any]] = []

    if not golden_set:
        print("No rows found in CSV.")
        return

    print(f"Loaded {len(golden_set)} rows from {filepath}\n")

    for row in golden_set:
        print(f"Judging test {row['id']}: {row['query'][:50]}...")
        scores = judge(row["query"], row["response"])
        results.append({
            "id":       row["id"],
            "query":    row["query"],
            "response": row["response"],
            **scores
        })

    # Save to CSV (union of keys — judge JSON can vary per row)
    input_path = _resolve_filepath(filepath)
    today = date.today().isoformat()
    output_path = input_path.parent / f"judge_results_{today}.csv"
    fieldnames = _result_fieldnames(results)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDone — results saved to {output_path} ({len(fieldnames)} columns)")


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        filepath = sys.argv[1].strip()
    else:
        filepath = input("Enter path to CSV file: ").strip()

    if not filepath:
        print("No file specified.")
        print("Usage: python evals/run_eval.py path/to/your_file.csv")
        sys.exit(1)

    run(filepath)
