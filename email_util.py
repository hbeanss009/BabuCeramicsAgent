from __future__ import annotations

import html as html_lib
import logging
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from utils.style_sample import sanitize_customer_output

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)

logger = logging.getLogger(__name__)


def _gmail_credentials() -> tuple[str, str]:
    user = os.environ.get("GMAIL_USER")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if password:
        password = password.replace(" ", "")
    if not user or not password:
        raise RuntimeError(
            "GMAIL_USER and GMAIL_APP_PASSWORD must be set in .env"
        )
    return user, password


def _send_email(
    *,
    to_addr: str,
    subject: str,
    body: str,
    reply_to: Optional[str] = None,
    html_body: Optional[str] = None,
) -> None:
    """Send one email via Gmail SMTP. to_addr is whoever receives it."""
    gmail_user, gmail_password = _gmail_credentials()
    to_addr = to_addr.strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to_addr
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.attach(MIMEText(body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, [to_addr], msg.as_string())


def send_enquiry_to_owner(
    customer_name: str,
    customer_email: str,
    query: str,
    *,
    thread_id: Optional[str] = None,
    reason: str = "New enquiry",
) -> bool:
    """Email GMAIL_USER when a conversation needs human attention."""
    try:
        gmail_user, _ = _gmail_credentials()
        ref_line = f"Thread ref: {thread_id}\n" if thread_id else ""
        body = f"""
{reason}

{ref_line}Name: {customer_name}
Email: {customer_email}
Message:
{query}
""".strip()
        subject = f"[Human review] {customer_name}"
        if thread_id:
            subject = f"[Human review] [ref: {thread_id}] {customer_name}"
        _send_email(
            to_addr=gmail_user,
            subject=subject,
            body=body,
            reply_to=customer_email,
        )
        logger.info("Owner notified (%s) | thread: %s", reason, thread_id or "n/a")
        return True
    except (RuntimeError, smtplib.SMTPException) as exc:
        logger.error("Owner notification failed — %s", exc)
        return False


def _plain_from_html(text: str) -> str:
    """Minimal tag strip when the router returns HTML."""
    plain = re.sub(r"<[^>]+>", "", text)
    return html_lib.unescape(plain).strip()


def send_customer_reply(to: str, subject: str, body: str) -> bool:
    """Send reply email to the customer with a dynamic subject."""
    try:
        text = sanitize_customer_output(body.strip())
        if "<" in text:
            _send_email(
                to_addr=to,
                subject=subject,
                body=_plain_from_html(text),
                html_body=text,
            )
        else:
            _send_email(to_addr=to, subject=subject, body=text)
        logger.info("Reply sent to %s | subject: %s", to, subject)
        return True
    except RuntimeError:
        logger.error(
            "Email failed — check GMAIL_USER and GMAIL_APP_PASSWORD in .env"
        )
        return False
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Email failed — check GMAIL_USER and GMAIL_APP_PASSWORD in .env"
        )
        return False
    except smtplib.SMTPConnectError:
        logger.error("Email failed — could not connect to Gmail")
        return False
    except smtplib.SMTPException as e:
        logger.error("Email failed — %s", e)
        return False
