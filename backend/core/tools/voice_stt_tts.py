"""
# backend/core/tools/voice_stt_tts.py

Speech-to-Text (STT) and Text-to-Speech (TTS) using OpenAI APIs.

- transcribe_audio: Sends an audio file/buffer to OpenAI Whisper for transcription.
- synthesize_speech: Sends text to OpenAI TTS and returns raw audio bytes.
"""

import os
import httpx
from typing import Optional


class VoiceService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")

    async def transcribe_audio(self, audio_data: bytes, filename: str = "audio.webm") -> str:
        """
        Transcribes audio bytes using OpenAI Whisper API.
        Supports webm, mp3, mp4, wav, m4a formats.
        Returns the transcribed text.
        """
        if not self.api_key:
            return "Error: OPENAI_API_KEY is not configured."

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (filename, audio_data)},
                data={"model": "whisper-1"},
            )
            if response.status_code != 200:
                return f"Error: Whisper API returned {response.status_code}: {response.text}"

            result = response.json()
            return result.get("text", "")

    async def synthesize_speech(
        self, text: str, voice: str = "alloy", speed: float = 1.0
    ) -> Optional[bytes]:
        """
        Converts text to speech using OpenAI TTS API.
        Returns raw mp3 audio bytes, or None on failure.

        Voices: alloy, echo, fable, onyx, nova, shimmer
        """
        if not self.api_key:
            return None

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tts-1",
                    "input": text[:4096],  # API limit
                    "voice": voice,
                    "speed": speed,
                },
            )
            if response.status_code != 200:
                print(f"✗ [VoiceService] TTS error {response.status_code}: {response.text}")
                return None

            return response.content


# Singleton
voice_service = VoiceService()
