from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, cast

from supabase_client import supabase

logger = logging.getLogger(__name__)


def generate_thread_id() -> str:
    return str(uuid.uuid4())


def create_conversation(
    thread_id: str,
    email: str,
    initial_query: str,
    messages: List[Dict[str, Any]],
    name: Optional[str] = None,
    status: str = "active",
) -> bool:
    try:
        supabase.table("conversations").insert(
            {
                "thread_id": thread_id,
                "email": email.strip().lower(),
                "name": name,
                "initial_query": initial_query,
                "messages": messages,
                "status": status,
            }
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Full error: {e}")
        logger.error(f"Error type: {type(e)}")
        return False

def conversation_needs_human_review(
    conversation: Optional[Dict[str, Any]],
) -> bool:
    return bool(
        conversation and conversation.get("status") == "needs_human_review"
    )


def get_conversation_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Return the most recent conversation row for this customer email, if any."""
    try:
        result = (
            supabase.table("conversations")
            .select("*")
            .eq("email", email.strip().lower())
            .execute()
        )
        if not result.data:
            return None
        return cast(Dict[str, Any], result.data[-1])
    except Exception as e:
        logger.error("Error getting conversation by email: %s", e)
        return None


def get_conversation(thread_id: str) -> Optional[Dict[str, Any]]:
    try:
        result = (
            supabase.table("conversations")
            .select("*")
            .eq("thread_id", thread_id)
            .execute()
        )
        if not result.data:
            return None
        return cast(Dict[str, Any], result.data[0])
    except Exception as e:
        logger.error("Error getting conversation: %s", e)
        return None


def update_status(thread_id: str, status: str) -> bool:
    """Update the status column for the conversation with the given thread_id."""
    try:
        supabase.table("conversations").update({"status": status}).eq(
            "thread_id", thread_id
        ).execute()
        return True
    except Exception as e:
        logger.error(
            "Failed to update status for %s to %r: %s", thread_id, status, e
        )
        return False


def set_status(thread_id: str, status: str) -> bool:
    """Alias for update_status."""
    return update_status(thread_id, status)


def update_messages(
    thread_id: str,
    messages: List[Dict[str, Any]],
    *,
    status: Optional[str] = None,
) -> bool:
    try:
        payload: Dict[str, Any] = {"messages": messages}
        if status is not None:
            payload["status"] = status
        supabase.table("conversations").update(payload).eq(
            "thread_id", thread_id
        ).execute()
        return True
    except Exception as e:
        logger.error("Failed to update messages for %s: %s", thread_id, e)
        return False

