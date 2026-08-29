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


def _extract_multipart_fields(request: httpx.Request) -> dict:
    """Parse multipart form data from request and return field name -> value dict.

    Extracts the boundary from Content-Type header and splits the body accordingly.
    Returns a dict where:
    - form fields (data) have str -> str mapping
    - file fields have str -> (filename, bytes) mapping
    """
    content_type = request.headers.get("content-type", "")
    if "boundary=" not in content_type:
        raise ValueError("No boundary found in Content-Type header")

    boundary = content_type.split("boundary=")[-1].strip()
    if boundary.startswith('"') and boundary.endswith('"'):
        boundary = boundary[1:-1]

    fields = {}
    # Split by boundary, excluding the first preamble and last epilogue
    parts = request.content.split(f"--{boundary}".encode())

    for part in parts[1:-1]:  # Skip first (empty) and last (--) parts
        if not part or part == b"--\r\n" or part == b"--":
            continue

        # Split headers from body
        try:
            header_section, body = part.split(b"\r\n\r\n", 1)
        except ValueError:
            continue

        # Remove trailing CRLF from body
        body = body.rstrip(b"\r\n")

        # Parse Content-Disposition header
        header_text = header_section.decode("utf-8", errors="ignore")
        lines = header_text.split("\r\n")

        field_name = None
        filename = None

        for line in lines:
            if line.startswith("Content-Disposition:"):
                # Extract name and filename from Content-Disposition
                if 'name="' in line:
                    name_start = line.index('name="') + 6
                    name_end = line.index('"', name_start)
                    field_name = line[name_start:name_end]

                if 'filename="' in line:
                    fn_start = line.index('filename="') + 10
                    fn_end = line.index('"', fn_start)
                    filename = line[fn_start:fn_end]

        if field_name:
            if filename:
                # File field: store (filename, bytes)
                fields[field_name] = (filename, body)
            else:
                # Form field: store as string
                fields[field_name] = body.decode("utf-8", errors="ignore")

    return fields


@pytest.mark.asyncio
async def test_transcribe_happy_path():
    """Happy path: 200 response with {"text": "..."} returns the text.

    Also asserts that the request was properly formed (URL, headers, multipart fields),
    not just that the response parsing works.
    """
    audio_bytes = b"fake audio data"
    expected_text = "Salom, bugun Present Perfect o'rgandik."
    captured_request = None

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"text": expected_text})

    transport = httpx.MockTransport(mock_handler)
    result = await transcribe(audio_bytes, _transport=transport)

    # Assert response parsing
    assert result == expected_text

    # Assert request shape
    assert captured_request is not None
    assert str(captured_request.url) == "https://api.elevenlabs.io/v1/speech-to-text"
    assert captured_request.headers["xi-api-key"] == settings.elevenlabs_api_key

    # Assert multipart form fields
    fields = _extract_multipart_fields(captured_request)
    assert fields["model_id"] == "scribe_v1"
    assert fields["language_code"] == "uzb"
    assert "file" in fields
    filename, file_bytes = fields["file"]
    assert filename == "audio.oga"
    assert file_bytes == audio_bytes


@pytest.mark.asyncio
async def test_transcribe_request_shape():
    """Assert the request URL, headers, and multipart fields are exactly correct."""
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

    # Assert multipart form fields by name and value
    fields = _extract_multipart_fields(captured_request)
    assert fields["model_id"] == "scribe_v1", f"Expected model_id='scribe_v1', got {fields['model_id']}"
    assert fields["language_code"] == "uzb", f"Expected language_code='uzb', got {fields['language_code']}"
    assert "file" in fields, f"Expected 'file' field in form, got fields: {fields.keys()}"

    # Assert file field contains custom filename and audio bytes
    stored_filename, stored_bytes = fields["file"]
    assert stored_filename == filename, f"Expected filename='{filename}', got '{stored_filename}'"
    assert stored_bytes == audio_bytes, "Audio bytes mismatch"


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
    """Custom filename parameter is used in the multipart file field."""
    audio_bytes = b"fake audio data"
    custom_filename = "voice.oga"
    captured_request = None

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"text": "Transcribed"})

    transport = httpx.MockTransport(mock_handler)
    await transcribe(audio_bytes, filename=custom_filename, _transport=transport)

    # Assert custom filename is in the file field
    assert captured_request is not None
    fields = _extract_multipart_fields(captured_request)
    assert "file" in fields
    stored_filename, stored_bytes = fields["file"]
    assert stored_filename == custom_filename, f"Expected filename='{custom_filename}', got '{stored_filename}'"
    assert stored_bytes == audio_bytes


@pytest.mark.asyncio
async def test_transcribe_groq_whisper(monkeypatch):
    """Groq Whisper provider request shape and prompt support."""
    monkeypatch.setattr(settings, "asr_provider", "groq")
    monkeypatch.setattr(settings, "llm_api_key", "gsk_test123")

    captured_request = None

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"text": "Transcribed Uzbek text"})

    transport = httpx.MockTransport(mock_handler)
    res = await transcribe(
        b"fake audio",
        prompt="Aziza, Bobur, Present Simple",
        _transport=transport,
    )

    assert res == "Transcribed Uzbek text"
    assert str(captured_request.url) == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert captured_request.headers["authorization"] == "Bearer gsk_test123"

    fields = _extract_multipart_fields(captured_request)
    assert fields["model"] == "whisper-large-v3-turbo"
    assert fields["language"] == "uz"
    assert fields["prompt"] == "Aziza, Bobur, Present Simple"
