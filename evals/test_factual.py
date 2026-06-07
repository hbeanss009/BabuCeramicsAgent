# evals/test_factual.py
import csv
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import run_router

VALID_MATERIALS = ["Stoneware", "Earthenware", "Porcelain"]

_QUERY_KEYS = ("query", "question", "user_question", "user question", "input", "prompt")
_RESPONSE_KEYS = ("response", "reply", "output", "answer", "agent_response", "expected_response")
_ITEM_KEYS = ("item_name", "item", "expected_item", "item mention", "item_mention")
_PRICE_KEYS = ("expected_price", "price", "expected price")
_MATERIAL_KEYS = ("expected_material", "material", "expected material")


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


def extract_price(response: str) -> Optional[str]:
    match = re.search(r"\$[\d,]+(?:\.\d{2})?", response)
    return match.group(0) if match else None


def price_amount(price_str: Optional[str]) -> Optional[str]:
    """Dollar amount digits only, e.g. '68' from '$68.00'."""
    if not price_str:
        return None
    match = re.search(r"\$(\d[\d,]*)(?:\.\d{2})?", price_str)
    if not match:
        return None
    return match.group(1).replace(",", "")


def materials_in(response: str) -> List[str]:
    return [m for m in VALID_MATERIALS if m.lower() in response.lower()]


def item_mentioned(response: str, item_name: str) -> bool:
    return item_name.lower() in response.lower()


def _build_checks(
    golden_response: str,
    item_name: Optional[str],
    expected_price: Optional[str],
    expected_material: Optional[str],
) -> List[Tuple[str, Callable[[str], bool]]]:
    """Build checks that compare run_router output against the golden CSV response."""
    checks: List[Tuple[str, Callable[[str], bool]]] = []

    price_digits = (expected_price or "").lstrip("$").split(".")[0]
    if not price_digits:
        price_digits = price_amount(extract_price(golden_response))

    if price_digits:
        checks.append((
            f"price matches golden (${price_digits})",
            lambda actual, p=price_digits: price_amount(extract_price(actual)) == p,
        ))

    materials: List[str] = []
    if expected_material:
        materials = [expected_material]
    else:
        materials = materials_in(golden_response)

    for material in materials:
        checks.append((
            f"material matches golden ({material})",
            lambda actual, mat=material: mat.lower() in actual.lower(),
        ))

    if item_name:
        checks.append((
            f"item mentioned (matches golden: {item_name})",
            lambda actual, name=item_name: (
                item_mentioned(actual, name) and item_mentioned(golden_response, name)
            ),
        ))

    return checks


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
            golden_response = _field(normalized, _RESPONSE_KEYS)
            item_name = _field(normalized, _ITEM_KEYS)
            expected_price = _field(normalized, _PRICE_KEYS)
            expected_material = _field(normalized, _MATERIAL_KEYS)

            if not query:
                raise ValueError(
                    f"{path.name} row {i}: missing query column. "
                    f"Found headers: {list(reader.fieldnames)}"
                )
            if not golden_response:
                raise ValueError(
                    f"{path.name} row {i}: missing response column (golden expected reply)."
                )
            if expected_material and expected_material not in VALID_MATERIALS:
                raise ValueError(
                    f"{path.name} row {i}: expected_material must be one of "
                    f"{VALID_MATERIALS}, got {expected_material!r}."
                )

            checks = _build_checks(
                golden_response, item_name, expected_price, expected_material
            )
            if not checks:
                raise ValueError(
                    f"{path.name} row {i}: could not derive any factual checks from "
                    "the golden response. Add expected_price, expected_material, or "
                    "item_name, or include a price/material in the response text."
                )

            cases.append({
                "id": i,
                "query": query,
                "golden_response": golden_response,
                "checks": checks,
            })

    return cases


def run(filepath: str) -> bool:
    test_cases = load_test_cases(filepath)
    if not test_cases:
        print(f"No test cases found in {filepath}")
        return False

    passed = 0
    total = 0

    print(f"\n── Factual Accuracy Eval ({Path(filepath).name}) ─────────────────")
    print("Compares run_router() output against golden response in CSV.\n")

    for case in test_cases:
        query = case["query"]
        golden = case["golden_response"]
        checks = case["checks"]
        result = run_router(query)
        actual = result.get("reply") or ""

        print(f"\n  Query: {query[:55]}")

        for check_name, check_fn in checks:
            total += 1
            ok = check_fn(actual)
            status = "✅" if ok else "❌"
            print(f"  {status} {check_name}")
            if not ok:
                print(f"     Golden price:   {extract_price(golden)}")
                print(f"     Actual price:   {extract_price(actual)}")
                print(f"     Golden material:{materials_in(golden) or '—'}")
                print(f"     Actual material:{materials_in(actual) or '—'}")
                print(f"     Golden preview: {golden[:120]}")
                print(f"     Actual preview: {actual[:120]}")
            passed += ok

    print(f"\nResult: {passed}/{total} passed")
    return passed == total


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        csv_path = sys.argv[1].strip()
    else:
        csv_path = input("Enter path to factual test CSV: ").strip()

    if not csv_path:
        print("No file specified.")
        print("Usage: python evals/test_factual.py path/to/factual_cases.csv")
        sys.exit(1)

    try:
        success = run(csv_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    sys.exit(0 if success else 1)
