"""
Tests for Task 8's ElevenLabs Scribe ASR service.

`transcribe(audio_bytes, filename) -> str` sends audio to ElevenLabs and
returns the transcribed text. Tests use httpx.MockTransport to inject
controlled responses and assert on the exact request shape (URL, headers,
multipart payload).
"""
import httpx
import pytest

from app.config import settings
from app.services.asr import transcribe


@pytest.mark.asyncio
async def test_transcribe_happy_path():
    """Happy path: 200 response with {"text": "..."} returns the text."""
    audio_bytes = b"fake audio data"
    expected_text = "Salom, bugun Present Perfect o'rgandik."

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"text": expected_text},
        )

    transport = httpx.MockTransport(mock_handler)
    result = await transcribe(audio_bytes, _transport=transport)

    assert result == expected_text


@pytest.mark.asyncio
async def test_transcribe_request_shape():
    """Assert the request went to the correct URL with correct headers and payload."""
    audio_bytes = b"fake audio data"
    filename = "lesson_recording.ogg"
    captured_request = None

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request

        return httpx.Response(200, json={"text": "Transcribed text"})

    transport = httpx.MockTransport(mock_handler)
    await transcribe(audio_bytes, filename=filename, _transport=transport)

    # Assert URL
    assert captured_request is not None
    assert str(captured_request.url) == "https://api.elevenlabs.io/v1/speech-to-text"

    # Assert header
    assert captured_request.headers["xi-api-key"] == settings.elevenlabs_api_key

    # Assert multipart payload: model_id and language_code in data
    # httpx encodes these into the multipart body
    content = captured_request.content.decode("utf-8", errors="ignore")
    assert "scribe_v1" in content
    assert "uzb" in content
    assert filename in content or "lesson_recording" in content
    assert audio_bytes in captured_request.content


@pytest.mark.asyncio
async def test_transcribe_error_401():
    """401 response raises httpx.HTTPStatusError."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    transport = httpx.MockTransport(mock_handler)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await transcribe(b"audio", _transport=transport)

    assert exc_info.value.response.status_code == 401


@pytest.mark.asyncio
async def test_transcribe_error_500():
    """500 response raises httpx.HTTPStatusError."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Internal server error"})

    transport = httpx.MockTransport(mock_handler)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await transcribe(b"audio", _transport=transport)

    assert exc_info.value.response.status_code == 500


@pytest.mark.asyncio
async def test_transcribe_custom_filename():
    """Custom filename parameter is used in the multipart payload."""
    audio_bytes = b"fake audio data"
    custom_filename = "voice.oga"
    captured_request = None

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request

        return httpx.Response(200, json={"text": "Transcribed"})

    transport = httpx.MockTransport(mock_handler)
    await transcribe(audio_bytes, filename=custom_filename, _transport=transport)

    # Filename should appear in the multipart boundary
    assert captured_request is not None
    content = captured_request.content.decode("utf-8", errors="ignore")
    assert "voice.oga" in content or custom_filename in content
