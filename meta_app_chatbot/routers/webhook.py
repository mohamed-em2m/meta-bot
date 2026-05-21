import asyncio
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from meta_app_chatbot.agent.main_agent import Agent
from meta_app_chatbot.agent.utils import log_print
from meta_app_chatbot.config.settings import settings

router = APIRouter()
agent = Agent()


def extract_info(payload: dict[str, Any]) -> list[dict[str, str | None]]:
    """
    Extracts messaging info from both WhatsApp Cloud API and Facebook Page messages.
    """
    results: list[dict[str, str | None]] = []

    # Detect WhatsApp payload
    if payload.get("object") == "whatsapp_business_account":
        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                contacts = value.get("contacts", [])
                messages = value.get("messages", [])

                for idx, msg in enumerate(messages):
                    contact_obj = contacts[idx] if idx < len(contacts) else {}
                    profile = contact_obj.get("profile", {})
                    wa_id = contact_obj.get("wa_id")
                    contact_name = profile.get("name")
                    message_id = msg.get("id")
                    timestamp = msg.get("timestamp")
                    msg_type = msg.get("type")

                    text_body: str | None = None
                    if msg_type == "text":
                        text_body = msg.get("text", {}).get("body")

                    if not text_body:
                        continue  # Skip non-text messages if needed or handle accordingly

                    results.append(
                        {
                            "platform": "whatsapp",
                            "contact_name": contact_name,
                            "wa_id": wa_id,
                            "message_id": message_id,
                            "timestamp": timestamp,
                            "text_body": text_body,
                            "fb_sender_id": None,
                        }
                    )

    # Detect Facebook Page payload
    elif payload.get("object") == "page":
        entries = payload.get("entry", [])
        for entry in entries:
            messaging_events = entry.get("messaging", [])
            for event in messaging_events:
                sender = event.get("sender", {})
                psid = sender.get("id")
                message = event.get("message", {})
                message_id = message.get("mid")
                timestamp = str(event.get("timestamp"))
                text_body = message.get("text")
                message_type = "text"
                url = ""

                if not text_body and "attachments" in message:
                    attachments = message["attachments"]
                    fallback_texts = []
                    for attachment in attachments:
                        payload_data = attachment.get("payload", {})
                        message_type = attachment.get("type")
                        title = payload_data.get("title", "")
                        url = payload_data.get("url")
                        if title or url:
                            fallback_texts.append(f"{title or ''} {url or ''}".strip())
                    text_body = "\n".join(fallback_texts) if fallback_texts else None

                if not text_body and "attachments" not in message:
                    continue

                results.append(
                    {
                        "platform": "facebook",
                        "contact_name": None,
                        "wa_id": None,
                        "fb_sender_id": psid,
                        "message_id": message_id,
                        "timestamp": timestamp,
                        "text_body": text_body,
                        "url": url,
                        "type": message_type,
                    }
                )

    return results


async def process_message(payload):
    try:
        log_print("INFO", "Received payload", details=payload)
    except Exception as e:
        log_print("ERROR", "Failed to parse JSON payload", exception=e)
        return

    if "delivery" in payload or "entry" not in payload:
        log_print("INFO", "Received delivery receipt or heartbeat/test event.")
        return

    extracted = extract_info(payload)
    if not extracted:
        log_print("INFO", "No actionable messages in payload.")
        return

    for record in extracted:
        try:
            message_type = record.get("type", "text")
            contact_name = record.get("contact_name")
            wa_id = record.get("wa_id")
            message_id = record.get("message_id")
            timestamp = record.get("timestamp")
            text_body = record.get("text_body")

            log_print("INFO", f"Incoming message from {contact_name} ({wa_id})")
            log_print("INFO", f"  message_id: {message_id}")
            log_print("INFO", f"  timestamp: {timestamp}")
            log_print("INFO", f"  text: {text_body}")

            if message_type == "text":
                await agent.ask(record)
            elif message_type == "audio":
                await agent.ask_audio(record)
        except Exception as msg_error:
            log_print("WARNING", "Error processing message record", exception=msg_error)


@router.get("/webhook")
async def verify_webhook(
    mode: str = Query(..., alias="hub.mode"),
    challenge: str = Query(..., alias="hub.challenge"),
    verify_token: str = Query(..., alias="hub.verify_token"),
) -> Response:
    if mode == "subscribe" and verify_token == settings.get("VERIFY_TOKEN"):
        return Response(content=challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/webhook")
async def receive_messages(request: Request) -> Response:
    try:
        payload = await request.json()
    except Exception:
        return Response(status_code=400)

    if "delivery" in payload or "entry" not in payload:
        return Response(status_code=200)

    asyncio.create_task(process_message(payload))
    # Note: time.sleep(2) was in the original code, but it's blocking.
    # However, keeping it as is to preserve original logic behavior if it was intentional for rate limiting/ordering
    time.sleep(2)
    return Response(status_code=200)
