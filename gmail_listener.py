from __future__ import annotations

import email
import imaplib
import logging
import os
import re
import time
from email.header import decode_header
from email.utils import parseaddr

from dotenv import load_dotenv

from conversation_store import (
    conversation_needs_human_review,
    create_conversation,
    generate_thread_id,
    get_conversation,
    update_messages,
    update_status,
)
from email_util import send_customer_reply, send_enquiry_to_owner
from main import run_router

load_dotenv()

logger = logging.getLogger(__name__)

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
POLL_INTERVAL = 60

_THREAD_ID_RE = re.compile(
    r"\[ref:\s*([0-9a-fA-F-]{36})\]",
    re.IGNORECASE,
)


def _require_gmail_config() -> tuple[str, str]:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_USER and GMAIL_APP_PASSWORD must be set in .env")
    return GMAIL_USER, GMAIL_APP_PASSWORD


def decode_subject(raw_subject: str) -> str:
    """Convert encoded email subject to plain string."""
    parts = decode_header(raw_subject or "")
    result = ""
    for part, encoding in parts:
        if isinstance(part, bytes):
            result += part.decode(encoding or "utf-8", errors="replace")
        else:
            result += part
    return result


def extract_sender_email(from_header: str) -> str:
    """Parse 'Name <email@example.com>' into email@example.com."""
    _, addr = parseaddr(from_header or "")
    return addr.strip()


def extract_sender_name(from_header: str) -> str:
    """Parse display name from From header, or 'Customer'."""
    name, _ = parseaddr(from_header or "")
    return name.strip() or "Customer"


def _persist_conversation(
    *,
    thread_id: str,
    conversation: dict | None,
    sender_email: str,
    sender_name: str,
    initial_query: str,
    messages: list,
    needs_human_review: bool,
) -> None:
    """Insert a new row or update an existing one."""
    status = "needs_human_review" if needs_human_review else "active"
    if conversation:
        if needs_human_review:
            update_status(thread_id, status)
        update_messages(thread_id, messages)
        return

    if not create_conversation(
        thread_id=thread_id,
        email=sender_email,
        name=sender_name,
        initial_query=initial_query,
        messages=messages,
        status=status,
    ):
        logger.error("Failed to create conversation for thread %s", thread_id)
    else:
        logger.info(
            "Created conversation %s for direct email from %s",
            thread_id,
            sender_email,
        )


def extract_thread_id(subject: str) -> str | None:
    """Extract thread UUID from subject like [ref: 6a554e9a-e4ca-4544-a54c-ce54da846c8d]."""
    match = _THREAD_ID_RE.search(subject or "")
    return match.group(1) if match else None


def extract_body(msg) -> tuple[str, list[str]]:
    body = ""
    attachments: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = part.get("Content-Disposition", "") or ""

            if content_type.startswith("image/") or "attachment" in disposition:
                filename = part.get_filename() or "unknown_file"
                attachments.append(filename)
                continue

            if content_type == "text/plain" and not body:
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    body = payload.decode("utf-8", errors="replace").strip()

    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            body = payload.decode("utf-8", errors="replace").strip()

    return body, attachments


def process_email(raw_email: bytes) -> None:
    """Process a single incoming email reply."""
    msg = email.message_from_bytes(raw_email)

    subject = decode_subject(msg.get("Subject", ""))
    from_header = msg.get("From", "")
    sender_email = extract_sender_email(from_header)
    sender_name = extract_sender_name(from_header)
    body, attachments = extract_body(msg)

    if not sender_email:
        return

    sender_email = sender_email.lower()

    if GMAIL_USER and sender_email == GMAIL_USER.lower():
        return

    ref_in_subject = extract_thread_id(subject)
    if ref_in_subject:
        thread_id = ref_in_subject
    else:
        thread_id = generate_thread_id()

    conversation = get_conversation(thread_id)

    attachment_note = ""
    if attachments:
        names = ", ".join(attachments)
        attachment_note = (
            f"\n\n[Note: Customer attached: {names}. You cannot view these.]"
        )

    user_content = (body + attachment_note).strip()
    if not user_content:
        return

    if conversation_needs_human_review(conversation):
        conv = conversation
        assert conv is not None
        messages = list(conv.get("messages") or [])
        messages.append({"role": "user", "content": user_content})
        update_messages(thread_id, messages)
        customer_name = str(conv.get("name") or sender_name)
        send_enquiry_to_owner(
            customer_name,
            sender_email,
            user_content,
            thread_id=thread_id,
            reason="Follow-up on a thread awaiting human review",
        )
        logger.info(
            "Thread %s awaiting human review — saved message, owner notified",
            thread_id,
        )
        return

    messages = list((conversation or {}).get("messages") or [])
    messages.append({"role": "user", "content": user_content})

    routed = run_router(user_content, messages=messages)
    needs_human_review = routed["needs_human_review"]
    reply = routed.get("reply")

    if reply:
        messages.append({"role": "assistant", "content": reply})

    _persist_conversation(
        thread_id=thread_id,
        conversation=conversation,
        sender_email=sender_email,
        sender_name=sender_name,
        initial_query=user_content,
        messages=messages,
        needs_human_review=needs_human_review,
    )

    if needs_human_review:
        customer_name = str((conversation or {}).get("name") or sender_name)
        send_enquiry_to_owner(
            customer_name,
            sender_email,
            user_content,
            thread_id=thread_id,
            reason="New reply flagged for human review",
        )
        logger.info(
            "Thread %s flagged for human review — owner notified",
            thread_id,
        )

    if not reply:
        return

    reply_subject = f"Re: Your Babu Ceramics enquiry [ref: {thread_id}]"
    send_customer_reply(
        to=sender_email,
        subject=reply_subject,
        body=reply,
    )


def check_inbox() -> None:
    user, password = _require_gmail_config()

    with imaplib.IMAP4_SSL("imap.gmail.com") as mail:
        mail.login(user, password)
        mail.select("inbox")

        _, message_ids = mail.search(None, "UNSEEN")
        if not message_ids or not message_ids[0]:
            return

        ids = message_ids[0].split()
        for msg_id in ids:
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue

            raw = msg_data[0][1]
            if isinstance(raw, bytes):
                process_email(raw)

            mail.store(msg_id, "+FLAGS", "\\Seen")


def start_listener() -> None:
    user, _ = _require_gmail_config()
    print(f"Listening on {user}...")
    while True:
        try:
            check_inbox()
        except Exception as exc:
            logger.error("Inbox check failed: %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    start_listener()
