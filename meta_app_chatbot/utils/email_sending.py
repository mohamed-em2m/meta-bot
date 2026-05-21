"""
Email notification utilities.

Send flow
---------
1. Primary  — Gmail SMTP (SSL, app-password auth)
2. Fallback — Resend API, triggered only when Gmail fails
"""

from __future__ import annotations

import asyncio
import html
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional, Tuple, Union

import resend
from config import CONFIG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_recipients(value: Union[str, list[str]]) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


def _build_recipients() -> list[str]:
    recipients = _normalize_recipients(CONFIG.NOTIFICATION_EMAILS)
    if not recipients:
        raise ValueError("CONFIG.NOTIFICATION_EMAILS is empty.")
    return recipients


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------


def create_ads_notification(
    action_type: str,
    campaign_id: str,
    message: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Return (html_body, plain_body) for an ads notification."""

    def fmt(v: Any) -> str:
        return html.escape(str(v))

    html_parts = [
        "<div style='font-family:Arial,sans-serif;line-height:1.6;'>",
        "<h2>📢 Ads System Notification</h2>",
        f"<p><strong>Action:</strong> {fmt(action_type)}</p>",
        f"<p><strong>Campaign:</strong> {fmt(campaign_id)}</p>",
    ]
    text_parts = [
        "📢 Ads System Notification",
        f"Action: {action_type}",
        f"Campaign: {campaign_id}",
    ]

    if message:
        html_parts.append(f"<p><strong>Message:</strong> {fmt(message)}</p>")
        text_parts.append(f"Message: {message}")

    if old_value is not None and new_value is not None:
        html_parts.append(
            f"<p><strong>Change:</strong> {fmt(old_value)} → {fmt(new_value)}</p>"
        )
        text_parts.append(f"Change: {old_value} → {new_value}")

    if extra:
        html_parts.append("<p><strong>Details:</strong></p><ul>")
        text_parts.append("Details:")
        for key, value in extra.items():
            html_parts.append(f"<li><strong>{fmt(key)}:</strong> {fmt(value)}</li>")
            text_parts.append(f"- {key}: {value}")
        html_parts.append("</ul>")

    html_parts.append(
        "<hr>"
        "<p style='color:#666;font-size:12px;'>"
        "This is an automated notification from your Ads Management System."
        "</p></div>"
    )
    text_parts.append(
        "— This is an automated notification from your Ads Management System."
    )

    return "\n".join(html_parts), "\n".join(text_parts)


# ---------------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------------


def _send_via_gmail(subject: str, html_body: str, plain_body: str) -> None:
    sender = CONFIG.NOTIFICATION_EMAILS[0]
    recipients = _build_recipients()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, CONFIG.APP_PASSWORD)
        server.send_message(msg)


async def _send_via_gmail_async(subject: str, html_body: str, plain_body: str) -> bool:
    try:
        await asyncio.to_thread(_send_via_gmail, subject, html_body, plain_body)
        return True
    except Exception as exc:
        logger.warning("Gmail SMTP failed: %s", exc)
        return False


def _send_via_resend(subject: str, html_body: str) -> None:
    if not CONFIG.RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY is not configured.")

    recipients = _build_recipients()
    resend.api_key = CONFIG.RESEND_API_KEY

    result = resend.Emails.send(
        {
            "from": f"meta ads manager <{CONFIG.NOTIFICATION_EMAILS[0]}>",
            "to": recipients,
            "subject": subject,
            "html": html_body,
        }
    )

    if not result:
        raise RuntimeError("Resend returned an empty response.")

    logger.debug("Email sent via Resend: %s", result)


async def _send_via_resend_async(subject: str, html_body: str) -> bool:
    try:
        await asyncio.to_thread(_send_via_resend, subject, html_body)
        return True
    except Exception as exc:
        logger.error("Resend fallback failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def send_notification(
    subject: str,
    html_body: str,
    plain_body: str = "",
) -> bool:
    """Send an email. Falls back to Resend if Gmail SMTP fails."""
    if not plain_body:
        plain_body = "This email requires an HTML-compatible viewer."

    if await _send_via_gmail_async(subject, html_body, plain_body):
        return True

    logger.warning("Gmail failed. Trying Resend fallback.")
    return await _send_via_resend_async(subject, html_body)


async def send_message(
    action_type: str,
    campaign_id: str,
    message: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    """Build and send an ads notification email."""
    try:
        html_body, plain_body = create_ads_notification(
            action_type=action_type,
            campaign_id=campaign_id,
            message=message,
            old_value=old_value,
            new_value=new_value,
            extra=extra,
        )
        subject = f"[Ads] {action_type} - {campaign_id}"
        return await send_notification(subject, html_body, plain_body)
    except Exception:
        logger.exception("send_message: notification delivery failed")
        return False
