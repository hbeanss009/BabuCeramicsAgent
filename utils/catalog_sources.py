from __future__ import annotations

import json
from typing import Any, Dict, List


def format_catalog_sources(
    catalog_payload: Dict[str, Any],
    faqs: List[Any],
    artist_notes: List[Any],
) -> str:
    return (
        f"Catalog data:\n{json.dumps(catalog_payload, ensure_ascii=False, indent=2)}\n\n"
        f"FAQs:\n{json.dumps(faqs, ensure_ascii=False, indent=2)}\n\n"
        f"Artist notes:\n{json.dumps(artist_notes, ensure_ascii=False, indent=2)}"
    )
