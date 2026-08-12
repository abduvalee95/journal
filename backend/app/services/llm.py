"""Claude-based structured extraction of lesson data from a voice transcript.

`extract_lesson()` sends the ASR transcript (Task 8) plus the group's
student names to Claude, forcing a tool call so the response is
structured JSON matching `_SCHEMA`. Task 10 feeds this into `match_names()`
(matcher.py) to resolve `per_student[].name_mentioned` to real student ids.

`summary_public` and each `per_student[].note_public` are student-facing:
they get sent to students verbatim, so `_SYSTEM`'s rules on neutral,
non-critical, non-comparative language are requirements, not decoration.
"""
import httpx

from app.config import settings

_URL = "https://api.anthropic.com/v1/messages"

_SCHEMA = {
    "type": "object",
    "properties": {
        "topic":          {"type": "string"},
        "summary_public": {"type": "string"},
        "homework":       {"type": "string"},
        "per_student": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name_mentioned":  {"type": "string"},
                    "note_public":     {"type": "string"},
                    "grade_suggested": {"type": "integer", "minimum": 1, "maximum": 5},
                    "attendance_hint": {"type": "string", "enum": ["present","absent","late"]},
                },
                "required": ["name_mentioned", "attendance_hint"],
            },
        },
    },
    "required": ["topic", "summary_public", "per_student"],
}

_SYSTEM = """You are a teacher's assistant. Extract structured lesson data from a voice note transcript.
Rules:
- summary_public: 2-3 neutral sentences, NO criticism, NO student comparisons.
- note_public: one supportive sentence per student; soften any harsh language.
- grade_suggested: integer 1-5 only; omit if not clearly stated.
- Return JSON matching the tool schema exactly."""


async def extract_lesson(
    transcript: str,
    student_names: list[str],
    _transport: httpx.MockTransport | None = None,
) -> dict:
    """Extract structured lesson data from a transcript via Claude tool use.

    Args:
        transcript: ASR transcript of the teacher's voice note (Task 8 output)
        student_names: full names of students in this group, for name grounding
        _transport: Optional httpx.MockTransport for testing (internal use only)

    Returns:
        Dict matching `_SCHEMA` (topic, summary_public, homework, per_student)

    Raises:
        httpx.HTTPStatusError: If the API returns an error status code
    """
    user_content = (
        f"Transcript:\n{transcript}\n\n"
        f"Students in this group: {', '.join(student_names)}"
    )

    kwargs = {"timeout": 60}
    if _transport is not None:
        kwargs["transport"] = _transport

    async with httpx.AsyncClient(**kwargs) as client:
        r = await client.post(
            _URL,
            headers={
                "x-api-key":         settings.llm_api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":       settings.llm_model,
                "max_tokens":  1024,
                "system":      _SYSTEM,
                "messages":    [{"role": "user", "content": user_content}],
                "tools":       [{"name": "extract", "input_schema": _SCHEMA}],
                "tool_choice": {"type": "tool", "name": "extract"},
            },
        )
        r.raise_for_status()
        return r.json()["content"][0]["input"]
