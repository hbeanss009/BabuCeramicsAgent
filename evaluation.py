import os

# Set before importing phoenix so trace defaults and HTTP clients agree on the project.
PROJECT_NAME = "Evaluating-babu-ceramics-agent"
os.environ["PHOENIX_PROJECT_NAME"] = PROJECT_NAME
_PHOENIX_HTTP_HEADERS: dict[str, str] = {"project-name": PROJECT_NAME}

import warnings

warnings.filterwarnings("ignore")

import json
import re
from contextlib import nullcontext
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional, cast

import pandas as pd
import phoenix as px
from phoenix.client import Client as PhoenixClient
from phoenix.client.types.spans import SpanQuery
from phoenix.evals import (
    NOT_PARSABLE,
    AnthropicModel,
    QA_PROMPT_RAILS_MAP,
    QA_PROMPT_TEMPLATE,
    TOOL_CALLING_PROMPT_TEMPLATE,
    TOOL_CALLING_PROMPT_RAILS_MAP,
    llm_classify,
)
from phoenix.trace import SpanEvaluations
from tqdm import tqdm

from client_config import MODEL
from tools_registry import TOOLS

_phoenix_rest_client = PhoenixClient(headers=_PHOENIX_HTTP_HEADERS)
_phoenix_session_client = px.Client(headers=_PHOENIX_HTTP_HEADERS, warn_if_server_not_running=False)

import main  # noqa: E402
from main import run_router  # noqa: E402

TOOL_PROMPT_TEMPLATE = TOOL_CALLING_PROMPT_TEMPLATE
INTENT_LABEL_PROMPT_TEMPLATE = QA_PROMPT_TEMPLATE
RUN_ROUTER_QA_PROMPT_TEMPLATE = QA_PROMPT_TEMPLATE

# Classification rails for each TOOL eval (separate lists - do not alias or share references).
TOOL_CORRECTNESS_LLM_RAILS = list(TOOL_CALLING_PROMPT_RAILS_MAP.values())
TOOL_TONE_LLM_RAILS = list(TOOL_CALLING_PROMPT_RAILS_MAP.values())

# Only appended when building the TOOL_TONE prompt for llm_classify; never applied to TOOL_CORRECTNESS.
TOOL_TONE_EVAL_LLM_LABEL_SUFFIX = """
For automated evaluation, after your EXPLANATION, your final LABEL must be exactly one word:
"correct" if the answer's tone adequately matches Olivia's writing style (warm, friendly, on-brand enough to ship),
"incorrect" if the tone is clearly off-brand, chilly, or not Olivia-like. No other words for the label.
"""

ROUTER_EVAL_CASES = [
    {"question": "What are the collections available?", "expected_route": "item_inquiry"},
    {"question": "I am a newly wed, suggest some items for my home", "expected_route": "recommendation"},
    {
        "question": "I want to place a custom order for a potpurri bowl with my initials on it",
        "expected_route": "orders",
    },
    {"question": "What is the return policy on opened items?", "expected_route": "orders"},
    {
        "question": "What is the shipping cost of shipping 4 pasta bowls to zip code 95125",
        "expected_route": "orders",
    },
    {"question": "Show me all the items available in 'Dot' collection?", "expected_route": "item_inquiry"},
]


def _load_tool_correctness_template_raw() -> str:
    base = Path(__file__).resolve().parent
    for name in ("TOOL_CORRECTNESS_EVALUATION.txt", "TOOL_CORRECTNESS_EVALUATION"):
        path = base / name
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text.startswith("TOOL_CORRECTNESS_EVALUATION"):
                first = text.find('"""')
                if first != -1:
                    rest = text[first + 3:]
                    last = rest.rfind('"""')
                    if last != -1:
                        return rest[:last].strip()
            return text
    raise FileNotFoundError(
        "Missing TOOL_CORRECTNESS_EVALUATION.txt (or TOOL_CORRECTNESS_EVALUATION) next to evaluation.py."
    )


def _escape_braces_keep_query_response(template: str) -> str:
    """Escape literal `{`/`}` except `{query}` and `{response}` placeholders."""
    t = template.replace("{query}", "\x00Q\x00").replace("{response}", "\x00R\x00")
    t = t.replace("{", "{{").replace("}", "}}")
    return t.replace("\x00Q\x00", "{query}").replace("\x00R\x00", "{response}")


@lru_cache(maxsize=1)
def get_tool_correctness_prompt_template() -> str:
    """TOOL_CORRECTNESS_EVALUATION* only - not used for tone."""
    return _escape_braces_keep_query_response(_load_tool_correctness_template_raw())


def _load_tool_tone_template_raw() -> str:
    base = Path(__file__).resolve().parent
    for name in ("TOOL_TONE_EVALUATION.txt", "TOOL_TONE_EVALUATION", "TOOL_TONE_EVAULATION"):
        path = base / name
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if '"""' in text:
                first = text.find('"""')
                rest = text[first + 3:]
                last = rest.rfind('"""')
                if last != -1:
                    return rest[:last].strip()
            return text
    raise FileNotFoundError(
        "Missing TOOL_TONE_EVALUATION.txt (or TOOL_TONE_EVALUATION / TOOL_TONE_EVAULATION) next to evaluation.py."
    )


def _inject_olivia_writing_style_into_tool_tone_template(template: str) -> str:
    """TOOL_TONE template only - replaces {olivia_writing_style.txt} with file contents."""
    path = Path(__file__).resolve().parent / "olivia_writing_style.txt"
    body = (
        path.read_text(encoding="utf-8").strip()
        if path.is_file()
        else "[Could not load olivia_writing_style.txt]"
    )
    return template.replace("{olivia_writing_style.txt}", body)


@lru_cache(maxsize=1)
def get_tool_tone_prompt_template() -> str:
    """TOOL_TONE_EVALUATION* only - not mixed with TOOL_CORRECTNESS."""
    raw = _load_tool_tone_template_raw()
    raw = _inject_olivia_writing_style_into_tool_tone_template(raw)
    return _escape_braces_keep_query_response(raw) + TOOL_TONE_EVAL_LLM_LABEL_SUFFIX


def _extract_routed_handler(output_value: Any) -> str:
    if output_value is None:
        return ""
    if isinstance(output_value, dict):
        return str(output_value.get("routed to handler", "")).strip().lower()

    raw = str(output_value).strip()
    if not raw:
        return ""

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return str(parsed.get("routed to handler", "")).strip().lower()
    except Exception:
        pass

    return raw.lower()


def run_eval_cases() -> None:
    batch_span_ctx = (
        main.tracer.start_as_current_span(
            "router_route_eval_batch",
            openinference_span_kind="chain",
        )
        if main.tracer is not None
        else nullcontext()
    )

    with batch_span_ctx:
        for case in tqdm(ROUTER_EVAL_CASES, desc="Running router route eval"):
            try:
                run_router(case["question"])
            except Exception as exc:
                print(f"Router call failed for: {case['question']}")
                print(exc)


def evaluate_run_router_routes() -> pd.DataFrame:
    query = (
        SpanQuery()
        .where("name == 'run_router'")
        .select("input.value", "output.value")
        .rename(input_value="question", output_value="router_output_raw")
    )

    try:
        spans_df = _phoenix_rest_client.spans.get_spans_dataframe(
            query=cast(Any, query),
            project_identifier=PROJECT_NAME,
            timeout=None,
        )
    except Exception as exc:
        print(f"Failed to query run_router spans from Phoenix: {exc}")
        return pd.DataFrame(
            {"question": [], "expected_route": [], "detected_route": [], "is_correct": []}
        )

    if spans_df.empty:
        return pd.DataFrame(
            {"question": [], "expected_route": [], "detected_route": [], "is_correct": []}
        )

    spans_df = spans_df.copy()
    spans_df["span_id"] = spans_df.index.astype(str)
    question_col = "question" if "question" in spans_df.columns else "input.value"
    output_col = "router_output_raw" if "router_output_raw" in spans_df.columns else "output.value"
    if question_col not in spans_df.columns or output_col not in spans_df.columns:
        return pd.DataFrame(
            {"span_id": [], "question": [], "expected_route": [], "detected_route": [], "is_correct": []}
        )

    spans_df["question"] = spans_df[question_col]
    spans_df["detected_route"] = spans_df[output_col].apply(_extract_routed_handler)
    spans_df = spans_df[spans_df["question"].notna()][["span_id", "question", "detected_route"]]

    expected_df = pd.DataFrame(ROUTER_EVAL_CASES)
    result_df = expected_df.merge(cast(pd.DataFrame, spans_df), on="question", how="left")
    result_df["detected_route"] = result_df["detected_route"].fillna("")
    result_df["is_correct"] = (
        result_df["expected_route"].str.lower() == result_df["detected_route"].str.lower()
    )
    return result_df


def fetch_run_router_chain_spans() -> pd.DataFrame:
    query = (
        SpanQuery()
        .where("span_kind == 'CHAIN' and name == 'run_router'")
        .select("input.value", "output.value")
        .rename(input_value="question", output_value="router_output_raw")
    )
    try:
        spans_df = _phoenix_rest_client.spans.get_spans_dataframe(
            query=cast(Any, query),
            project_identifier=PROJECT_NAME,
            timeout=None,
        )
    except Exception as exc:
        print(f"Failed to query run_router (CHAIN) spans from Phoenix: {exc}")
        return pd.DataFrame()
    if spans_df.empty:
        return pd.DataFrame()
    spans_df = spans_df.copy()
    spans_df["span_id"] = spans_df.index.astype(str)
    return spans_df


def build_run_router_llm_dataframe(spans_df: pd.DataFrame) -> pd.DataFrame:
    if spans_df.empty:
        return pd.DataFrame()
    qcol = "question" if "question" in spans_df.columns else "input.value"
    ocol = "router_output_raw" if "router_output_raw" in spans_df.columns else "output.value"
    expected_df = pd.DataFrame(ROUTER_EVAL_CASES)
    rows: list[dict[str, Any]] = []
    for _, row in spans_df.iterrows():
        q = row.get(qcol)
        question = "" if q is None or (isinstance(q, float) and pd.isna(q)) else str(q).strip()
        if not question:
            continue
        routed = _extract_routed_handler(row.get(ocol))
        if not routed:
            continue
        match = expected_df[expected_df["question"] == question]
        if match.empty:
            continue
        expected = str(match.iloc[0]["expected_route"]).strip().lower()
        reference = (
            f"The benchmark expected handler is '{expected}'. "
            "Handlers: item_inquiry (catalog, items, price, collections), "
            "recommendation (suggestions, gifts), "
            "orders (shipping, returns, custom orders). "
            "Decide if the routed handler name in the output matches this expected routing."
        )
        rows.append(
            {
                "span_id": str(row["span_id"]),
                "input": question,
                "reference": reference,
                "output": routed,
                "expected_route": expected,
                "detected_route": routed,
            }
        )
    return pd.DataFrame(rows)


def _score_from_tool_label(label: Any) -> float:
    s = str(label).strip().lower()
    if s == "correct":
        return 1.0
    if s == "incorrect":
        return 0.0
    return 0.0


def _normalize_eval_text_for_label_parse(text: str) -> str:
    """Normalize quotes / dashes so regexes match model output."""
    t = str(text)
    t = (
        t.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    return t


def _line_is_label_placeholder_echo(line: str) -> bool:
    """True if line looks like the instruction stub, not a real verdict."""
    low = line.lower()
    if " or " not in low:
        return False
    return "correct" in low and "incorrect" in low and "label" in low


def _recover_verdict_synonyms(text: str) -> Optional[str]:
    """Last-resort: models often say Right/Wrong/Yes/No instead of correct/incorrect."""
    t = _normalize_eval_text_for_label_parse(text)
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    ms = list(
        re.finditer(
            r"(?is)\b(?:verdict|conclusion|result|assessment|rating|final\s*(?:answer|judgment))\b"
            r"\s*[:=-]\s*\*?\s*\b(wrong|right|yes|no)\b",
            t,
        )
    )
    if ms:
        w = ms[-1].group(1).lower()
        if w in ("wrong", "no"):
            return "incorrect"
        if w in ("right", "yes"):
            return "correct"
    for line in reversed(lines[-8:]):
        if _line_is_label_placeholder_echo(line):
            continue
        m = re.match(
            r"(?i)^(?:verdict|conclusion|result|answer)\s*[:=-]\s*\*?\s*(wrong|right|yes|no)\s*\.?$",
            line.strip(),
        )
        if m:
            w = m.group(1).lower()
            return "incorrect" if w in ("wrong", "no") else "correct"
        m2 = re.match(r"(?i)^[*_`\s]*\b(wrong|right|yes|no)\b[*_`\s.]*$", line.strip())
        if m2:
            w = m2.group(1).lower()
            return "incorrect" if w in ("wrong", "no") else "correct"
    return None


def _recover_binary_correct_incorrect_label(text: str) -> Optional[str]:
    """Recover 'correct' / 'incorrect' when Phoenix snap_to_rail returned NOT_PARSABLE.

    Common causes: both rails appear in CoT; model echoes ``LABEL: "correct" or "incorrect"``;
    unicode quotes; verdict only at end of a long response.
    """
    if not text or not str(text).strip():
        return None
    t = _normalize_eval_text_for_label_parse(text)

    # 1) Line-leading LABEL / VERDICT (ignore instruction-echo lines). Allow : = - – — and trailing text.
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    for line in reversed(lines[-24:]):
        if _line_is_label_placeholder_echo(line):
            continue
        m = re.match(
            r"(?i)^(?:label|final\s*label|verdict|answer)\s*[:=\-–—]\s*[\"'`\s*]*\b(correct|incorrect)\b",
            line,
        )
        if m:
            return m.group(1).lower()

    # 2) Any LABEL:/VERDICT: with a rail (skip "correct or incorrect" stubs)
    good: List[re.Match[Any]] = []
    for m in re.finditer(
        r"(?i)\b(?:label|final\s*label|verdict|answer)\s*[:=\-–—]\s*[\"'`\s]*\b(correct|incorrect)\b",
        t,
    ):
        line_start = t.rfind("\n", 0, m.start()) + 1
        line_end = t.find("\n", m.end())
        if line_end == -1:
            line_end = len(t)
        line = t[line_start:line_end]
        if _line_is_label_placeholder_echo(line):
            continue
        good.append(m)
    if good:
        return good[-1].group(1).lower()

    # 3) JSON-like
    jm = re.search(
        r'(?i)["\']label["\']\s*:\s*["\']?(correct|incorrect)\b',
        t,
    )
    if jm:
        return jm.group(1).lower()

    # 4) Last few lines: exact single word (markdown tolerated)
    for line in reversed(lines[-16:]):
        if _line_is_label_placeholder_echo(line):
            continue
        m = re.match(
            r"(?i)^[*_`\s]*\b(correct|incorrect)\b[*_`\s.]*$",
            line.strip(),
        )
        if m:
            return m.group(1).lower()
        low = line.lower().rstrip(".")
        if low in ("correct", "incorrect"):
            return low

    stripped = t.strip()
    if stripped.lower() in ("correct", "incorrect"):
        return stripped.lower()

    found = re.findall(r"(?i)\b(correct|incorrect)\b", t)
    if len(found) == 1:
        return found[0].lower()
    uniq = {x.lower() for x in found}
    if len(uniq) == 1 and found:
        return found[0].lower()

    sentences = re.split(r"(?<=[.!?])\s+", stripped)
    if sentences:
        last_sent = sentences[-1]
        sf = re.findall(r"(?i)\b(correct|incorrect)\b", last_sent)
        sfu = {x.lower() for x in sf}
        if len(sfu) == 1 and sf:
            return sf[-1].lower()

    summary_hits = list(
        re.finditer(
            r"(?is)\b(?:therefore|thus|overall|in\s+conclusion|my\s+(?:final\s+)?(?:answer|verdict|label))\b"
            r"[^.!?\n]{0,320}?"
            r"\b(correct|incorrect)\b",
            t,
        )
    )
    if summary_hits:
        return summary_hits[-1].group(1).lower()

    tail = t[-2000:] if len(t) > 2000 else t
    tail_found = re.findall(r"(?i)\b(correct|incorrect)\b", tail)
    if tail_found:
        return tail_found[-1].lower()
    syn = _recover_verdict_synonyms(t)
    if syn:
        return syn
    return None


def _normalize_llm_classify_output(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure Phoenix llm_classify results have string `label` and float `score`.

    Phoenix sets `label` via snap_to_rail on text from ``extract_label_from_explanation`` (not the
    full reply). That text can be wrong when ``\\blabel\\b`` appears early (e.g. "predicted label"),
    or when both rails appear in CoT — then Phoenix emits NOT_PARSABLE. The dataframe still has the
    full model output in ``explanation`` / ``response``; we re-parse that here and map synonyms.
    """
    out = df.copy()
    meta_cols = {
        "exceptions",
        "execution_status",
        "execution_seconds",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt",
        "response",
    }
    if "label" not in out.columns:
        candidates = [c for c in out.columns if c not in meta_cols]
        if candidates:
            out = out.rename(columns={candidates[0]: "label"})

    def _to_label_str(v: Any) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return NOT_PARSABLE
        t = str(v).strip()
        return t if t else NOT_PARSABLE

    if "label" not in out.columns:
        out["label"] = NOT_PARSABLE
    else:
        out["label"] = out["label"].map(_to_label_str)

    def _finalize_label_row(row: pd.Series) -> str:
        primary = str(row["label"])
        pl = primary.strip().lower()
        if pl in ("correct", "incorrect"):
            return pl
        parts: List[str] = []
        for col in ("explanation", "response", "label"):
            if col not in row.index:
                continue
            v = row[col]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            s = str(v).strip()
            if not s:
                continue
            # Dropping NOT_PARSABLE keeps the real model text (explanation/response) visible to recovery.
            if s.upper() == NOT_PARSABLE:
                continue
            parts.append(s)
        combined = "\n\n".join(parts) if parts else primary.strip()
        recovered = _recover_binary_correct_incorrect_label(combined)
        if recovered:
            return recovered
        return primary

    out["label"] = out.apply(_finalize_label_row, axis=1)
    out["score"] = out["label"].map(_score_from_tool_label).astype(float)
    return out


def evaluate_run_router_with_llm() -> pd.DataFrame:
    spans_df = fetch_run_router_chain_spans()
    prep = build_run_router_llm_dataframe(spans_df)
    if prep.empty:
        print("No run_router CHAIN spans with routed handler + benchmark match for LLM eval.")
        return pd.DataFrame()
    classify_in = prep[["input", "reference", "output"]].copy()
    try:
        classified = llm_classify(
            data=classify_in,
            model=AnthropicModel(model=MODEL, temperature=0.0),
            template=RUN_ROUTER_QA_PROMPT_TEMPLATE,
            rails=list(QA_PROMPT_RAILS_MAP.values()),
            provide_explanation=True,
            include_response=True,
            run_sync=True,
            progress_bar_format=None,
        )
    except Exception as exc:
        print(f"LLM run_router evaluation failed: {exc}")
        return pd.DataFrame()
    classified = _normalize_llm_classify_output(classified)
    classified = classified.copy()
    classified.insert(0, "span_id", prep["span_id"].values)
    classified["question"] = prep["input"].values
    classified["expected_route"] = prep["expected_route"].values
    classified["detected_route"] = prep["detected_route"].values
    return classified


def log_run_router_llm_evaluations(classified_df: pd.DataFrame) -> None:
    if classified_df.empty or "span_id" not in classified_df.columns:
        print("No run_router LLM eval rows to log to Phoenix.")
        return
    label_col = "label" if "label" in classified_df.columns else None
    if not label_col:
        print("run_router LLM eval dataframe missing label column.")
        return
    ann = classified_df.dropna(subset=["span_id"]).copy()
    ann["label"] = ann[label_col].astype(str)
    expl_col = "explanation" if "explanation" in ann.columns else None
    if expl_col:
        ann["explanation"] = ann[expl_col].astype(str)
    else:
        ann["explanation"] = ""
    ann["score"] = ann["label"].map(_score_from_tool_label)
    ann["metadata"] = ann.apply(
        lambda row: {
            "question": row.get("question", ""),
            "expected_route": row.get("expected_route", ""),
            "detected_route": row.get("detected_route", ""),
        },
        axis=1,
    )
    ann = ann.set_index("span_id")[["label", "score", "explanation", "metadata"]]
    ann = cast(pd.DataFrame, ann)
    try:
        _phoenix_rest_client.spans.log_span_annotations_dataframe(
            dataframe=ann,
            annotator_kind="LLM",
            annotation_name="run_router_llm_eval",
        )
        print("Logged run_router_llm_eval span annotations to Phoenix (UI).")
    except Exception as exc:
        print(f"Failed to log run_router LLM span annotations to Phoenix: {exc}")
    verdict_col = cast(str, label_col)
    log_df = classified_df[["span_id", verdict_col]].copy()
    log_df.columns = ["span_id", "label"]
    log_df = cast(pd.DataFrame, log_df)
    if expl_col:
        log_df["explanation"] = classified_df[expl_col].astype(str)
    else:
        log_df["explanation"] = ""
    log_df["score"] = log_df["label"].map(_score_from_tool_label)
    log_df = log_df.dropna(subset=["span_id"])
    log_df = cast(pd.DataFrame, log_df.set_index("span_id")[["label", "score", "explanation"]])
    try:
        _phoenix_session_client.log_evaluations(
            SpanEvaluations(eval_name="Run Router LLM Eval", dataframe=log_df)
        )
        print("Logged Run Router LLM Eval to Phoenix (evaluations API).")
    except Exception as exc:
        print(f"Failed to log run_router LLM evaluations via evaluations API: {exc}")


def _extract_intent_label_from_output(output_value: Any) -> str:
    if output_value is None:
        return ""
    if isinstance(output_value, dict):
        return str(output_value.get("label", "")).strip().lower()
    raw = str(output_value).strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return str(parsed.get("label", "")).strip().lower()
    except Exception:
        pass
    return ""


def fetch_detect_intent_spans() -> pd.DataFrame:
    query = (
        SpanQuery()
        .where("span_kind == 'AGENT' and name == 'detect_intent'")
        .select("input.value", "output.value")
        .rename(input_value="question", output_value="intent_output_raw")
    )
    try:
        spans_df = _phoenix_rest_client.spans.get_spans_dataframe(
            query=cast(Any, query),
            project_identifier=PROJECT_NAME,
            timeout=None,
        )
    except Exception as exc:
        print(f"Failed to query detect_intent spans from Phoenix: {exc}")
        return pd.DataFrame()
    if spans_df.empty:
        return pd.DataFrame()
    spans_df = spans_df.copy()
    spans_df["span_id"] = spans_df.index.astype(str)
    return spans_df


def build_detect_intent_llm_dataframe(spans_df: pd.DataFrame) -> pd.DataFrame:
    if spans_df.empty:
        return pd.DataFrame()
    qcol = "question" if "question" in spans_df.columns else "input.value"
    ocol = "intent_output_raw" if "intent_output_raw" in spans_df.columns else "output.value"
    expected_df = pd.DataFrame(ROUTER_EVAL_CASES)
    rows: list[dict[str, Any]] = []
    for _, row in spans_df.iterrows():
        q = row.get(qcol)
        question = "" if q is None or (isinstance(q, float) and pd.isna(q)) else str(q).strip()
        if not question:
            continue
        predicted = _extract_intent_label_from_output(row.get(ocol))
        if not predicted:
            continue
        match = expected_df[expected_df["question"] == question]
        if match.empty:
            continue
        expected = str(match.iloc[0]["expected_route"]).strip().lower()
        reference = (
            f"The benchmark expected intent is '{expected}'. "
            "Labels: item_inquiry (catalog, items, price, collections, stock), "
            "recommendation (suggestions, gifts, what to buy), "
            "orders (shipping, returns, refunds, custom orders). "
            "Decide if the predicted intent label matches the expected intent."
        )
        rows.append(
            {
                "span_id": str(row["span_id"]),
                "input": question,
                "reference": reference,
                "output": predicted,
                "expected_route": expected,
                "predicted_label": predicted,
            }
        )
    return pd.DataFrame(rows)


def evaluate_detect_intent_with_llm() -> pd.DataFrame:
    spans_df = fetch_detect_intent_spans()
    prep = build_detect_intent_llm_dataframe(spans_df)
    if prep.empty:
        print("No detect_intent spans with label + benchmark match for LLM intent eval.")
        return pd.DataFrame()
    classify_in = prep[["input", "reference", "output"]].copy()
    try:
        classified = llm_classify(
            data=classify_in,
            model=AnthropicModel(model=MODEL, temperature=0.0),
            template=INTENT_LABEL_PROMPT_TEMPLATE,
            rails=list(QA_PROMPT_RAILS_MAP.values()),
            provide_explanation=True,
            include_response=True,
            run_sync=True,
            progress_bar_format=None,
        )
    except Exception as exc:
        print(f"LLM detect_intent evaluation failed: {exc}")
        return pd.DataFrame()
    classified = _normalize_llm_classify_output(classified)
    classified = classified.copy()
    classified.insert(0, "span_id", prep["span_id"].values)
    classified["question"] = prep["input"].values
    classified["expected_route"] = prep["expected_route"].values
    classified["predicted_label"] = prep["predicted_label"].values
    return classified


def log_detect_intent_evaluations(classified_df: pd.DataFrame) -> None:
    if classified_df.empty or "span_id" not in classified_df.columns:
        print("No detect_intent LLM eval rows to log to Phoenix.")
        return
    label_col = "label" if "label" in classified_df.columns else None
    if not label_col:
        print("detect_intent eval dataframe missing label column.")
        return
    ann = classified_df.dropna(subset=["span_id"]).copy()
    ann["label"] = ann[label_col].astype(str)
    expl_col = "explanation" if "explanation" in ann.columns else None
    if expl_col:
        ann["explanation"] = ann[expl_col].astype(str)
    else:
        ann["explanation"] = ""
    ann["score"] = ann["label"].map(_score_from_tool_label)
    ann["metadata"] = ann.apply(
        lambda row: {
            "question": row.get("question", ""),
            "expected_route": row.get("expected_route", ""),
            "predicted_label": row.get("predicted_label", ""),
        },
        axis=1,
    )
    ann = ann.set_index("span_id")[["label", "score", "explanation", "metadata"]]
    ann = cast(pd.DataFrame, ann)
    try:
        _phoenix_rest_client.spans.log_span_annotations_dataframe(
            dataframe=ann,
            annotator_kind="LLM",
            annotation_name="detect_intent_llm_eval",
        )
        print("Logged detect_intent_llm_eval span annotations to Phoenix (UI).")
    except Exception as exc:
        print(f"Failed to log detect_intent span annotations to Phoenix: {exc}")
    verdict_col = cast(str, label_col)
    log_df = classified_df[["span_id", verdict_col]].copy()
    log_df.columns = ["span_id", "label"]
    log_df = cast(pd.DataFrame, log_df)
    if expl_col:
        log_df["explanation"] = classified_df[expl_col].astype(str)
    else:
        log_df["explanation"] = ""
    log_df["score"] = log_df["label"].map(_score_from_tool_label)
    log_df = log_df.dropna(subset=["span_id"])
    log_df = cast(pd.DataFrame, log_df.set_index("span_id")[["label", "score", "explanation"]])
    try:
        _phoenix_session_client.log_evaluations(
            SpanEvaluations(eval_name="Detect Intent LLM Eval", dataframe=log_df)
        )
        print("Logged Detect Intent LLM Eval to Phoenix (evaluations API).")
    except Exception as exc:
        print(f"Failed to log detect_intent evaluations via evaluations API: {exc}")


def _extract_tool_name_from_agent_output(output_value: Any) -> str:
    if output_value is None:
        return ""
    if isinstance(output_value, dict):
        return str(output_value.get("tool_name", "")).strip()
    raw = str(output_value).strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return str(parsed.get("tool_name", "")).strip()
    except Exception:
        pass
    return ""


def fetch_agent_spans_for_tool_eval() -> pd.DataFrame:
    query = (
        SpanQuery()
        .where("span_kind == 'AGENT' and name != 'detect_intent'")
        .select("input.value", "output.value", "name")
        .rename(input_value="question", output_value="agent_output_raw")
    )
    try:
        spans_df = _phoenix_rest_client.spans.get_spans_dataframe(
            query=cast(Any, query),
            project_identifier=PROJECT_NAME,
            timeout=None,
        )
    except Exception as exc:
        print(f"Failed to query agent spans from Phoenix: {exc}")
        return pd.DataFrame()
    if spans_df.empty:
        return pd.DataFrame()
    spans_df = spans_df.copy()
    spans_df["span_id"] = spans_df.index.astype(str)
    name_col = "name" if "name" in spans_df.columns else None
    if not name_col:
        print("Span query did not return span name; cannot filter agent tool spans.")
        return pd.DataFrame()
    spans_df = cast(pd.DataFrame, spans_df[spans_df[name_col].astype(str) == "item_inquiry"])
    return spans_df


def build_tool_eval_classify_dataframe(spans_df: pd.DataFrame) -> pd.DataFrame:
    if spans_df.empty:
        return pd.DataFrame()
    td = json.dumps(TOOLS, indent=2, ensure_ascii=False)
    qcol = "question" if "question" in spans_df.columns else "input.value"
    ocol = "agent_output_raw" if "agent_output_raw" in spans_df.columns else "output.value"
    rows = []
    for _, row in spans_df.iterrows():
        q = row.get(qcol)
        out_raw = row.get(ocol)
        tool_name = _extract_tool_name_from_agent_output(out_raw)
        if not tool_name:
            continue
        rows.append(
            {
                "span_id": str(row["span_id"]),
                "question": "" if q is None else str(q),
                "tool_call": tool_name,
                "tool_definitions": td,
            }
        )
    return pd.DataFrame(rows)


def evaluate_agent_tool_choice_with_llm() -> pd.DataFrame:
    spans_df = fetch_agent_spans_for_tool_eval()
    prep = build_tool_eval_classify_dataframe(spans_df)
    if prep.empty:
        print("No item_inquiry agent spans with tool_name available for LLM tool eval.")
        return pd.DataFrame()
    try:
        # With provide_explanation=True, Phoenix parses LABEL from long CoT text then snaps to
        # rails; if both "correct" and "incorrect" appear (common in explanations), snap_to_rail
        # yields NOT_PARSABLE. The base TOOL_CALLING template asks for a single-word answer,
        # which snaps reliably on Anthropic (no OpenAI-style function calling here).
        classified = llm_classify(
            data=prep,
            model=AnthropicModel(model=MODEL, temperature=0.0),
            template=TOOL_PROMPT_TEMPLATE,
            rails=list(TOOL_CALLING_PROMPT_RAILS_MAP.values()),
            provide_explanation=False,
            include_response=True,
            run_sync=True,
            progress_bar_format=None,
        )
    except Exception as exc:
        print(f"LLM tool evaluation failed: {exc}")
        return pd.DataFrame()
    classified = _normalize_llm_classify_output(classified)
    classified = classified.copy()
    classified.insert(0, "span_id", prep["span_id"].values)
    classified["question"] = prep["question"].values
    classified["tool_call"] = prep["tool_call"].values
    return classified


def log_agent_tool_evaluations(classified_df: pd.DataFrame) -> None:
    if classified_df.empty or "span_id" not in classified_df.columns:
        print("No LLM tool eval rows to log to Phoenix.")
        return
    label_col = "label" if "label" in classified_df.columns else None
    if not label_col:
        print("LLM tool eval dataframe missing label column.")
        return
    ann = classified_df.dropna(subset=["span_id"]).copy()
    ann["label"] = ann[label_col].astype(str)
    expl_col = "explanation" if "explanation" in ann.columns else None
    if expl_col:
        ann["explanation"] = ann[expl_col].astype(str)
    else:
        ann["explanation"] = ""
    ann["score"] = ann["label"].map(_score_from_tool_label)
    qcol = "question" if "question" in ann.columns else None
    tcol = "tool_call" if "tool_call" in ann.columns else None
    if qcol or tcol:
        ann["metadata"] = ann.apply(
            lambda row: {
                "question": row[qcol] if qcol else "",
                "tool_call": row[tcol] if tcol else "",
            },
            axis=1,
        )
    else:
        ann["metadata"] = [{} for _ in range(len(ann))]
    ann = ann.set_index("span_id")[["label", "score", "explanation", "metadata"]]
    ann = cast(pd.DataFrame, ann)
    try:
        _phoenix_rest_client.spans.log_span_annotations_dataframe(
            dataframe=ann,
            annotator_kind="LLM",
            annotation_name="agent_tool_choice_llm_eval",
        )
        print("Logged agent_tool_choice_llm_eval span annotations to Phoenix (UI).")
    except Exception as exc:
        print(f"Failed to log agent tool span annotations to Phoenix: {exc}")
    verdict_col = cast(str, label_col)
    log_df = classified_df[["span_id", verdict_col]].copy()
    log_df.columns = ["span_id", "label"]
    log_df = cast(pd.DataFrame, log_df)
    if expl_col:
        log_df["explanation"] = classified_df[expl_col].astype(str)
    else:
        log_df["explanation"] = ""
    log_df["score"] = log_df["label"].map(_score_from_tool_label)
    log_df = log_df.dropna(subset=["span_id"])
    log_df = cast(pd.DataFrame, log_df.set_index("span_id")[["label", "score", "explanation"]])
    try:
        _phoenix_session_client.log_evaluations(
            SpanEvaluations(eval_name="Agent Tool Choice LLM Eval", dataframe=log_df)
        )
        print("Logged Agent Tool Choice LLM Eval to Phoenix (evaluations API).")
    except Exception as exc:
        print(f"Failed to log agent tool evaluations via evaluations API: {exc}")


def fetch_tool_kind_spans() -> pd.DataFrame:
    query = (
        SpanQuery()
        .where("span_kind == 'TOOL'")
        .select("input.value", "output.value", "name")
        .rename(input_value="tool_input_raw", output_value="tool_output_raw")
    )
    try:
        spans_df = _phoenix_rest_client.spans.get_spans_dataframe(
            query=cast(Any, query),
            project_identifier=PROJECT_NAME,
            timeout=None,
        )
    except Exception as exc:
        print(f"Failed to query TOOL spans from Phoenix: {exc}")
        return pd.DataFrame()
    if spans_df.empty:
        return pd.DataFrame()
    spans_df = spans_df.copy()
    spans_df["span_id"] = spans_df.index.astype(str)
    return spans_df


def _cell_to_eval_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)
    return str(value).strip()


def _tool_spans_to_query_response_dataframe(spans_df: pd.DataFrame) -> pd.DataFrame:
    if spans_df.empty:
        return pd.DataFrame()
    icol = "tool_input_raw" if "tool_input_raw" in spans_df.columns else "input.value"
    ocol = "tool_output_raw" if "tool_output_raw" in spans_df.columns else "output.value"
    ncol = "name" if "name" in spans_df.columns else None
    rows: list[dict[str, Any]] = []
    for _, row in spans_df.iterrows():
        query_text = _cell_to_eval_str(row.get(icol))
        response_text = _cell_to_eval_str(row.get(ocol))
        if not query_text and not response_text:
            continue
        r: dict[str, Any] = {
            "span_id": str(row["span_id"]),
            "query": query_text or "(empty)",
            "response": response_text or "(empty)",
        }
        if ncol:
            r["span_name"] = str(row.get(ncol, ""))
        rows.append(r)
    return pd.DataFrame(rows)


def build_tool_correctness_eval_dataframe(spans_df: pd.DataFrame) -> pd.DataFrame:
    """Rows for TOOL_CORRECTNESS eval only (same span inputs as tone; separate function for clarity)."""
    return _tool_spans_to_query_response_dataframe(spans_df)


def build_tool_tone_eval_dataframe(spans_df: pd.DataFrame) -> pd.DataFrame:
    """Rows for TOOL_TONE eval only."""
    return _tool_spans_to_query_response_dataframe(spans_df)


def evaluate_tool_kind_correctness_with_llm() -> pd.DataFrame:
    spans_df = fetch_tool_kind_spans()
    prep = build_tool_correctness_eval_dataframe(spans_df)
    if prep.empty:
        print("No TOOL spans with input/output available for tool correctness LLM eval.")
        return pd.DataFrame()
    classify_in = prep[["query", "response"]].copy()
    try:
        classified = llm_classify(
            data=classify_in,
            model=AnthropicModel(model=MODEL, temperature=0.0),
            template=get_tool_correctness_prompt_template(),
            rails=TOOL_CORRECTNESS_LLM_RAILS,
            provide_explanation=True,
            include_response=True,
            run_sync=True,
            progress_bar_format=None,
        )
    except Exception as exc:
        print(f"LLM tool-kind correctness evaluation failed: {exc}")
        return pd.DataFrame()
    classified = _normalize_llm_classify_output(classified)
    classified = classified.copy()
    classified.insert(0, "span_id", prep["span_id"].values)
    classified["query"] = prep["query"].values
    classified["response"] = prep["response"].values
    if "span_name" in prep.columns:
        classified["span_name"] = prep["span_name"].values
    return classified


def log_tool_kind_correctness_evaluations(classified_df: pd.DataFrame) -> None:
    if classified_df.empty or "span_id" not in classified_df.columns:
        print("No tool-kind correctness LLM eval rows to log to Phoenix.")
        return
    label_col = "label" if "label" in classified_df.columns else None
    if not label_col:
        print("Tool correctness eval dataframe missing label column.")
        return
    ann = classified_df.dropna(subset=["span_id"]).copy()
    ann["label"] = ann[label_col].astype(str)
    expl_col = "explanation" if "explanation" in ann.columns else None
    if expl_col:
        ann["explanation"] = ann[expl_col].astype(str)
    else:
        ann["explanation"] = ""
    ann["score"] = ann["label"].map(_score_from_tool_label)

    def _meta_row(row: Any) -> dict[str, Any]:
        resp = str(row.get("response", ""))
        return {
            "span_name": str(row.get("span_name", "")),
            "query": str(row.get("query", "")),
            "response_preview": (resp[:500] + "…") if len(resp) > 500 else resp,
        }

    ann["metadata"] = ann.apply(_meta_row, axis=1)
    ann = ann.set_index("span_id")[["label", "score", "explanation", "metadata"]]
    ann = cast(pd.DataFrame, ann)
    try:
        _phoenix_rest_client.spans.log_span_annotations_dataframe(
            dataframe=ann,
            annotator_kind="LLM",
            annotation_name="tool_kind_correctness_llm_eval",
        )
        print("Logged tool_kind_correctness_llm_eval span annotations to Phoenix (UI).")
    except Exception as exc:
        print(f"Failed to log tool-kind correctness span annotations to Phoenix: {exc}")
    verdict_col = cast(str, label_col)
    log_df = classified_df[["span_id", verdict_col]].copy()
    log_df.columns = ["span_id", "label"]
    log_df = cast(pd.DataFrame, log_df)
    if expl_col:
        log_df["explanation"] = classified_df[expl_col].astype(str)
    else:
        log_df["explanation"] = ""
    log_df["score"] = log_df["label"].map(_score_from_tool_label)
    log_df = log_df.dropna(subset=["span_id"])
    log_df = cast(pd.DataFrame, log_df.set_index("span_id")[["label", "score", "explanation"]])
    try:
        _phoenix_session_client.log_evaluations(
            SpanEvaluations(eval_name="Tool Kind Correctness LLM Eval", dataframe=log_df)
        )
        print("Logged Tool Kind Correctness LLM Eval to Phoenix (evaluations API).")
    except Exception as exc:
        print(f"Failed to log tool-kind correctness evaluations via evaluations API: {exc}")


def evaluate_tool_kind_tone_with_llm() -> pd.DataFrame:
    spans_df = fetch_tool_kind_spans()
    prep = build_tool_tone_eval_dataframe(spans_df)
    if prep.empty:
        print("No TOOL spans with input/output available for tool tone LLM eval.")
        return pd.DataFrame()
    classify_in = prep[["query", "response"]].copy()
    try:
        classified = llm_classify(
            data=classify_in,
            model=AnthropicModel(model=MODEL, temperature=0.0),
            template=get_tool_tone_prompt_template(),
            rails=TOOL_TONE_LLM_RAILS,
            provide_explanation=True,
            include_response=True,
            run_sync=True,
            progress_bar_format=None,
        )
    except Exception as exc:
        print(f"LLM tool-kind tone evaluation failed: {exc}")
        return pd.DataFrame()
    classified = _normalize_llm_classify_output(classified)
    classified = classified.copy()
    classified.insert(0, "span_id", prep["span_id"].values)
    classified["query"] = prep["query"].values
    classified["response"] = prep["response"].values
    if "span_name" in prep.columns:
        classified["span_name"] = prep["span_name"].values
    return classified


def log_tool_kind_tone_evaluations(classified_df: pd.DataFrame) -> None:
    if classified_df.empty or "span_id" not in classified_df.columns:
        print("No tool-kind tone LLM eval rows to log to Phoenix.")
        return
    label_col = "label" if "label" in classified_df.columns else None
    if not label_col:
        print("Tool tone eval dataframe missing label column.")
        return
    ann = classified_df.dropna(subset=["span_id"]).copy()
    ann["label"] = ann[label_col].astype(str)
    expl_col = "explanation" if "explanation" in ann.columns else None
    if expl_col:
        ann["explanation"] = ann[expl_col].astype(str)
    else:
        ann["explanation"] = ""
    ann["score"] = ann["label"].map(_score_from_tool_label)

    def _tone_meta_row(row: Any) -> dict[str, Any]:
        resp = str(row.get("response", ""))
        return {
            "span_name": str(row.get("span_name", "")),
            "query": str(row.get("query", "")),
            "response_preview": (resp[:500] + "…") if len(resp) > 500 else resp,
        }

    ann["metadata"] = ann.apply(_tone_meta_row, axis=1)
    ann = ann.set_index("span_id")[["label", "score", "explanation", "metadata"]]
    ann = cast(pd.DataFrame, ann)
    try:
        _phoenix_rest_client.spans.log_span_annotations_dataframe(
            dataframe=ann,
            annotator_kind="LLM",
            annotation_name="tool_kind_tone_llm_eval",
        )
        print("Logged tool_kind_tone_llm_eval span annotations to Phoenix (UI).")
    except Exception as exc:
        print(f"Failed to log tool-kind tone span annotations to Phoenix: {exc}")
    verdict_col = cast(str, label_col)
    log_df = classified_df[["span_id", verdict_col]].copy()
    log_df.columns = ["span_id", "label"]
    log_df = cast(pd.DataFrame, log_df)
    if expl_col:
        log_df["explanation"] = classified_df[expl_col].astype(str)
    else:
        log_df["explanation"] = ""
    log_df["score"] = log_df["label"].map(_score_from_tool_label)
    log_df = log_df.dropna(subset=["span_id"])
    log_df = cast(pd.DataFrame, log_df.set_index("span_id")[["label", "score", "explanation"]])
    try:
        _phoenix_session_client.log_evaluations(
            SpanEvaluations(eval_name="Tool Kind Tone LLM Eval", dataframe=log_df)
        )
        print("Logged Tool Kind Tone LLM Eval to Phoenix (evaluations API).")
    except Exception as exc:
        print(f"Failed to log tool-kind tone evaluations via evaluations API: {exc}")


if __name__ == "__main__":
    run_eval_cases()
    results = evaluate_run_router_routes()
    print(results.to_string(index=False))
    if not results.empty:
        print(f"\nRoute accuracy (string match vs benchmark): {results['is_correct'].mean():.2%}")

    router_llm_df = evaluate_run_router_with_llm()
    if not router_llm_df.empty:
        print("\nRun router LLM eval (sample):")
        print(
            router_llm_df[
                ["span_id", "label", "score", "detected_route", "expected_route"]
            ]
            .head()
            .to_string(index=False)
        )
    log_run_router_llm_evaluations(router_llm_df)

    intent_eval_df = evaluate_detect_intent_with_llm()
    if not intent_eval_df.empty:
        print("\nDetect intent LLM eval (sample):")
        print(
            intent_eval_df[
                ["span_id", "label", "score", "predicted_label", "expected_route"]
            ]
            .head()
            .to_string(index=False)
        )
    log_detect_intent_evaluations(intent_eval_df)

    tool_kind_df = evaluate_tool_kind_correctness_with_llm()
    if not tool_kind_df.empty:
        print("\nTOOL span correctness LLM eval (sample):")
        _cols = [
            c for c in ("span_id", "label", "score", "span_name") if c in tool_kind_df.columns
        ]
        print(tool_kind_df[_cols].head().to_string(index=False))
    log_tool_kind_correctness_evaluations(tool_kind_df)

    tool_tone_df = evaluate_tool_kind_tone_with_llm()
    if not tool_tone_df.empty:
        print("\nTOOL span tone LLM eval (sample):")
        _tcols = [
            c for c in ("span_id", "label", "score", "span_name") if c in tool_tone_df.columns
        ]
        print(tool_tone_df[_tcols].head().to_string(index=False))
    log_tool_kind_tone_evaluations(tool_tone_df)

    tool_eval_df = evaluate_agent_tool_choice_with_llm()
    if not tool_eval_df.empty:
        print("\nLLM tool eval (sample):")
        print(
            tool_eval_df[["span_id", "label", "score"]].head().to_string(index=False)
        )
    log_agent_tool_evaluations(tool_eval_df)
