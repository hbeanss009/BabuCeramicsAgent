# eval/build_ground_truth.py
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
load_dotenv(_PROJECT_ROOT / ".env")

from context_builder import (
    fetch_care_guides,
    fetch_collection_stories,
    fetch_faqs,
    fetch_items,
)


def _str_field(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def build_ground_truth() -> List[Dict[str, str]]:
    """
    Dynamically fetch ground truth from Supabase.
    Returns list of {query, expected} dicts.
    """
    ground_truth: List[Dict[str, str]] = []

    for item in fetch_items() or []:
        if not isinstance(item, dict):
            continue
        name = _str_field(item, "name")
        price = item.get("price")
        material = _str_field(item, "material")
        collection = _str_field(item, "collection_name", "collection")
        if name and price is not None:
            ground_truth.append({
                "query": (
                    f"How much is the {name}?"
                ),
                "expected": (
                    f"The {name} is ${price}. It is made from {material} "
                    f"and is part of the {collection} collection."
                ),
            })

    for faq in fetch_faqs() or []:
        if not isinstance(faq, dict):
            continue
        question = _str_field(faq, "question")
        answer = _str_field(faq, "answer")
        if question and answer:
            ground_truth.append({
                "query": question,
                "expected": answer,
            })

    for story in fetch_collection_stories() or []:
        if not isinstance(story, dict):
            continue
        name = _str_field(story, "collection_name", "name", "collection", "title")
        story_text = _str_field(story, "story", "description", "content")
        if name and story_text:
            ground_truth.append({
                "query": f"Tell me about the {name} collection",
                "expected": story_text,
            })

    for guide in fetch_care_guides() or []:
        if not isinstance(guide, dict):
            continue
        material = _str_field(guide, "material")
        instructions = _str_field(guide, "instructions", "care_instructions", "guide")
        if material and instructions:
            ground_truth.append({
                "query": f"How do I care for {material}?",
                "expected": instructions,
            })

    return ground_truth


if __name__ == "__main__":
    truth = build_ground_truth()
    print(f"Built ground truth from {len(truth)} Supabase records")
   
    for row in truth[:5]:
        print(f"  Q: {row['query']}")
        print(f"  A: {row['expected'][:60]}...\n")
