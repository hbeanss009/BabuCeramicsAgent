# evals/llm_judge_hallucination.py
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client_config import client, MODEL
from context_builder import TOOL_SOURCE_MAP, fetch_all_agent_sources

_QUERY_KEYS = ("query", "question", "input", "prompt", "customer_query")
_RESPONSE_KEYS = ("response", "reply", "output", "answer", "agent_response")

HALLUCINATION_JUDGE_PROMPT = """
You are verifying whether an AI customer service agent's response for Babu Ceramics
is factually grounded in the provided source documents.

The agent routes customer queries to one or more tools. Each tool may only state
facts found in its authorized source tables. A synthesized reply may combine
outputs from multiple tools — check every factual claim against ALL sources provided.

Tool → authorized sources:
- item_inquiry (item details): items, care_guides, collection_stories
  → item names, prices, materials, dimensions, care instructions, collection context
- collection_inquiry: items, collection_stories, faqs, artist_notes
  → collection stories, browse listings, categories, item names and prices shown in browse results
- recommendation: items, collection_stories, editorial_picks
  → recommended item names, prices, styles, occasions, editorial gift picks
- returns_enquiry_tool: faqs, artist_notes
  → return/refund/damage policies and procedures
- shipping_enquiry_tool: faqs, artist_notes
  → shipping times, costs, regions, delivery policies
- custom_order_enquiry_tool: faqs, artist_notes
  → custom order process, timelines, requirements, studio practices

Your job:
1. Read the source documents and tool map carefully
2. Read the customer query and the agent's response
3. Identify any factual claim in the response that is NOT supported by the sources
4. Return your verdict

A claim is a hallucination if:
- It states a fact not present in any source document
- It contradicts a fact in the source documents
- It invents item names, prices, materials, collections, policies, care rules,
  shipping details, return rules, or custom-order timelines not in the sources
- It recommends or describes items not in the items or editorial_picks sources

A claim is NOT a hallucination if:
- It is a reasonable inference directly supported by the sources
- It is a stylistic rephrasing of a source fact without adding new facts
- It is a general pleasantry, greeting, or Olivia's tone with no factual claim
- It defers to the customer, asks a clarifying question, or flags for human review
  without inventing facts

Ignore HTML, image placeholders, and email sign-offs unless they contain factual claims.

Return ONLY valid JSON:
{
  "hallucinations_found": true or false,
  "hallucinated_claims": ["claim 1", "claim 2"],
  "explanation": "one sentence summary"
}
"""


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


def _parse_json_response(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"hallucinations_found": None, "error": "Judge returned invalid JSON", "raw": raw}


def _build_judge_context(sources: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "tool_source_map": {
                tool: list(tables) for tool, tables in TOOL_SOURCE_MAP.items()
            },
            "sources": sources,
        },
        ensure_ascii=False,
        indent=2,
    )


def judge_hallucination(query: str, response: str, sources: dict) -> dict:
    """
    Run LLM-as-judge on a query/response pair against all agent source documents.
    Returns hallucination verdict and extracted claims.
    """
    result = client.messages.create(
        model=MODEL,
        max_tokens=500,
        temperature=0.0,
        system=HALLUCINATION_JUDGE_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Customer query:\n{query}\n\n"
                f"Agent response:\n{response}\n\n"
                f"Agent tool map and source documents:\n"
                f"{_build_judge_context(sources)}"
            ),
        }],
    )

    raw = next(
        (
            getattr(block, "text", "")
            for block in result.content
            if getattr(block, "type", None) == "text"
        ),
        "{}",
    ).strip()

    return _parse_json_response(raw)


def load_csv(filepath: str) -> List[Dict[str, Any]]:
    """Load query/response pairs from a CSV file."""
    path = _resolve_filepath(filepath)
    rows: List[Dict[str, Any]] = []

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
            response = _field(normalized, _RESPONSE_KEYS)

            if not query or not response:
                raise ValueError(
                    f"{path.name} row {i}: need query and response columns. "
                    f"Found headers: {list(reader.fieldnames)}"
                )

            rows.append({
                "id": i,
                "query": query,
                "response": response,
            })

    return rows


def _result_fieldnames(rows: List[Dict[str, Any]]) -> List[str]:
    preferred = (
        "id",
        "query",
        "response",
        "hallucinations_found",
        "hallucinated_claims",
        "explanation",
        "error",
        "raw",
    )
    all_keys: set[str] = set()
    for row in rows:
        all_keys.update(row.keys())
    ordered = [key for key in preferred if key in all_keys]
    ordered.extend(sorted(all_keys - set(ordered)))
    return ordered


def _format_row_for_csv(row: Dict[str, Any]) -> Dict[str, Any]:
    formatted = dict(row)
    claims = formatted.get("hallucinated_claims")
    if isinstance(claims, list):
        formatted["hallucinated_claims"] = " | ".join(str(c) for c in claims)
    return formatted


def run(filepath: str) -> bool:
    rows = load_csv(filepath)
    if not rows:
        print("No rows found in CSV.")
        return False

    print(f"\n── Hallucination Detection Eval ({Path(filepath).name}) ─────────")
    print(f"Loaded {len(rows)} rows")
    print("Grounding against all agent tools and source tables:")
    for tool, tables in TOOL_SOURCE_MAP.items():
        print(f"  {tool}: {', '.join(tables)}")
    print()

    sources = fetch_all_agent_sources()
    results: List[Dict[str, Any]] = []
    passed = 0

    for row in rows:
        query = row["query"]
        response = row["response"]

        print(f"Judging row {row['id']}: {query[:55]}...")
        verdict = judge_hallucination(query, response, sources)

        hallucinated = verdict.get("hallucinations_found")
        has_error = verdict.get("error") is not None or hallucinated is None
        ok = hallucinated is False and not has_error
        status = "✅" if ok else "❌"

        print(f"{status} {query[:55]}")
        print(f"   {verdict.get('explanation', verdict.get('error', ''))}")
        if hallucinated and verdict.get("hallucinated_claims"):
            for claim in verdict["hallucinated_claims"]:
                print(f"   ⚠️  Hallucinated: {claim}")

        passed += ok
        results.append({
            "id": row["id"],
            "query": query,
            "response": response,
            **verdict,
        })

    print(f"\nResult: {passed}/{len(rows)} grounded (no hallucinations)")

    input_path = _resolve_filepath(filepath)
    today = date.today().isoformat()
    output_path = input_path.parent / f"hallucination_results_{today}.csv"
    fieldnames = _result_fieldnames(results)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(_format_row_for_csv(r) for r in results)

    print(f"Results saved to {output_path}")
    return passed == len(rows)


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        csv_path = sys.argv[1].strip()
    else:
        csv_path = input("Enter path to hallucination eval CSV: ").strip()

    if not csv_path:
        print("No file specified.")
        print("Usage: python evals/llm_judge_hallucination.py path/to/your_file.csv")
        sys.exit(1)

    try:
        success = run(csv_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    sys.exit(0 if success else 1)
