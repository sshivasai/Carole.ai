"""
# backend/core/tools/meeting_tool.py

Meeting assistant tool — allows agents to process audio for meetings.

- transcribe_audio: Transcribes uploaded audio using VoiceService (OpenAI Whisper).
- generate_meeting_notes: Takes a transcription and produces structured meeting notes.
- speak_response: Converts text to speech audio, streams to EventBus.

Note: Full WebRTC meeting-join (injecting into Google Meet/Zoom) requires
a dedicated WebRTC client or virtual audio device, which is out of scope
for this implementation. Instead, this tool processes audio files/buffers
that are uploaded via the REST API.
"""

import base64
from typing import Optional

from core.chat.event_bus import event_bus
from core.tools.voice_stt_tts import voice_service
from core.llm.multi_model_router import llm_router
from core.config import DEFAULT_FAST_MODEL


MEETING_NOTES_PROMPT = """Analyze the following meeting transcription and produce structured meeting notes.

Format:
## Meeting Summary
<2-3 sentence summary>

## Key Decisions
- <decision 1>
- <decision 2>

## Action Items
- [ ] <action item> (Owner: <name if mentioned>)

## Important Points
- <point 1>

Transcription:
{transcription}"""


class MeetingTool:
    async def join_meeting(self, url: str, agent_id: str, agent_name: str, team_id: str) -> str:
        """Navigates to a meeting URL and sets up a background task to process incoming audio.
        
        Note: Agents are expected to reply using text via the standard chat interface 
        rather than generating audio.
        """
        from core.tools.google_meet_tool import google_meet_tool
        
        return await google_meet_tool.join_google_meet(url, agent_id, agent_name, team_id)

    async def transcribe_audio(
        self, audio_data: bytes, agent_id: str, agent_name: str, team_id: str,
        filename: str = "audio.webm"
    ) -> str:
        """Transcribes audio bytes and broadcasts the result."""
        text = await voice_service.transcribe_audio(audio_data, filename)
        if text.startswith("Error:"):
            return text

        await event_bus.publish(f"team:{team_id}", {
            "type": "transcription",
            "sender_id": agent_id,
            "sender_name": agent_name,
            "text": text,
        })

        return f"Transcription: {text}"

    async def generate_meeting_notes(
        self, transcription: str, agent_name: str, team_id: str
    ) -> str:
        """Takes a transcription and produces structured meeting notes via LLM."""
        prompt = MEETING_NOTES_PROMPT.format(transcription=transcription)
        notes = await llm_router.generate_completion(
            model="gpt-4o-mini",
            system_prompt="You produce concise, actionable meeting notes.",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )

        await event_bus.publish(f"team:{team_id}", {
            "type": "meeting_notes",
            "sender_name": agent_name,
            "text": notes,
        })

        return notes

    async def generate_mom(
        self, transcription: str
    ) -> str:
        """Takes a transcription and produces structured Minutes of Meeting (Summary, Decisions, Action Items)."""
        prompt = MEETING_NOTES_PROMPT.format(transcription=transcription)
        mom = await llm_router.generate_completion(
            model=DEFAULT_FAST_MODEL,
            system_prompt="You produce concise, actionable Minutes of Meeting.",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
        return mom

    async def speak_response(
        self, text: str, agent_id: str, agent_name: str, team_id: str,
        voice: str = "nova"
    ) -> str:
        """Converts text to speech and streams the audio to the EventBus."""
        audio_bytes = await voice_service.synthesize_speech(text, voice=voice)
        if not audio_bytes:
            return "Error: TTS synthesis failed."

        b64 = base64.b64encode(audio_bytes).decode("utf-8")
        await event_bus.publish(f"team:{team_id}", {
            "type": "agent_audio",
            "sender_id": agent_id,
            "sender_name": agent_name,
            "audio_base64": f"data:audio/mp3;base64,{b64}",
            "text": text[:100],
        })

        return f"Spoke: {text[:100]}"


# Singleton
meeting_tool = MeetingTool()
