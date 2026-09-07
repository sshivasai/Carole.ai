"""
Speech-to-text and text-to-speech using OpenAI APIs.

Compatibility:
    transcribe_audio -> str, including "Error: ..." on failure
    synthesize_speech -> bytes | None

Call aclose() during application shutdown after active requests drain.
"""

from __future__ import annotations

import json
import logging
from pathlib import PurePosixPath

from core.llm.config_manager import get_key, load_config
from core.tools.network_clients import (
    APIHTTP,
    ToolNetworkError,
    bounded_number,
)

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 24 * 1024 * 1024
MAX_TTS_CHARACTERS = 4096
MAX_TTS_RESPONSE_BYTES = 20 * 1024 * 1024

AUDIO_TYPES = {
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}

# Voices supported by this service's intentionally fixed tts-1 configuration.
TTS_VOICES = frozenset(
    {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
)


class VoiceService:
    def __init__(self) -> None:
        self._http = APIHTTP(concurrency=4)
        self.api_key: str | None = None
        self.reload_config()

    def reload_config(self) -> None:
        """Reload the configured OpenAI key with environment fallback."""
        cfg = load_config()
        self.api_key = get_key(cfg, "openai", "OPENAI_API_KEY") or None

    async def aclose(self) -> None:
        await self._http.aclose()

    async def transcribe_audio(
        self,
        audio_data: bytes,
        filename: str = "audio.webm",
    ) -> str:
        """
        Transcribe a complete audio buffer with whisper-1.

        Filenames determine the upload MIME type, not the file's actual
        validity. OpenAI performs audio decoding/validation.
        """
        api_key = self.api_key
        if not api_key:
            return "Error: OPENAI_API_KEY is not configured."

        try:
            if not isinstance(audio_data, bytes) or not audio_data:
                raise ValueError("audio_data must be non-empty bytes.")
            if len(audio_data) > MAX_AUDIO_BYTES:
                raise ValueError("Audio exceeds the 24 MiB upload limit.")
            if (
                not isinstance(filename, str)
                or not filename
                or len(filename) > 255
                or any(ord(char) < 32 or ord(char) == 127 for char in filename)
            ):
                raise ValueError("Invalid audio filename.")

            # Never send a caller-provided directory path as the upload name.
            safe_name = filename.replace("\\", "/").rsplit("/", 1)[-1]
            extension = PurePosixPath(safe_name).suffix.lower()
            mime_type = AUDIO_TYPES.get(extension)
            if mime_type is None:
                raise ValueError(
                    "Unsupported audio format. Use mp3, mp4, mpeg, mpga, "
                    "m4a, wav, or webm."
                )

            response = await self._http.request(
                "POST",
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (safe_name, audio_data, mime_type)},
                data={
                    "model": "whisper-1",
                    "response_format": "json",
                },
                max_bytes=2 * 1024 * 1024,
                deadline=90.0,
            )

            try:
                payload = json.loads(response.content)
            except (ValueError, UnicodeError):
                raise ToolNetworkError(
                    "Transcription provider returned invalid JSON."
                ) from None

            if not isinstance(payload, dict) or not isinstance(
                payload.get("text"), str
            ):
                raise ToolNetworkError(
                    "Transcription provider returned an unexpected response."
                )

            return payload["text"]

        except (ValueError, ToolNetworkError) as exc:
            return f"Error: {exc}"

    async def synthesize_speech(
        self,
        text: str,
        voice: str = "alloy",
        speed: float = 1.0,
    ) -> bytes | None:
        """
        Generate MP3 audio using tts-1.

        Oversized text is rejected, not silently truncated.
        All documented failure cases return None for backward compatibility.
        """
        api_key = self.api_key
        if not api_key:
            logger.warning("TTS unavailable: OpenAI key is not configured")
            return None

        try:
            if not isinstance(text, str) or not text.strip():
                raise ValueError("text must be a non-empty string.")
            if len(text) > MAX_TTS_CHARACTERS:
                raise ValueError(
                    f"text exceeds {MAX_TTS_CHARACTERS} characters; "
                    "split it into smaller requests."
                )
            if not isinstance(voice, str) or voice not in TTS_VOICES:
                raise ValueError("Unsupported TTS voice.")

            speed = bounded_number(
                speed,
                name="speed",
                minimum=0.25,
                maximum=4.0,
            )

            response = await self._http.request(
                "POST",
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "tts-1",
                    "input": text,
                    "voice": voice,
                    "speed": speed,
                    "response_format": "mp3",
                },
                max_bytes=MAX_TTS_RESPONSE_BYTES,
                deadline=90.0,
            )

            if response.mime_type not in {
                "audio/mpeg",
                "audio/mp3",
                "application/octet-stream",
            }:
                raise ToolNetworkError(
                    "TTS provider returned an unexpected content type."
                )
            if not response.content:
                raise ToolNetworkError("TTS provider returned empty audio.")

            return response.content

        except (ValueError, ToolNetworkError) as exc:
            # These errors are locally generated and do not include submitted
            # text, audio, provider response bodies, or credentials.
            logger.warning("TTS failed: %s", exc)
            return None


voice_service = VoiceService()
