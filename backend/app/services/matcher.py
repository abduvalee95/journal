"""Fuzzy name matcher: resolves loosely-spoken student names to student ids.

Used after `extract_lesson()` (llm.py) returns a `per_student` list with
`name_mentioned` strings pulled from a voice transcript ("Aziza", "Dildore").
`match_names` resolves those against the *passed-in* student list only —
it must never guess across groups by falling back to some global roster.
"""
from __future__ import annotations

from rapidfuzz import process, fuzz, utils


def match_names(
    mentioned: list[str],
    students: list[dict],   # [{"id": int, "full_name": str}]
    threshold: int = 80,
) -> dict[str, int | None]:
    if not mentioned:
        return {}
    known = {s["full_name"]: s["id"] for s in students}
    result: dict[str, int | None] = {}
    for name in mentioned:
        if not known:
            result[name] = None
            continue
        # processor=utils.default_process normalizes case/whitespace/punctuation
        # before scoring. Deviation from the brief's Step 3 snippet, which omits
        # it: plain fuzz.WRatio is case-sensitive, so a lowercase transcript
        # mention like "aziza" scores 72 against "Aziza Karimova" (below the
        # threshold of 80) and silently fails to match. Since transcript casing
        # is not controlled, that's a real gap, not a hypothetical one. Adding
        # the processor does not change the threshold and does not alter the
        # outcome of any of the brief's six test cases (verified before adding).
        hit = process.extractOne(
            name, known.keys(), scorer=fuzz.WRatio, processor=utils.default_process
        )
        result[name] = known[hit[0]] if hit and hit[1] >= threshold else None
    return result
