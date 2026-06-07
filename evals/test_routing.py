# evals/test_routing.py
import csv
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import detect_routed_intents
from orders import detect_order_tools, fallback_order_tools

_QUERY_KEYS = ("query", "question", "user_question", "user question", "input", "prompt")
_SUITE_KEYS = ("suite", "test_suite", "section", "type")
_INTENT_KEYS = (
    "expected_intent",
    "expected intent",
    "intent",
    "golden_intent",
    "expected",
)
_TOOLS_KEYS = (
    "expected_tools",
    "expected tools",
    "tools",
    "golden_tools",
    "order_tools",
)
_LLM_KEYS = ("use_llm", "use llm", "llm")


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


def _parse_bool(raw: Optional[str], default: bool = True) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in ("true", "yes", "1", "y"):
        return True
    if value in ("false", "no", "0", "n"):
        return False
    raise ValueError(f"Invalid boolean value {raw!r}. Use true/false or 1/0.")


def _parse_csv_list(raw: Optional[str]) -> List[str]:
    """Parse comma/pipe/semicolon-separated values; strips optional [ ] wrappers."""
    if not raw:
        return []
    text = raw.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    for sep in ("|", ";"):
        text = text.replace(sep, ",")
    return [
        part.strip().strip("'\"")
        for part in text.split(",")
        if part.strip().strip("'\"")
    ]


def _parse_tools(raw: Optional[str]) -> List[str]:
    return _parse_csv_list(raw)


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
            suite = (_field(normalized, _SUITE_KEYS) or "top_level").lower()
            expected_intents = _parse_csv_list(_field(normalized, _INTENT_KEYS))
            expected_tools = _parse_tools(_field(normalized, _TOOLS_KEYS))
            use_llm = _parse_bool(_field(normalized, _LLM_KEYS), default=True)

            if not query:
                raise ValueError(
                    f"{path.name} row {i}: missing query column. "
                    f"Found headers: {list(reader.fieldnames)}"
                )

            if suite in ("top_level", "intent", "intents"):
                if not expected_intents:
                    raise ValueError(
                        f"{path.name} row {i}: top_level suite needs expected_intent."
                    )
            elif suite in ("order_tools", "orders", "order"):
                if not expected_tools:
                    raise ValueError(
                        f"{path.name} row {i}: order_tools suite needs expected_tools."
                    )
            else:
                raise ValueError(
                    f"{path.name} row {i}: unknown suite {suite!r}. "
                    "Use top_level or order_tools."
                )

            cases.append({
                "id": i,
                "query": query,
                "suite": suite,
                "expected_intents": expected_intents,
                "expected_tools": expected_tools,
                "use_llm": use_llm,
            })

    return cases


def _run_case(case: Dict[str, Any]) -> Tuple[bool, Any, Any]:
    query = case["query"]
    suite = case["suite"]

    if suite in ("top_level", "intent", "intents"):
        actual, _, _ = detect_routed_intents(query)
        expected = case["expected_intents"]
        ok = set(actual) == set(expected)
        return ok, expected, actual

    if case["use_llm"]:
        actual, _, _ = detect_order_tools(query)
    else:
        actual = fallback_order_tools(query)
    expected = case["expected_tools"]
    ok = set(actual) == set(expected)
    return ok, expected, actual


def run(filepath: str) -> bool:
    test_cases = load_test_cases(filepath)
    if not test_cases:
        print(f"No test cases found in {filepath}")
        return False

    passed = 0
    total = len(test_cases)

    print(f"\n── Routing Eval ({Path(filepath).name}) ─────────────────")
    print("Compares routed intents (handlers that would run) against CSV.\n")

    for case in test_cases:
        query = case["query"]
        ok, expected, actual = _run_case(case)

        if case["suite"] in ("top_level", "intent", "intents"):
            label = f"intent={expected}"
        else:
            mode = "LLM" if case["use_llm"] else "fallback"
            label = f"tools={', '.join(expected)} ({mode})"

        status = "✅" if ok else "❌"
        print(f"{status} [{label}] {query[:55]}")
        if not ok:
            print(f"   Expected: {expected}")
            print(f"   Got:      {actual}")
        passed += ok

    print(f"\nResult: {passed}/{total} passed")
    return passed == total


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        csv_path = sys.argv[1].strip()
    else:
        csv_path = input("Enter path to routing test CSV: ").strip()

    if not csv_path:
        print("No file specified.")
        print("Usage: python evals/test_routing.py path/to/routing_cases.csv")
        sys.exit(1)

    try:
        success = run(csv_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    sys.exit(0 if success else 1)
