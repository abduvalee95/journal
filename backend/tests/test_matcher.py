"""
Tests for Task 9's rapidfuzz-based name matcher.

`match_names(mentioned, students, threshold=80) -> dict[str, int | None]`
resolves loosely-spoken names (from an LLM transcript extraction) to
student ids by fuzzy matching against the student list it is handed.
It must never fall back to a global roster — only the passed-in list.
"""
from app.services.matcher import match_names

STUDENTS = [
    {"id": 1, "full_name": "Aziza Karimova"},
    {"id": 2, "full_name": "Bobur Toshmatov"},
    {"id": 3, "full_name": "Dildora Yusupova"},
]


def test_exact_first_name():
    assert match_names(["Aziza"], STUDENTS)["Aziza"] == 1


def test_partial_name():
    assert match_names(["Bobur"], STUDENTS)["Bobur"] == 2


def test_typo():
    assert match_names(["Dildore"], STUDENTS)["Dildore"] == 3


def test_no_match():
    assert match_names(["Xurshid"], STUDENTS)["Xurshid"] is None


def test_scoped_to_passed_list():
    # Bobur not in group_a list -> None (must not fall back to a global roster)
    group_a = [{"id": 1, "full_name": "Aziza Karimova"}]
    assert match_names(["Bobur"], group_a)["Bobur"] is None


def test_empty_input():
    assert match_names([], STUDENTS) == {}


# --- Additional tests for pipeline-relevant edge cases (authorized addition #3) ---


def test_empty_students_list_does_not_crash():
    """No students in the group (e.g. new/empty group) must not raise."""
    result = match_names(["Aziza"], [])
    assert result == {"Aziza": None}


def test_case_insensitivity():
    """Transcript casing is not controlled by us (LLM output), so a
    lowercase mention must still resolve."""
    assert match_names(["aziza"], STUDENTS)["aziza"] == 1


def test_ambiguous_name_is_deterministic():
    """Two similarly-scoring students for one mentioned name: the match
    must be deterministic (same input -> same output every time), not
    merely "some" match chosen arbitrarily per-run."""
    similar_students = [
        {"id": 10, "full_name": "Aziza Karimova"},
        {"id": 11, "full_name": "Aziza Karimboyeva"},
    ]
    results = {match_names(["Aziza"], similar_students)["Aziza"] for _ in range(20)}
    assert len(results) == 1, f"match_names is non-deterministic across repeated calls: {results}"
