# evals/test_flagging.py
import csv
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import run_router

_QUERY_KEYS = ("query", "question", "user_question", "user question", "input", "prompt")
_RESPONSE_KEYS = ("response", "reply", "output", "answer", "agent_response", "expected_response")
_FLAG_KEYS = (
    "should_flag",
    "should flag",
    "needs_human_review",
    "needs human review",
    "flag",
    "expected_flag",
    "expected",
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
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _parse_should_flag(raw: str, row_num: int, filename: str) -> bool:
    value = raw.strip().lower()
    if value in ("true", "yes", "1", "y", "flag"):
        return True
    if value in ("false", "no", "0", "n", "handle"):
        return False
    raise ValueError(
        f"{filename} row {row_num}: invalid flag value {raw!r}. "
        "Use true/false, yes/no, flag/handle, or 1/0."
    )


def _field_or_empty(row: Dict[str, str], keys: Tuple[str, ...]) -> str:
    for key in keys:
        if key in row:
            return str(row[key]).strip()
    return ""


def load_test_cases(filepath: str) -> List[Dict[str, Any]]:
    path = _resolve_filepath(filepath)
    cases: List[Dict[str, Any]] = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"{path.name} has no header row.")

        for i, row in enumerate(reader, start=1):
            normalized = {
                (key or "").strip().lower(): (value or "")
                for key, value in row.items()
            }
            query = _field(normalized, _QUERY_KEYS)
            golden_response = _field_or_empty(normalized, _RESPONSE_KEYS)
            flag_raw = _field(normalized, _FLAG_KEYS)

            if not query:
                raise ValueError(
                    f"{path.name} row {i}: missing query column. "
                    f"Found headers: {list(reader.fieldnames)}"
                )
            if flag_raw is None:
                raise ValueError(
                    f"{path.name} row {i}: missing needs_human_review / should_flag column."
                )

            cases.append({
                "id": i,
                "query": query,
                "golden_response": golden_response,
                "should_flag": _parse_should_flag(flag_raw, i, path.name),
            })

    return cases


def _reply_matches_golden(golden: str, actual: str) -> bool:
    if not golden.strip():
        return True
    if not actual.strip():
        return False
    g = golden.strip().lower()
    a = actual.strip().lower()
    if g in a or a in g:
        return True
    return g[:40] in a


def run(filepath: str) -> bool:
    test_cases = load_test_cases(filepath)
    if not test_cases:
        print(f"No test cases found in {filepath}")
        return False

    passed = 0
    total = 0

    print(f"\n── Flagging Eval ({Path(filepath).name}) ─────────────────")
    print("Compares run_router() output against golden CSV expectations.\n")

    for case in test_cases:
        query = case["query"]
        golden = case["golden_response"]
        should_flag = case["should_flag"]

        result = run_router(query)
        actual_flagged = result.get("needs_human_review", False)
        actual = result.get("reply") or ""

        total += 1
        flag_ok = actual_flagged == should_flag

        reply_ok = True
        if not should_flag and golden:
            reply_ok = _reply_matches_golden(golden, actual)

        ok = flag_ok and reply_ok
        status = "✅" if ok else "❌"
        label = "FLAG" if should_flag else "HANDLE"

        print(f"{status} [{label}] {query[:55]}")
        if not flag_ok:
            print(f"   Expected needs_human_review={should_flag}, got {actual_flagged}")
        if not reply_ok:
            print(f"   Golden preview: {golden[:120] or '(empty)'}")
            print(f"   Actual preview: {actual[:120] or '(empty)'}")
        passed += ok

    print(f"\nResult: {passed}/{total} passed")
    return passed == total


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        csv_path = sys.argv[1].strip()
    else:
        csv_path = input("Enter path to flagging test CSV: ").strip()

    if not csv_path:
        print("No file specified.")
        print("Usage: python evals/test_flagging.py path/to/flagging_cases.csv")
        sys.exit(1)

    try:
        success = run(csv_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    sys.exit(0 if success else 1)
