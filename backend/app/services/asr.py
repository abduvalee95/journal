from __future__ import annotations

import httpx

from app.config import settings

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


async def transcribe(
    audio_bytes: bytes,
    filename: str = "audio.oga",
    _transport: httpx.MockTransport | None = None,
) -> str:
    """Transcribe audio bytes to text using ElevenLabs or Groq Whisper API.

    Args:
        audio_bytes: Raw audio file bytes (OGG format expected)
        filename: Filename to send in multipart payload (default: "audio.oga")
        _transport: Optional httpx.MockTransport for testing (internal use only)

    Returns:
        Transcribed text from the audio
    """
    kwargs = {"timeout": 90}
    if _transport is not None:
        kwargs["transport"] = _transport
        async with httpx.AsyncClient(**kwargs) as client:
            r = await client.post(
                SCRIBE_URL,
                headers={"xi-api-key": settings.elevenlabs_api_key},
                files={"file": (filename, audio_bytes, "audio/ogg")},
                data={"model_id": "scribe_v1", "language_code": "uzb"},
            )
            r.raise_for_status()
            return r.json()["text"]

    # Use Groq Whisper if Groq API key is present or model is whisper
    is_groq = settings.llm_api_key.startswith("gsk_") or "whisper" in settings.llm_model.lower()
    if is_groq:
        whisper_model = settings.llm_model if "whisper" in settings.llm_model.lower() else "whisper-large-v3-turbo"
        async with httpx.AsyncClient(**kwargs) as client:
            r = await client.post(
                GROQ_WHISPER_URL,
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                files={"file": (filename, audio_bytes, "audio/ogg")},
                data={"model": whisper_model, "language": "uz"},
            )
            r.raise_for_status()
            return r.json()["text"]

    # Fallback to ElevenLabs
    async with httpx.AsyncClient(**kwargs) as client:
        r = await client.post(
            SCRIBE_URL,
            headers={"xi-api-key": settings.elevenlabs_api_key},
            files={"file": (filename, audio_bytes, "audio/ogg")},
            data={"model_id": "scribe_v1", "language_code": "uzb"},
        )
        r.raise_for_status()
        return r.json()["text"]
