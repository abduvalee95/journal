"""Speech-to-text for the teacher's voice note.

Like llm.py, the provider is a setting rather than a consequence of how the
function was called: the old `_transport is not None` early-return meant no
test ever executed the Groq Whisper branch or the ElevenLabs fallback.
"""
from __future__ import annotations

import httpx

from app.config import settings

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def _provider() -> str:
    if settings.asr_provider != "auto":
        return settings.asr_provider
    model = (settings.llm_model or "").lower()
    if (settings.llm_api_key or "").startswith("gsk_") or "whisper" in model:
        return "groq"
    return "elevenlabs"


async def transcribe(
    audio_bytes: bytes,
    filename: str = "audio.oga",
    _transport: httpx.MockTransport | None = None,
) -> str:
    """Transcribe audio bytes to text.

    Args:
        audio_bytes: raw audio file bytes (OGG expected)
        filename: filename sent in the multipart payload
        _transport: optional httpx transport for testing; it decides how the
            request is carried, not which provider is called.

    Returns:
        Transcribed text.
    """
    kwargs = {"timeout": 90}
    if _transport is not None:
        kwargs["transport"] = _transport

    if _provider() == "groq":
        model = (
            settings.llm_model
            if "whisper" in (settings.llm_model or "").lower()
            else "whisper-large-v3-turbo"
        )
        url = GROQ_WHISPER_URL
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        data = {"model": model, "language": "uz"}
    else:
        url = SCRIBE_URL
        headers = {"xi-api-key": settings.elevenlabs_api_key}
        data = {"model_id": "scribe_v1", "language_code": "uzb"}

    async with httpx.AsyncClient(**kwargs) as client:
        r = await client.post(
            url,
            headers=headers,
            files={"file": (filename, audio_bytes, "audio/ogg")},
            data=data,
        )
        r.raise_for_status()
        return r.json()["text"]
