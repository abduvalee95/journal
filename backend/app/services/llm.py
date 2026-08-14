"""Claude-based structured extraction of lesson data from a voice transcript.

`extract_lesson()` sends the ASR transcript (Task 8) plus the group's
student names to Claude, forcing a tool call so the response is
structured JSON matching `_SCHEMA`. Task 10 feeds this into `match_names()`
(matcher.py) to resolve `per_student[].name_mentioned` to real student ids.

`summary_public` and each `per_student[].note_public` are student-facing:
they get sent to students verbatim, so `_SYSTEM`'s rules on neutral,
non-critical, non-comparative language are requirements, not decoration.
"""
from __future__ import annotations

import json
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


def _is_groq() -> bool:
    return settings.llm_api_key.startswith("gsk_") or "llama" in (settings.llm_model or "").lower() or "whisper" in (settings.llm_model or "").lower()


def _is_gemini() -> bool:
    model = (settings.llm_model or "").lower()
    return "gemini" in model or settings.llm_api_key.startswith("AIza") or settings.llm_api_key.startswith("AQ.")


def _gemini_model_name() -> str:
    model = (settings.llm_model or "").lower()
    if model in ("gemini", "gemini-flash", "gemini-latest", "gemini-pro"):
        return "gemini-3.7-flash"
    if model.startswith("models/"):
        return model.replace("models/", "")
    return settings.llm_model


async def extract_lesson(
    transcript: str,
    student_names: list[str],
    _transport: httpx.MockTransport | None = None,
) -> dict:
    """Extract structured lesson data from a transcript via Groq, Claude or Gemini.

    Args:
        transcript: ASR transcript of the teacher's voice note (Task 8 output)
        student_names: full names of students in this group, for name grounding
        _transport: Optional httpx.MockTransport for testing (internal use only)

    Returns:
        Dict matching `_SCHEMA` (topic, summary_public, homework, per_student)
    """
    user_content = (
        f"Transcript:\n{transcript}\n\n"
        f"Students in this group: {', '.join(student_names)}"
    )

    kwargs = {"timeout": 60}
    if _transport is not None:
        kwargs["transport"] = _transport

    # Groq high-speed extraction
    if _is_groq() and _transport is None:
        url = "https://api.groq.com/openai/v1/chat/completions"
        groq_model = "llama-3.3-70b-versatile"
        prompt_with_schema = f"{_SYSTEM}\nReturn a valid JSON object matching this schema:\n{json.dumps(_SCHEMA)}"
        payload = {
            "model": groq_model,
            "messages": [
                {"role": "system", "content": prompt_with_schema},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(**kwargs) as client:
            r = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            return json.loads(text)

    # Gemini extraction
    if _is_gemini() and _transport is None:
        model_name = _gemini_model_name()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={settings.llm_api_key}"
        payload = {
            "system_instruction": {
                "parts": [{"text": _SYSTEM}]
            },
            "contents": [{
                "parts": [{"text": user_content}]
            }],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": _SCHEMA
            }
        }
        async with httpx.AsyncClient(**kwargs) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)

    # Anthropic Claude extraction (default & test transport)
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
