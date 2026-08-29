"""Fuzzy name matcher: resolves loosely-spoken student names to student ids.

Used after `extract_lesson()` (llm.py) returns a `per_student` list with
`name_mentioned` strings pulled from a voice transcript ("Aziza", "Dildore").
`match_names` resolves those against the *passed-in* student list only —
it must never guess across groups by falling back to some global roster.
"""
from __future__ import annotations

from rapidfuzz import fuzz, process, utils


def _norm(s: str) -> str:
    return str(utils.default_process(s)) if s else ""


def match_names(
    mentioned: list[str],
    students: list[dict],   # [{"id": int, "full_name": str}]
    threshold: int = 75,
) -> dict[str, int | None]:
    if not mentioned:
        return {}
    if not students:
        return {name: None for name in mentioned}

    known = {s["full_name"]: s["id"] for s in students}
    first_name_map: dict[str, list[dict]] = {}
    last_name_map: dict[str, list[dict]] = {}

    for s in students:
        parts = s["full_name"].strip().split()
        if parts:
            first_name_map.setdefault(_norm(parts[0]), []).append(s)
        if len(parts) > 1:
            last_name_map.setdefault(_norm(parts[-1]), []).append(s)

    result: dict[str, int | None] = {}
    for name in mentioned:
        if not name or not name.strip():
            result[name] = None
            continue

        norm_name = _norm(name)

        # 1. Exact full name match
        matched_id = None
        for full_name, sid in known.items():
            if _norm(full_name) == norm_name:
                matched_id = sid
                break

        # 2. Single token match (first name or last name if unique)
        if matched_id is None and " " not in name.strip():
            first_candidates = first_name_map.get(norm_name, [])
            if len(first_candidates) == 1:
                matched_id = first_candidates[0]["id"]
            elif not first_candidates:
                last_candidates = last_name_map.get(norm_name, [])
                if len(last_candidates) == 1:
                    matched_id = last_candidates[0]["id"]

        # 3. Token set ratio (handles reversed names e.g. "Karimova Aziza")
        if matched_id is None:
            hit = process.extractOne(
                name,
                known.keys(),
                scorer=fuzz.token_set_ratio,
                processor=utils.default_process,
            )
            if hit and hit[1] >= threshold:
                matched_id = known[hit[0]]

        # 4. WRatio fallback
        if matched_id is None:
            hit = process.extractOne(
                name,
                known.keys(),
                scorer=fuzz.WRatio,
                processor=utils.default_process,
            )
            if hit and hit[1] >= threshold:
                matched_id = known[hit[0]]

        result[name] = matched_id
    return result
