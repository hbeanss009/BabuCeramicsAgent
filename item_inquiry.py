from pathlib import Path
from typing import Any, Iterable, cast
import json

from opentelemetry import trace as otel_trace
from client_config import client, MODEL
from tools_registry import TOOLS, TOOL_IMPLEMENTATIONS

_STYLE_PATH = Path(__file__).with_name("olivia_writing_style.txt")
tracer = otel_trace.get_tracer("BabuCeramicsAgent.item_inquiry")


def _to_span_io_value(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _set_span_input(span: object, value: object) -> None:
    if span is None:
        return
    set_input = getattr(span, "set_input", None)
    if callable(set_input):
        set_input(value)
        return
    set_attribute = getattr(span, "set_attribute", None)
    if callable(set_attribute):
        set_attribute("input.value", _to_span_io_value(value))


def _set_span_output(span: object, value: object) -> None:
    if span is None:
        return
    set_output = getattr(span, "set_output", None)
    if callable(set_output):
        set_output(value)
        return
    set_attribute = getattr(span, "set_attribute", None)
    if callable(set_attribute):
        set_attribute("output.value", _to_span_io_value(value))


def extract_text_blocks(content_blocks: Iterable[Any]) -> str:
    return " ".join(
        getattr(block, "text", "")
        for block in content_blocks
        if getattr(block, "type", None) == "text"
    ).strip()


def _style_text() -> str:
    try:
        return _STYLE_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def item_inquiry(user_text: str) -> str:
    with cast(Any, tracer).start_as_current_span(
        "item_inquiry", openinference_span_kind="agent"
    ) as span:
        span_any = cast(Any, span)
        _set_span_input(span_any, user_text)

        style_sample = _style_text()
        SYSTEM_PROMPT = f"""
        You are a catalog assistant for the business. You will be helping customers with any item related inquiries.
        You will be given a user question, you have to parse the question, identify what the user is asking for
        and call the respective tool to handle that question.

        The tools available to you are: {TOOLS}

        You have to call the tool that is most relevant to the user's query. You also need to
        determine if you need to call multiple tools to answer the user's query.
        You should return the final response to the user and ask the user if your response was helpful.

        Writing style:
        - warm, friendly, concise
        - sound like Olivia from Babu Ceramics
        - keep wording natural, not corporate

        Style sample:
        {style_sample}
        """

        messages: list[Any] = [{"role": "user", "content": user_text}]
        called_tool_names: list[str] = []

        while True:
            response = client.messages.create(
                model=MODEL,
                system=SYSTEM_PROMPT,
                messages=messages,
                max_tokens=1024,
                tools=cast(Any, TOOLS),
            )

            if response.stop_reason != "tool_use":
                final_text = extract_text_blocks(response.content)
                output_text = final_text or "I could not generate a response right now."
                _set_span_output(
                    span_any,
                    {
                        "tool_name": called_tool_names[-1] if called_tool_names else "",
                        "response": output_text,
                    },
                )
                return output_text

            tool_result_blocks: list[dict[str, Any]] = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                tool_name = getattr(block, "name", "")
                if tool_name:
                    called_tool_names.append(tool_name)
                tool_args = getattr(block, "input", None) or {}
                try:
                    fn = TOOL_IMPLEMENTATIONS[tool_name]
                    raw_result = fn(**tool_args)
                    result_text = str(raw_result)
                except Exception as exc:
                    result_text = f"Tool execution error: {tool_name}: {str(exc)}"

                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": getattr(block, "id", ""),
                        "content": result_text,
                    }
                )

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_result_blocks})
