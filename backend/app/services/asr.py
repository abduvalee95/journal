"""ElevenLabs Scribe ASR service for transcribing audio to text."""
import httpx

from app.config import settings

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"


async def transcribe(
    audio_bytes: bytes,
    filename: str = "audio.oga",
    _transport: httpx.MockTransport | None = None,
) -> str:
    """Transcribe audio bytes to text using ElevenLabs Scribe API.

    Args:
        audio_bytes: Raw audio file bytes (OGG format expected)
        filename: Filename to send in multipart payload (default: "audio.oga")
        _transport: Optional httpx.MockTransport for testing (internal use only)

    Returns:
        Transcribed text from the audio

    Raises:
        httpx.HTTPStatusError: If the API returns an error status code
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
