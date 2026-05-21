import os
import io
import wave
import tempfile
import subprocess
from google import genai
from typing import Optional
from google.genai import types
from meta_app_chatbot.config.settings import settings

try:
    import pygame
    import numpy as np
    from google.cloud import speech
    from google.cloud import texttospeech
except ImportError as e:
    print(f"Missing required library: {e}")
    print(
        "Install with: pip install google-cloud-texttospeech google-cloud-speech pygame sounddevice soundfile"
    )


class GoogleSpeechService:
    """
    A class to handle Google Cloud Text-to-Speech and Speech-to-Text operations.

    Requirements:
    - Google Cloud credentials (service account key or application default credentials)
    - pip install google-cloud-texttospeech google-cloud-speech pygame sounddevice soundfile
    """

    def __init__(
        self, credentials_path: Optional[str] = None, play_audio: bool = False
    ):
        """
        Initialize the Google Speech Service.

        Args:
            credentials_path: Path to Google Cloud service account JSON file.
                            If None, uses application default credentials.
        """
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        # Initialize clients
        self.tts_client = texttospeech.TextToSpeechClient()
        self.stt_client = speech.SpeechClient()
        self.gemini_client = genai.Client(api_key=settings.get("Gemini_API_KEY"))

        if play_audio:  # Initialize pygame mixer for audio playback
            pygame.mixer.init()

        # Audio recording parameters
        self.sample_rate = 16000
        self.channels = 1
        self.dtype = np.int16

    def wave_file(self, filename, pcm, channels=1, rate=24000, sample_width=2):
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm)

    def text_to_speech(
        self,
        text: str,
        output_file: Optional[str] = None,
        language_code: str = "en-US",
    ) -> bytes:
        """
        Convert text to speech using Google TTS.

        Args:
            text: Text to convert to speech
            output_file: Path to save audio file (optional)
            language_code: Language code (e.g., "en-US", "es-ES")
            voice_name: Specific voice name (optional)
            voice_gender: Voice gender ("NEUTRAL", "MALE", "FEMALE")
            audio_encoding: Audio format ("MP3", "LINEAR16", "OGG_OPUS")
            speaking_rate: Speaking rate (0.25 to 4.0)
            pitch: Voice pitch (-20.0 to 20.0)
            play_audio: Whether to play the audio immediately

        Returns:
            Audio content as bytes
        """
        response = self.gemini_client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=f"""Speak this text in a friendly, supportive tone—like you're talking to a close friend.\
                     Your voice should be warm, calm, and steady, with gentle inflections and a relaxed pace.\
                     Sound natural, approachable, and caring. Avoid sounding robotic or overly energetic.\
                     The tone should make the listener feel safe, heard,\
                     and understood—like a late-night comforting conversation with someone who genuinely cares.
                    {language_code} voice tone as you response to your friend: {text}""",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Algieba",
                        )
                    )
                ),
            ),
        )

        raw_pcm = response.candidates[0].content.parts[0].inline_data.data
        if output_file:
            self.wave_file(output_file, raw_pcm)
            print(f"Audio saved to {output_file}")
        return raw_pcm

    async def speech_to_text(
        self,
        audio_file: Optional[str] = None,
        audio_content: Optional[bytes] = None,
        uri: Optional[str] = None,
        language_code: str = "en-US",
        alternative_language_codes: Optional[list] = None,
        enable_automatic_punctuation: bool = True,
        model: str = "default",
        sample_rate: int = 16000,
    ) -> str:
        """
        Convert speech to text using Google STT.

        Args:
            audio_file: Path to audio file
            audio_content: Audio content as bytes
            uri: GCS URI to audio file
            language_code: Primary language code
            alternative_language_codes: List of other possible languages
            enable_automatic_punctuation: Enable automatic punctuation
            model: Recognition model to use

        Returns:
            Transcribed text
        """
        self.stt_client = speech.SpeechClient()

        if audio_file:
            with io.open(audio_file, "rb") as f:
                content = f.read()
        elif audio_content:
            content = audio_content
        elif uri:
            content = None
        else:
            raise ValueError(
                "Either audio_file, audio_content, or uri must be provided"
            )

        audio = (
            speech.RecognitionAudio(
                content=self.prepare_audio_for_reconiztion(
                    content, target_sample_rate=sample_rate
                )
            )
            if not uri
            else speech.RecognitionAudio(uri=uri)
        )

        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            language_code=language_code,
            alternative_language_codes=alternative_language_codes or [],
            enable_automatic_punctuation=enable_automatic_punctuation,
            model=model,
        )

        response = self.stt_client.recognize(config=config, audio=audio)

        transcripts = []
        for result in response.results:
            transcripts.append(result.alternatives[0].transcript)

        return " ".join(transcripts)

    def prepare_audio_for_reconiztion(
        self,
        audio_input,
        target_sample_rate: int = 16000,
        amplify_volume: float = 3.0,
        input_is_bytes: bool = True,
    ):
        """
        Load audio from a file path or in-memory bytes, optionally resample and amplify volume.

        Args:
            audio_input: Path to audio file (str) or audio bytes (bytes).
            target_sample_rate: Resample audio to this rate (e.g., 16000).
            amplify_volume: Amplify volume by this factor (e.g., 3.0 for 3x louder).
            input_is_bytes: Set to True if audio_input is bytes.

        Returns:
            Tuple (audio_bytes, sample_rate)
        """
        # Step 1: Save in-memory bytes to temp file if needed
        if input_is_bytes:
            with tempfile.NamedTemporaryFile(
                suffix=".mp4", delete=False, dir="./temp"
            ) as tmp:
                tmp.write(audio_input)
                tmp.flush()
                tmp_path = tmp.name
        else:
            if not os.path.exists(audio_input):
                raise FileNotFoundError(f"Audio file not found: {audio_input}")
            tmp_path = audio_input

        # Step 2: Read original sample rate

        # Step 3: Build ffmpeg command
        ffmpeg_input = tmp_path
        with tempfile.NamedTemporaryFile(
            suffix=".wav", dir="./temp", delete=False
        ) as out_tmp:
            output_path = out_tmp.name

        ffmpeg_cmd = ["ffmpeg", "-y", "-i", ffmpeg_input]

        if amplify_volume:
            ffmpeg_cmd += ["-filter:a", f"volume={amplify_volume}"]

        if target_sample_rate:
            ffmpeg_cmd += ["-ar", str(target_sample_rate)]

        ffmpeg_cmd += ["-ac", "1", output_path, "-y"]

        subprocess.run(ffmpeg_cmd, check=True)

        # Step 4: Read the processed audio back
        with open(output_path, "rb") as f:
            audio_bytes = f.read()

        # Clean up temp files
        os.remove(output_path)
        if input_is_bytes:
            os.remove(tmp_path)

        return audio_bytes

    def record_audio(
        self, duration: int = 5, output_file: Optional[str] = None
    ) -> bytes:
        """
        Record audio from microphone using sounddevice.

        Args:
            duration: Recording duration in seconds
            output_file: Path to save recorded audio (optional)

        Returns:
            Recorded audio as bytes
        """
        print(f"Recording for {duration} seconds...")

        pass

    async def speech_to_text_live(self, duration: int = 5) -> str:
        """
        Record audio from microphone and convert to text.

        Args:
            duration: Recording duration in seconds

        Returns:
            Transcribed text
        """
        audio_data = self.record_audio(duration)
        return await self.speech_to_text(audio_content=audio_data)

    async def conversation_mode(self, exit_phrase: str = "stop conversation"):
        """
        Interactive conversation mode - speak and get text responses.

        Args:
            exit_phrase: Phrase to exit conversation mode
        """
        print(f"Conversation mode started. Say '{exit_phrase}' to exit.")

        while True:
            try:
                # Record and transcribe
                print("\nListening... (5 seconds)")
                text = await self.speech_to_text_live(duration=5)

                if not text.strip():
                    print("No speech detected. Try again.")
                    continue

                print(f"You said: {text}")

                # Check for exit phrase
                if exit_phrase.lower() in text.lower():
                    print("Exiting conversation mode.")
                    break

                # Echo back the text (you can modify this to integrate with other services)
                response = f"You said: {text}"
                print(f"Response: {response}")
                self.text_to_speech(response)

            except KeyboardInterrupt:
                print("\nExiting conversation mode.")
                break
            except Exception as e:
                print(f"Error: {e}")

    def _play_audio(self, audio_content: bytes, encoding: str):
        """Play audio content using pygame."""
        try:
            # Create a temporary file to play
            temp_file = "temp_audio"
            if encoding == "MP3":
                temp_file += ".mp3"
            elif encoding == "LINEAR16":
                temp_file += ".wav"
            else:
                temp_file += ".ogg"

            with open(temp_file, "wb") as f:
                f.write(audio_content)

            # Play the audio
            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()

            # Wait for playback to finish
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)

            # Clean up temp file
            os.remove(temp_file)

        except Exception as e:
            print(f"Error playing audio: {e}")

    def get_available_voices(self, language_code: Optional[str] = None) -> list:
        """
        Get list of available voices.

        Args:
            language_code: Filter by language code (optional)

        Returns:
            List of available voices
        """
        voices = self.tts_client.list_voices()

        voice_list = []
        for voice in voices.voices:
            if language_code is None or language_code in voice.language_codes:
                voice_info = {
                    "name": voice.name,
                    "language_codes": list(voice.language_codes),
                    "gender": voice.ssml_gender.name,
                }
                voice_list.append(voice_info)

        return voice_list
