"""
Tests for Task 9's Claude structured-extraction service.

`extract_lesson(transcript, student_names) -> dict` sends the ASR transcript
and group student names to Claude, forcing a tool call, and returns the
tool's structured input dict.

Task 9's brief called for a live smoke test here (Step 6), but
`LLM_API_KEY` in backend/.env is the placeholder `test_llm_key` — a real
call cannot succeed, and it would spend real API credit besides. That step
is replaced with these tests against a mocked httpx transport, matching the
pattern established in test_asr.py: assert on the actual outgoing request
(URL, headers, body/schema/system prompt), not just on the canned response.
"""
import httpx
import pytest

from app.config import settings
from app.services.llm import extract_lesson, _SCHEMA, _SYSTEM


@pytest.mark.asyncio
async def test_extract_lesson_happy_path():
    """A realistic Anthropic tool_use response body returns the tool input dict."""
    expected_input = {
        "topic": "Present Perfect",
        "summary_public": "Bugun Present Perfect zamonini o'rgandik. Guruh yaxshi ishtirok etdi.",
        "homework": "22-betdagi mashqlarni bajarish.",
        "per_student": [
            {
                "name_mentioned": "Aziza",
                "note_public": "Aziza darsda faol ishtirok etdi.",
                "grade_suggested": 5,
                "attendance_hint": "present",
            },
            {
                "name_mentioned": "Bobur",
                "note_public": "Bobur bugungi darsda ishtirok eta olmadi.",
                "attendance_hint": "absent",
            },
        ],
    }

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "msg_01ABC",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_01XYZ",
                        "name": "extract",
                        "input": expected_input,
                    }
                ],
                "stop_reason": "tool_use",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    result = await extract_lesson(
        "Aziza juda yaxshi ishladi, besh berdim. Bobur kelmadi.",
        ["Aziza Karimova", "Bobur Toshmatov"],
        _transport=transport,
    )

    assert result == expected_input


@pytest.mark.asyncio
async def test_extract_lesson_request_shape():
    """Assert on the request the production code built, not the canned response."""
    captured_request = None
    transcript = "Aziza juda yaxshi ishladi, besh berdim. Bobur kelmadi."
    student_names = ["Aziza Karimova", "Bobur Toshmatov"]

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "tool_use",
                        "name": "extract",
                        "input": {
                            "topic": "x",
                            "summary_public": "x",
                            "per_student": [],
                        },
                    }
                ]
            },
        )

    transport = httpx.MockTransport(mock_handler)
    await extract_lesson(transcript, student_names, _transport=transport)

    assert captured_request is not None

    # URL
    assert str(captured_request.url) == "https://api.anthropic.com/v1/messages"

    # Headers
    assert captured_request.headers["x-api-key"] == settings.llm_api_key
    assert captured_request.headers["anthropic-version"] == "2023-06-01"
    assert captured_request.headers["content-type"] == "application/json"

    # Body
    import json
    body = json.loads(captured_request.content)

    assert body["model"] == settings.llm_model
    assert body["system"] == _SYSTEM

    # Transcript and student names must appear in the user message content
    assert len(body["messages"]) == 1
    user_message = body["messages"][0]
    assert user_message["role"] == "user"
    assert transcript in user_message["content"]
    for name in student_names:
        assert name in user_message["content"]

    # Tool definition: name "extract" with the brief's exact schema
    assert len(body["tools"]) == 1
    tool = body["tools"][0]
    assert tool["name"] == "extract"
    assert tool["input_schema"] == _SCHEMA

    # tool_choice forces the "extract" tool
    assert body["tool_choice"] == {"type": "tool", "name": "extract"}


@pytest.mark.asyncio
async def test_extract_lesson_error_401():
    """401 response raises httpx.HTTPStatusError, so Task 10's pipeline can
    catch it and tell the teacher to enter the lesson manually."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    transport = httpx.MockTransport(mock_handler)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await extract_lesson("transcript", ["Aziza Karimova"], _transport=transport)

    assert exc_info.value.response.status_code == 401


@pytest.mark.asyncio
async def test_extract_lesson_error_429():
    """429 (rate limited) response raises httpx.HTTPStatusError."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "Rate limited"})

    transport = httpx.MockTransport(mock_handler)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await extract_lesson("transcript", ["Aziza Karimova"], _transport=transport)

    assert exc_info.value.response.status_code == 429
