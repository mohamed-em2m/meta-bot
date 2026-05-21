import asyncio
import logging
import re
import traceback

from meta_app_chatbot.agent.utils import log_print

logger = logging.getLogger(__name__)


class MessageController:
    def __init__(self, pool_messages_db, firestore_factory, whatsapp, facebook):
        self.pool_messages_db = pool_messages_db
        self.firestore_factory = firestore_factory
        self.whatsapp = whatsapp
        self.facebook = facebook

    def markdown_to_facebook_chat(self, text):
        # Convert **bold** to *bold* (Messenger might render this as bold)
        text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)

        # Convert *bold* to *bold* (already valid)
        text = re.sub(r"\*(.*?)\*", r"*\1*", text)

        # Convert _italic_ to _italic_
        text = re.sub(r"_(.*?)_", r"_\1_", text)

        # Convert ~strikethrough~ to ~strikethrough~
        text = re.sub(r"~(.*?)~", r"~\1~", text)

        # Format code blocks (```) with triple backticks
        def format_code(match):
            code_content = match.group(1)
            return f"\n```\n{code_content.strip()}\n```\n"

        text = re.sub(r"```(.*?)```", format_code, text, flags=re.DOTALL)

        return text

    async def is_this_last_message(self, id, message_id):

        messages = await self.firestore_factory.get(
            self.pool_messages_db
        ).get_recent_messages(id, top=1)

        if not messages:
            return True

        latest_message_id = messages[0]["id"]

        if message_id == latest_message_id:
            return True

        log_print(
            "info",
            f" the user overwrite with id {message_id} this message and will stop this thread",
        )

        return False

    async def _send_platform_message(
        self, source: str, user_id: str, message: str
    ) -> None:
        """Send message to appropriate platform."""
        try:
            if source == "facebook":
                await self.facebook.send_text_message(
                    fb_sender_id=user_id, text=message
                )

            elif source == "whatsapp":
                await self.whatsapp.send_text_message(to=user_id, body=message)

            else:
                logger.warning(f"Unknown platform: {source}")

        except Exception as e:
            log_print("error", f"Error processing message: {traceback.format_exc()}")

            logger.error(f"Error sending message to {source}: {e}")

    async def _send_platform_attachment(
        self, source: str, user_id: str, url: str, message_type: str
    ) -> None:
        """Send message to appropriate platform."""
        try:
            if source == "facebook":
                await self.facebook.send_attachment(
                    fb_sender_id=user_id, attachment_type=message_type, url=url
                )

            elif source == "whatsapp":
                await self.whatsapp.send_image_message(to=user_id, url=url)

            else:
                logger.warning(f"Unknown platform: {source}")

        except Exception as e:
            log_print("error", f"Error processing message: {traceback.format_exc()}")

            logger.error(f"Error sending message to {source}: {e}")

    async def store_messages(
        self, db_name: str, firestore_id: str, document_id: str, message: dict
    ):
        """Stores a single message document in Firestore."""
        asyncio.create_task(
            self.firestore_factory.get(db_name).store_document(
                firestore_id, document_id, [message]
            )
        )

    async def delete_collection(self, db_name, firestore_id: str):
        asyncio.create_task(
            self.firestore_factory.get(db_name).delete_collection(firestore_id)
        )

    async def _get_conversation_context(self, firestore_id) -> tuple:
        """Retrieves conversation history and facts from the database."""
        messages = await self.firestore_factory.get(
            self.user_messages_db
        ).get_recent_messages(firestore_id, top=20)
        facts_collection = await self.firestore_factory.get(self.user_messages_db).read(
            "facts", firestore_id
        )
        facts = facts_collection.get("facts", "")
        last_collection_length = facts_collection.get("collection_length", 0)

        log_print(
            "info", f"Retrieved {len(messages)} messages and facts for {firestore_id}"
        )
        return firestore_id, messages, facts, last_collection_length

    @staticmethod
    def create_collection_id(id, source):
        return f"{id}_" + source

    @staticmethod
    def create_document_id(id, role):
        return id + f"_{role}"
