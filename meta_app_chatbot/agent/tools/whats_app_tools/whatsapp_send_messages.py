import os
import httpx
from meta_app_chatbot.agent.utils import log_print
from typing import Optional, List


class WhatsAppClient:
    def __init__(
        self, access_token: str, phone_number_id: str, api_version: str = "v21.0"
    ):
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def send_text_message(self, to: str, body: str, preview_url: bool = False):
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": preview_url, "body": body},
        }
        async with httpx.AsyncClient() as client:
            log_print(f"Sending message to {to}")
            response = await client.post(
                self.base_url, headers=self.headers, json=payload
            )

            log_print(f"Message body: {response.json()}")

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[List[dict]] = None,
    ):
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {"name": template_name, "language": {"code": language_code}},
        }
        if components:
            payload["template"]["components"] = components
        async with httpx.AsyncClient() as client:
            return await client.post(self.base_url, headers=self.headers, json=payload)

    async def send_image_message(
        self, to: str, image_link: str, caption: Optional[str] = None
    ):
        image_obj = {"link": image_link}
        if caption:
            image_obj["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": image_obj,
        }
        async with httpx.AsyncClient() as client:
            return await client.post(self.base_url, headers=self.headers, json=payload)

    async def send_document_message(
        self, to: str, document_link: str, filename: str, caption: Optional[str] = None
    ):
        document_obj = {"link": document_link, "filename": filename}
        if caption:
            document_obj["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "document",
            "document": document_obj,
        }
        async with httpx.AsyncClient() as client:
            return await client.post(self.base_url, headers=self.headers, json=payload)

    async def send_location_message(
        self,
        to: str,
        latitude: float,
        longitude: float,
        name: Optional[str] = None,
        address: Optional[str] = None,
    ):
        location_obj = {"latitude": latitude, "longitude": longitude}
        if name:
            location_obj["name"] = name
        if address:
            location_obj["address"] = address
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "location",
            "location": location_obj,
        }
        async with httpx.AsyncClient() as client:
            return await client.post(self.base_url, headers=self.headers, json=payload)

    async def send_reaction_message(self, to: str, message_id: str, emoji: str):
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "reaction",
            "reaction": {"message_id": message_id, "emoji": emoji},
        }
        async with httpx.AsyncClient() as client:
            return await client.post(self.base_url, headers=self.headers, json=payload)

    async def send_reply_message(
        self, to: str, message_id: str, body: str, preview_url: bool = False
    ):
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "context": {"message_id": message_id},
            "type": "text",
            "text": {"preview_url": preview_url, "body": body},
        }
        async with httpx.AsyncClient() as client:
            return await client.post(self.base_url, headers=self.headers, json=payload)


whatsapp = WhatsAppClient(
    os.getenv("WHATSAPP_ACCESS_TOKEN"), os.getenv("WHATSAPP_PHONE_NUMBER_ID"), "v22.0"
)
