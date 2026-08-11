"""
TDD tests for Task 7's report builder.

`build_report(lesson, attendance, group) -> str` renders one Uzbek-Cyrillic
report per student. It must never leak teacher-private text: `lessons.raw_note`
(the raw voice transcript) and `attendance.note_private` are teacher-only, and
the enforcement mechanism is that build_report only ever reads a fixed set of
public fields off the objects it's given.

The six tests below (test_full_present through test_raw_note_not_in_report)
are pinned verbatim from the task brief -- exact Uzbek-Cyrillic strings,
emoji, and the "⭐ Баҳо: N/5" form must not be restyled. test_private_fields_
never_leak_even_when_present is an addition (authorized beyond the brief) that
proves the mechanism itself, rather than just the absence of a literal string.
"""
from types import SimpleNamespace

from app.services.report import build_report


def make(lesson_kw=None, att_kw=None, group_kw=None):
    # NOTE: the brief's own helper wrote `SimpleNamespace(topic="...", **lesson_kw)`,
    # which raises `TypeError: got multiple values for keyword argument` the moment
    # a kw dict overrides a key that's also passed as an explicit keyword (i.e. on
    # every test below except test_full_present). Fixed here by merging into a
    # plain dict first, then unpacking once. Every pinned assertion in the tests
    # below is unchanged -- only this mechanical bug in the fixture is corrected.
    lesson_defaults = dict(
        lesson_date="2026-08-11",
        topic="Present Perfect",
        summary_public="Bugun Present Perfect o'rgandik.",
        homework="Workbook 42-43",
    )
    lesson_defaults.update(lesson_kw or {})
    lesson = SimpleNamespace(**lesson_defaults)

    att_defaults = dict(status="present", grade=4, note_public="Yaxshi ishladi.")
    att_defaults.update(att_kw or {})
    att = SimpleNamespace(**att_defaults)

    group_defaults = dict(name="Beginners A")
    group_defaults.update(group_kw or {})
    group = SimpleNamespace(**group_defaults)

    return build_report(lesson, att, group)


def test_full_present():
    text = make()
    assert "Beginners A" in text
    assert "11 август 2026" in text
    assert "Present Perfect" in text
    assert "✅ Келдингиз" in text
    assert "⭐ Баҳо: 4/5" in text
    assert "Yaxshi ishladi" in text
    assert "Workbook 42-43" in text


def test_absent_no_grade():
    text = make(att_kw={"status": "absent", "grade": None, "note_public": None})
    assert "❌ Келмадингиз" in text
    assert "Баҳо" not in text


def test_late_shows_emoji():
    text = make(att_kw={"status": "late", "grade": 3, "note_public": None})
    assert "🕐 Кеч келдингиз" in text
    assert "⭐ Баҳо: 3/5" in text


def test_empty_note_omitted():
    text = make(att_kw={"note_public": None})
    assert "💬" not in text


def test_empty_homework_omitted():
    text = make(lesson_kw={"homework": None})
    assert "Уй вазифаси" not in text


def test_raw_note_not_in_report():
    # NOTE: the brief's literal input here was `topic="SECRET raw_note content"`.
    # But `topic` is a legitimately public, rendered field (see "Мавзу: {topic}"
    # in build_report), so that string guarantees the substring "raw_note"
    # appears in the output -- this fails even against the brief's own
    # reference implementation, regardless of whether private fields leak.
    # Rephrased so the injected string can't defeat itself; the assertion and
    # intent (raw_note is not a field build_report reads) are unchanged. See
    # test_private_fields_never_leak_even_when_present below for the version
    # of this check that actually exercises the enforcement mechanism.
    text = make(lesson_kw={"topic": "Maxfiy mavzu"})
    # raw_note is not a field passed to build_report -- test that it takes only public fields
    assert "raw_note" not in text


def test_private_fields_never_leak_even_when_present():
    """Stronger version of test_raw_note_not_in_report: construct a lesson
    that DOES carry a raw_note attribute (as the real ORM object will, once
    Task 10 adds voice transcription) and an attendance that DOES carry
    note_private, both holding distinctive secret text, and prove build_report
    never surfaces either -- because it never reads those attributes at all,
    not because the caller happened to omit them."""
    lesson = SimpleNamespace(
        lesson_date="2026-08-11",
        topic="Present Perfect",
        summary_public="Bugun Present Perfect o'rgandik.",
        homework="Workbook 42-43",
        raw_note="TEACHER_ONLY_TRANSCRIPT_zzz919 talked about Ali being disruptive",
    )
    att = SimpleNamespace(
        status="present",
        grade=4,
        note_public="Yaxshi ishladi.",
        note_private="TEACHER_ONLY_PRIVATE_qqq818 parents are divorcing",
    )
    group = SimpleNamespace(name="Beginners A")

    text = build_report(lesson, att, group)

    assert "TEACHER_ONLY_TRANSCRIPT_zzz919" not in text
    assert "TEACHER_ONLY_PRIVATE_qqq818" not in text
