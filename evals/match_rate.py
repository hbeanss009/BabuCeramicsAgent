# eval/match_rate.py
import csv
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

CRITERIA = [
    "tone_accuracy",
    "completeness",
    "clarifying_question_quality",
    "recommendation_quality",
    "context_retention",
]

LABEL_MAP = {
    "great":          "great",
    "good":           "great",
    "average":        "average",
    "bad":            "bad",
    "n/a":            "n/a",
    "not applicable": "n/a",
    "":               "n/a",
}


def normalise(label: str) -> str:
    return LABEL_MAP.get(label.lower().strip(), "n/a")


def is_na_output(text: str) -> bool:
    """True when the agent response is missing or not evaluable."""
    if not text or not text.strip():
        return True
    lower = text.strip().lower()
    if lower in ("n/a", "na"):
        return True
    if "flagged for human review" in lower:
        return True
    if "connection issue" in lower or "hit a connection issue" in lower:
        return True
    return False


def score_to_num(score: str) -> int:
    return {"great": 2, "average": 1, "bad": 0, "n/a": -1}.get(score, -1)


_QUERY_KEYS = ("query", "user_question", "question", "user question")
_RESPONSE_KEYS = ("response", "ai_answer", "answer", "ai answer")

_CRITERIA_KEYS: Dict[str, Tuple[str, ...]] = {
    "tone_accuracy": (
        "tone_accuracy",
        "tone accuracy",
    ),
    "completeness": ("completeness",),
    "clarifying_question_quality": (
        "clarifying_question_quality",
        "clarifying questions quality",
    ),
    "recommendation_quality": (
        "recommendation_quality",
        "recommendation quality",
    ),
    "context_retention": (
        "context_retention",
        "context retention",
    ),
}


def _resolve_filepath(filepath: str) -> Path:
    path = Path(filepath).expanduser()
    if path.is_file():
        return path.resolve()
    evals_candidate = Path(__file__).parent / filepath
    if evals_candidate.is_file():
        return evals_candidate.resolve()
    raise FileNotFoundError(f"File not found: {filepath}")


def _normalize_row(row: Dict[str, str]) -> Dict[str, str]:
    """Strip headers and values; map 'Tone accuracy ' → 'tone_accuracy'."""
    normalized: Dict[str, str] = {}
    for key, value in row.items():
        norm_key = (key or "").strip().lower().replace(" ", "_")
        normalized[norm_key] = (value or "").strip()
    return normalized


def _field(row: Dict[str, str], keys: Tuple[str, ...]) -> str:
    for key in keys:
        norm_key = key.strip().lower().replace(" ", "_")
        value = row.get(norm_key)
        if value:
            return value
    return ""


def load_judge_results(filepath: str) -> Dict[int, Dict[str, str]]:
    results: Dict[int, Dict[str, str]] = {}
    path = _resolve_filepath(filepath)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            normalized = _normalize_row(row)
            results[i] = {
                "response": _field(normalized, _RESPONSE_KEYS),
                **{
                    criterion: normalise(
                        _field(normalized, _CRITERIA_KEYS[criterion]) or "n/a"
                    )
                    for criterion in CRITERIA
                },
            }
    return results


def load_golden_set(filepath: str) -> Dict[int, Dict[str, Any]]:
    golden: Dict[int, Dict[str, Any]] = {}
    path = _resolve_filepath(filepath)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            normalized = _normalize_row(row)
            golden[i] = {
                "query": _field(normalized, _QUERY_KEYS),
                "response": _field(normalized, _RESPONSE_KEYS),
                "human": {
                    criterion: normalise(
                        _field(normalized, _CRITERIA_KEYS[criterion]) or "n/a"
                    )
                    for criterion in CRITERIA
                },
            }
    return golden


def get_inputs() -> Tuple[str, str]:
    """Prompt user for file paths."""
    print("\n── Match Rate Calculator ────────────────────────────")
    print("Enter the paths to your two CSV files.\n")

    while True:
        judge_path = input("Path to judge results CSV (from run_eval.py): ").strip()
        try:
            _resolve_filepath(judge_path)
            break
        except FileNotFoundError:
            print(f"  ❌ File not found: {judge_path}. Try again.")

    while True:
        golden_path = input("Path to Human labels CSV  ").strip()
        try:
            _resolve_filepath(golden_path)
            break
        except FileNotFoundError:
            print(f"  ❌ File not found: {golden_path}. Try again.")

    return judge_path, golden_path


def calculate_match_rate(
    judge_filepath:  str,
    golden_filepath: str
) -> dict:
    llm_results = load_judge_results(judge_filepath)
    golden_set  = load_golden_set(golden_filepath)

    total_checks  = 0
    total_matches = 0

    criteria_checks  = {c: 0 for c in CRITERIA}
    criteria_matches = {c: 0 for c in CRITERIA}

    row_results = []

    for i, golden_row in golden_set.items():
        llm_row = llm_results.get(i, {})

        response = llm_row.get("response") or golden_row.get("response", "")
        if is_na_output(response):
            continue

        all_na = all(v == "n/a" for v in golden_row["human"].values())
        if all_na:
            continue

        row_checks  = 0
        row_matches = 0
        row_detail  = {
            "id":    i,
            "query": golden_row["query"][:60]
        }

        for criterion in CRITERIA:
            human_label = golden_row["human"].get(criterion, "n/a")
            llm_label   = llm_row.get(criterion, "n/a")

            if human_label == "n/a" or llm_label == "n/a":
                row_detail[criterion] = "n/a"
                continue

            match = score_to_num(human_label) == score_to_num(llm_label)

            criteria_checks[criterion]  += 1
            criteria_matches[criterion] += int(match)
            total_checks                += 1
            total_matches               += int(match)
            row_checks                  += 1
            row_matches                 += int(match)

            row_detail[criterion] = (
                f"✅ {human_label}" if match
                else f"❌ human={human_label} llm={llm_label}"
            )

        if row_checks == 0:
            continue

        row_detail["row_match_rate"] = f"{round(row_matches / row_checks * 100, 1)}%"
        row_results.append(row_detail)

    overall = (
        round(total_matches / total_checks * 100, 1)
        if total_checks > 0 else None
    )

    per_criteria = {
        criterion: (
            round(criteria_matches[criterion] / criteria_checks[criterion] * 100, 1)
            if criteria_checks[criterion] > 0 else None
        )
        for criterion in CRITERIA
    }

    return {
        "overall_match_rate": overall,
        "total_checks":       total_checks,
        "total_matches":      total_matches,
        "per_criteria":       per_criteria,
        "row_results":        row_results,
    }


def print_results(results: dict):
    print("\n═" * 55)
    print("  MATCH RATE RESULTS")
    print("═" * 55)

    overall = results["overall_match_rate"]
    if overall is None:
        print("\n  Overall match rate: n/a (no comparable human labels found)")
    else:
        print(f"\n  Overall match rate: {overall}%")
    print(f"  Total checks:       {results['total_checks']}")
    print(f"  Total matches:      {results['total_matches']}")

    print(f"\n── Per Criteria ─────────────────────────────────────")
    for criterion, rate in results["per_criteria"].items():
        if rate is None:
            print(f"  — {criterion:<35} n/a")
        else:
            bar    = "█" * int(rate / 10)
            status = "✅" if rate >= 80 else "⚠️ " if rate >= 60 else "❌"
            print(f"  {status} {criterion:<33} {rate}% {bar}")

    print(f"\n── Per Row ──────────────────────────────────────────")
    for row in results["row_results"]:
        print(f"\n  Test {row['id']}: {row['query']}")
        for criterion in CRITERIA:
            if criterion in row and row[criterion] != "n/a":
                print(f"    {criterion:<35} {row[criterion]}")
        print(f"    {'row match rate':<35} {row['row_match_rate']}")


if __name__ == "__main__":
    judge_path, golden_path = get_inputs()
    results = calculate_match_rate(judge_path, golden_path)
    print_results(results)