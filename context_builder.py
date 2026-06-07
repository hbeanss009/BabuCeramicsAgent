# context_builder.py
import os
import logging
from supabase import create_client

logger = logging.getLogger(__name__)

def _sb():
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_KEY")
    return create_client(url, key) if url and key else None

def fetch_items():
    try:
        return _sb().table("Items").select("*").execute().data
    except Exception as e:
        logger.error(f"fetch_items: {e}")
        return []

def fetch_collection_stories():
    try:
        return _sb().table("collection_stories").select("*").execute().data
    except Exception as e:
        logger.error(f"fetch_collection_stories: {e}")
        return []

def fetch_care_guides():
    try:
        return _sb().table("care_guides").select("*").execute().data
    except Exception as e:
        logger.error(f"fetch_care_guides: {e}")
        return []

def fetch_editorial_picks():
    try:
        return _sb().table("editorial_picks").select("*").execute().data
    except Exception as e:
        logger.error(f"fetch_editorial_picks: {e}")
        return []

def fetch_faqs():
    try:
        return _sb().table("faqs").select("*").execute().data
    except Exception as e:
        logger.error(f"fetch_faqs: {e}")
        return []

def fetch_artist_notes():
    try:
        return _sb().table("artist_notes").select("*").execute().data
    except Exception as e:
        logger.error(f"fetch_artist_notes: {e}")
        return []


# All Supabase tables the agent tools may ground responses in.
AGENT_SOURCE_FETCHERS = {
    "items": fetch_items,
    "collection_stories": fetch_collection_stories,
    "care_guides": fetch_care_guides,
    "editorial_picks": fetch_editorial_picks,
    "faqs": fetch_faqs,
    "artist_notes": fetch_artist_notes,
}

# Which source tables each handler is allowed to use for factual claims.
TOOL_SOURCE_MAP = {
    "item_inquiry": ("items", "care_guides", "collection_stories"),
    "collection_inquiry": ("items", "collection_stories", "faqs", "artist_notes"),
    "recommendation": ("items", "collection_stories", "editorial_picks"),
    "returns_enquiry_tool": ("faqs", "artist_notes"),
    "shipping_enquiry_tool": ("faqs", "artist_notes"),
    "custom_order_enquiry_tool": ("faqs", "artist_notes"),
}


def fetch_all_agent_sources():
    """Fetch every source table used by any agent tool."""
    return {name: fetcher() for name, fetcher in AGENT_SOURCE_FETCHERS.items()}