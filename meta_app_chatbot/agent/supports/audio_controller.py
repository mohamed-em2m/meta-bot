import re
import uuid
import time
import httpx
import asyncio
import logging
from meta_app_chatbot.agent.utils import *
from meta_app_chatbot.config.settings import settings

logger = logging.getLogger(__name__)


class AudioController:
    def __init__(self, sound_controller):
        self.sound_controller = sound_controller

    def prepare_text_for_tts(self, text: str) -> str:
        """
        Cleans input text for TTS by removing all special characters.
        Keeps only:
        - English letters (A-Z, a-z)
        - Arabic letters (ء to ي and other common forms)
        - Digits (0-9)
        - Spaces

        Args:
            text (str): The input text to be cleaned.

        Returns:
            str: Cleaned text suitable for TTS.
        """

        cleaned_text = re.sub(r"[^\u0600-\u06FFA-Za-z0-9\s]", "", text)
        cleaned_text = re.sub(r"\s+", " ", cleaned_text)  # normalize multiple spaces
        return cleaned_text.strip()

    def generate_audio_path(self):
        audio_id = uuid.uuid4().hex + f"_{time.time()}".replace(".", "_") + ".wav"

        temp_audio_path = f"{settings.get('temp_folder')}/{audio_id}"
        url = settings.get("audio_url") + "?path=" + audio_id
        return temp_audio_path, url

    async def download_sound(self, url: str):
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url)
                response.raise_for_status()  # Raise an error for bad responses
                return response.content
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error while downloading sound: {e}")
            except Exception as e:
                logger.error(f"Error downloading sound: {e}")

    def _pack_for_tts(self, text: str, max_bytes: int = 900) -> list[str]:
        """
        Splits text on sentences, then packs sentences into chunks that approach `max_bytes` without exceeding it.
        """

        # Split text into sentences
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []

        current = ""
        for sent in sentences:
            segment = sent.strip()
            if not segment:
                continue

            # If individual sentence too large, split by whitespace
            if len(segment.encode("utf-8")) > max_bytes:
                # Fallback: split into smaller parts by whitespace
                words = re.split(r"(\s+)", segment)
                piece = ""
                for w in words:
                    if len((piece + w).encode("utf-8")) <= max_bytes:
                        piece += w
                    else:
                        chunks.append(piece.strip())
                        piece = w
                if piece.strip():
                    chunks.append(piece.strip())
                continue

            # Try to append to current chunk
            if current:
                candidate = (
                    f"{current} {segment}"
                    if not current.endswith((" ", "\n"))
                    else f"{current}{segment}"
                )
            else:
                candidate = segment

            if len(candidate.encode("utf-8")) <= max_bytes:
                current = candidate
            else:
                # Flush current and start new
                chunks.append(current)
                current = segment

        # Append last buffer
        if current:
            chunks.append(current)

        return chunks

    async def _transcribe_audio_from_url(self, url: str) -> str | None:
        """Downloads and transcribes audio from a URL into text, with timeout & retries."""

        # First, download
        audio_bytes = await self.download_sound(url)
        if not audio_bytes:
            logger.error("Aborting transcription because download failed.")
            return None

        # Now attempt transcription up to 3 times, each with a 5s timeout
        for attempt in range(1, 4):
            try:
                text = await asyncio.wait_for(
                    self.sound_controller.speech_to_text(
                        audio_content=audio_bytes,
                        model="default",
                        alternative_language_codes=[
                            "ar-EG",
                            "ar-IQ",
                            "ar-SA",
                            "fr-FR",
                            "de-DE",
                            "en-US",
                        ],
                        sample_rate=16000,
                    ),
                    timeout=5,
                )

                return text

            except asyncio.TimeoutError:
                logger.warning(
                    f"Transcription attempt {attempt} timed out after 5 seconds."
                )
            except Exception as e:
                logger.error(f"Transcription attempt {attempt} failed: {e!r}")

        logger.error("All 3 transcription attempts failed or timed out.")
        return None

    async def send_audio(
        self, text_parts: list[str] | str, source: str, user_id: str, lang: str
    ) -> None:
        """
        Splits input text into maximum-sized safe TTS chunks, generates audio, and sends each chunk sequentially.
        Handles both single strings and lists of strings.
        """
        if not text_parts:
            logger.warning("Cannot generate audio from empty text.")
            return

        # Normalize input to a list
        parts = [text_parts] if isinstance(text_parts, str) else text_parts

        lang_code = lang
        voice_name = f"{lang_code}-Chirp3-HD-Algieba"
        logger.info(
            f"Preparing to send audio to user {user_id}, {len(parts)} part(s) total."
        )

        for idx, content in enumerate(parts, start=1):
            if not content.strip():
                logger.warning(f"Skipping empty text part {idx}.")
                continue

            # Split and pack content into optimal chunks <= max_bytes
            for chunk in self._pack_for_tts(content):
                try:
                    temp_path, public_url = self.generate_audio_path()
                    logger.debug(f"Synthesizing chunk (part {idx}): '{chunk[:50]}...' ")

                    # Generate speech
                    await self.generate_audio(chunk, temp_path, lang_code, voice_name)

                    await self._send_platform_attachment(
                        source, user_id, public_url, "audio"
                    )
                    logger.info(f"Sent audio chunk for part {idx}.")

                except Exception as e:
                    logger.error(f"Failed on part {idx} chunk: {e}")

    async def generate_audio(
        self, chunk: str, temp_path: str, lang_code: str, voice_name: str
    ):
        try:
            print(chunk)
            self.sound_controller.text_to_speech(
                self.prepare_text_for_tts(chunk),
                temp_path,
                language_code=lang_code,
                voice_name=voice_name,
            )

            return True

        except Exception as e:
            logger.error(f"Failed on generate audio {e}")

            return False
