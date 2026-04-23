import warnings
warnings.filterwarnings("ignore")

import json
import os
from contextlib import nullcontext
from typing import Any, cast

import pandas as pd
from phoenix.client import Client as PhoenixClient
from phoenix.client.types.spans import SpanQuery
from tqdm import tqdm

try:
    from openinference.instrumentation import suppress_tracing
except Exception:
    # Fallback when openinference package is unavailable.
    def suppress_tracing():  # type: ignore[no-redef]
        return nullcontext()

try:
    # Available in some Phoenix versions / environments.
    from phoenix.evals import llm_classify, OpenAIModel
except Exception:
    llm_classify = None
    OpenAIModel = None

PROJECT_NAME = "Evaluating-babu-ceramics-agent"
os.environ["PHOENIX_PROJECT_NAME"] = PROJECT_NAME

import main
from main import run_router


#evaluating if the correct tool was called by the route handler.
AGENT_TOOL_EVAL_CASES = [
    {
        "user_query": "What are the collections available?",
        "expected_tool_name": "view_collection",
    },
    {
        "user_query": "Show me all the items available in Dot collection",
        "expected_tool_name": "view_catalog_items",
    },
    {
        "user_query": "What is the price of pasta bowl?",
        "expected_tool_name": "get_item_price",
    },
]


LLM_TOOL_EVAL_PROMPT = """
You are evaluating whether the selected tool for a user query is correct.

User query: {user_query}
Expected tool: {expected_tool_name}
Selected tool: {tool_name}

Return one label:
- correct: selected tool matches the expected tool for the user query.
- incorrect: selected tool does not match the expected tool.
"""


def _extract_tool_name(output_value: Any) -> str:
    if output_value is None:
        return ""
    if isinstance(output_value, dict):
        return str(output_value.get("tool_name", "")).strip().lower()

    raw = str(output_value).strip()
    if not raw:
        return ""

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return str(parsed.get("tool_name", "")).strip().lower()
    except Exception:
        pass
    return raw.lower()


def run_agent_cases() -> None:
    batch_span_ctx = (
        main.tracer.start_as_current_span(
            "agent_tool_eval_batch",
            openinference_span_kind="chain",
        )
        if main.tracer is not None
        else nullcontext()
    )

    with batch_span_ctx:
        for case in tqdm(AGENT_TOOL_EVAL_CASES, desc="Running agent-tool eval"):
            try:
                run_router(case["user_query"])
            except Exception as exc:
                print(f"Router call failed for: {case['user_query']}")
                print(exc)


def fetch_agent_tool_spans() -> pd.DataFrame:
    query = (
        SpanQuery()
        .where("span_kind == 'AGENT' and name == 'item_inquiry'")
        .select("input.value", "output.value")
        .rename(input_value="user_query", output_value="tool_name_raw")
    )

    try:
        spans_df = PhoenixClient().spans.get_spans_dataframe(
            query=cast(Any, query),
            project_name=PROJECT_NAME,
            timeout=None,
        )
    except Exception as exc:
        print(f"Failed to query AGENT spans from Phoenix: {exc}")
        return pd.DataFrame({"user_query": [], "tool_name": []})

    if spans_df.empty:
        return pd.DataFrame({"user_query": [], "tool_name": []})

    spans_df = spans_df.copy()
    spans_df["tool_name"] = spans_df["tool_name_raw"].apply(_extract_tool_name)
    spans_df = spans_df[spans_df["user_query"].notna()][["user_query", "tool_name"]]
    return cast(pd.DataFrame, spans_df)


def evaluate_agent_tool_selection_with_llm() -> pd.DataFrame:
    spans_df = fetch_agent_tool_spans()
    expected_df = pd.DataFrame(AGENT_TOOL_EVAL_CASES)
    eval_df = expected_df.merge(spans_df, on="user_query", how="left")
    eval_df["tool_name"] = eval_df["tool_name"].fillna("")

    if llm_classify is None or OpenAIModel is None:
        print("Phoenix eval LLM helpers are unavailable. Returning merged dataframe only.")
        eval_df["label"] = ""
        eval_df["score"] = 0
        return eval_df

    with suppress_tracing():
        llm_eval = llm_classify(
            dataframe=eval_df[["user_query", "expected_tool_name", "tool_name"]],
            template=LLM_TOOL_EVAL_PROMPT,
            rails=["correct", "incorrect"],
            model=OpenAIModel(),
            provide_explanation=True,
        )

    llm_eval["score"] = llm_eval["label"].apply(lambda x: 1 if x == "correct" else 0)
    return llm_eval


if __name__ == "__main__":
    run_agent_cases()
    results = evaluate_agent_tool_selection_with_llm()
    print(results.to_string(index=False))
