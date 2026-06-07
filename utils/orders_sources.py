from __future__ import annotations

import json
from typing import Any, List


def format_orders_sources(faqs: List[Any], artist_notes: List[Any]) -> str:
    return (
        f"FAQs:\n{json.dumps(faqs, ensure_ascii=False, indent=2)}\n\n"
        f"Artist notes:\n{json.dumps(artist_notes, ensure_ascii=False, indent=2)}"
    )


def orders_sources_missing(faqs: List[Any], artist_notes: List[Any]) -> bool:
    return not faqs and not artist_notes
