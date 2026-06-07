from __future__ import annotations

import re
from pathlib import Path

_STYLE_PATH = Path(__file__).resolve().parent.parent / "olivia_writing_style.txt"

CONTACT_INFO_RULE = (
    "Never include email addresses, phone numbers, website URLs, or social "
    "handles unless they appear explicitly in the catalog, FAQ, or artist notes "
    "data provided in this request."
)

NO_EM_DASH_RULE = (
    "Never add this '—' to any of the outputs, use a ',' instead"
)

_EM_DASH_RE = re.compile(r"\s*[\u2014\u2013]\s*")


def sanitize_customer_output(text: str) -> str:
    """Replace em/en dashes with commas in customer-facing text."""
    if not text or "\u2014" not in text and "\u2013" not in text:
        return text
    cleaned = _EM_DASH_RE.sub(", ", text)
    cleaned = re.sub(r",\s*,", ",", cleaned)
    cleaned = re.sub(r" +", " ", cleaned)
    return cleaned.strip()

_EMAIL_HEADER_RE = re.compile(r"^On .+, .+ wrote:\s*$", re.MULTILINE)
_EMAIL_IN_ANGLE_RE = re.compile(r"<[^>]*@[^>]*>")
_EMAIL_RE = re.compile(r"\S+@\S+")
_SOCIAL_HANDLE_RE = re.compile(r"@\w+")
_SAMPLE_MARKER_RE = re.compile(r"^#sample\s*\d*\s*$", re.MULTILINE | re.IGNORECASE)


def strip_style_metadata(text: str) -> str:
    """Remove email headers and other metadata from Olivia style samples."""
    cleaned = text.replace("\ufeff", "")
    cleaned = _SAMPLE_MARKER_RE.sub("", cleaned)
    cleaned = _EMAIL_HEADER_RE.sub("", cleaned)
    cleaned = _EMAIL_IN_ANGLE_RE.sub("", cleaned)
    cleaned = _EMAIL_RE.sub("", cleaned)
    cleaned = _SOCIAL_HANDLE_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def load_olivia_style_sample() -> str:
    try:
        raw = _STYLE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    return sanitize_customer_output(strip_style_metadata(raw))
