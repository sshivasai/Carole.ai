import pytest
from core.tools.voice_stt_tts import VoiceService, TTS_VOICES


@pytest.mark.asyncio
async def test_voice_service_missing_api_key():
    svc = VoiceService()
    svc.api_key = None

    res_stt = await svc.transcribe_audio(b"audio data", "audio.wav")
    assert "Error: OPENAI_API_KEY is not configured." in res_stt

    res_tts = await svc.synthesize_speech("hello")
    assert res_tts is None
    await svc.aclose()


@pytest.mark.asyncio
async def test_voice_service_payload_limits():
    svc = VoiceService()
    svc.api_key = "sk-fake-test-key"

    # Non-bytes audio
    res = await svc.transcribe_audio("not-bytes", "audio.wav")
    assert "Error:" in res and "bytes" in res

    # Oversized audio > 24 MiB
    oversized_audio = b"0" * (25 * 1024 * 1024)
    res_large = await svc.transcribe_audio(oversized_audio, "audio.wav")
    assert "Error:" in res_large and "exceeds" in res_large

    # Unsupported audio format
    res_mime = await svc.transcribe_audio(b"fake-audio", "video.unknown")
    assert "Error:" in res_mime and "Unsupported audio format" in res_mime

    # Oversized text > 4096 chars returns None
    long_text = "A" * 5000
    res_text = await svc.synthesize_speech(long_text)
    assert res_text is None

    # Invalid voice returns None
    res_voice = await svc.synthesize_speech("Hello", voice="unknown_voice_123")
    assert res_voice is None

    await svc.aclose()


def test_tts_voices_set():
    assert "alloy" in TTS_VOICES
    assert "nova" in TTS_VOICES
    assert "shimmer" in TTS_VOICES
