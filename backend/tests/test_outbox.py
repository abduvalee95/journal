"""
Verification tests for Task 7's POST /confirm endpoint and outbox worker.

The brief gives no tests for outbox.py or /confirm, so these are written from
scratch (authorized addition #2 in the task brief's corrections). They drive
POST /confirm through real HTTP (TestClient) against a real, isolated SQLite
database, asserting on actual DB rows and real rendered report text -- and
they exercise the worker's drain pass (`_drain_once`) directly against a fake
bot object, never sleeping 30 seconds to test the loop.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import issue_token
from app.config import settings
from app.db.models import Attendance, Base, Group, Lesson, Outbox, Student
from app.db.session import get_session
from app.main import app
from app.services import outbox as outbox_module
from app.services.outbox import _drain_once
from app.services.report import build_report


def _make_token(sub) -> str:
    """Mint a session token the same way the app does, so these tests break if
    the token's shape (audience, subject check) ever stops matching."""
    return issue_token(sub)


AUTH_HEADERS = {"Authorization": f"Bearer {_make_token(settings.teacher_telegram_id)}"}


@pytest.fixture
async def db(tmp_path):
    """Isolated SQLite DB wired into the app's get_session dependency, so
    every request made through TestClient in a test hits this throwaway
    database instead of backend/data/journal.db."""
    db_path = tmp_path / "test_outbox.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield session_maker
    app.dependency_overrides.pop(get_session, None)
    await engine.dispose()


@pytest.fixture
def client(db):
    # No `with` block: keeps Starlette from running the lifespan (which would
    # try to register a real Telegram webhook and start the real outbox
    # worker against the real DB), same pattern as test_lessons.py.
    return TestClient(app)


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------

async def _seed_group(db, *, weekday=1, is_active=1, name="Beginners A") -> Group:
    async with db() as s:
        g = Group(name=name, weekday=weekday, start_time="09:00", is_active=is_active)
        s.add(g)
        await s.commit()
        await s.refresh(g)
        return g


async def _seed_student(db, group_id, *, full_name="Ali Valiyev", telegram_id=1001, is_active=1) -> Student:
    async with db() as s:
        st = Student(
            group_id=group_id, full_name=full_name, telegram_id=telegram_id,
            joined_at="2026-01-01T00:00:00+06:00", is_active=is_active,
        )
        s.add(st)
        await s.commit()
        await s.refresh(st)
        return st


async def _seed_lesson(db, group_id, *, lesson_date="2026-08-10", status="draft",
                       summary_reviewed=1, **kw) -> Lesson:
    async with db() as s:
        lesson = Lesson(
            group_id=group_id, lesson_date=lesson_date, status=status,
            summary_reviewed=summary_reviewed,
            created_at="2026-08-10T09:00:00+06:00", **kw,
        )
        s.add(lesson)
        await s.commit()
        await s.refresh(lesson)
        return lesson


async def _seed_attendance(db, lesson_id, student_id, **kwargs) -> Attendance:
    async with db() as s:
        att = Attendance(lesson_id=lesson_id, student_id=student_id, **kwargs)
        s.add(att)
        await s.commit()
        await s.refresh(att)
        return att


async def _seed_outbox(db, student_id, lesson_id, **kwargs) -> Outbox:
    defaults = dict(text="hello", created_at="2026-08-10T09:00:00+06:00")
    defaults.update(kwargs)
    async with db() as s:
        row = Outbox(student_id=student_id, lesson_id=lesson_id, **defaults)
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row


# ---------------------------------------------------------------------------
# POST /api/lessons/{id}/confirm
# ---------------------------------------------------------------------------

async def test_confirm_saves_lesson_and_queues_one_outbox_row_per_active_student(client, db):
    group = await _seed_group(db)
    lesson = await _seed_lesson(
        db, group.id,
        topic="Present Perfect", homework="Workbook 42-43",
        summary_public="Bugun Present Perfect o'rgandik.",
    )
    active_student = await _seed_student(db, group.id, full_name="Ali Valiyev", telegram_id=1001)
    inactive_student = await _seed_student(db, group.id, full_name="Vali Aliyev", telegram_id=1002, is_active=0)
    att_active = await _seed_attendance(
        db, lesson.id, active_student.id, status="present", grade=4, note_public="Yaxshi ishladi.",
    )
    await _seed_attendance(db, lesson.id, inactive_student.id, status="absent")

    r = client.post(f"/api/lessons/{lesson.id}/confirm", headers=AUTH_HEADERS)
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    async with db() as s:
        refreshed_lesson = await s.get(Lesson, lesson.id)
        assert refreshed_lesson.status == "saved"
        assert refreshed_lesson.saved_at

        outbox_rows = (await s.execute(select(Outbox))).scalars().all()
        group_obj = await s.get(Group, group.id)

    # Exactly one outbox row, for the active student only.
    assert len(outbox_rows) == 1
    row = outbox_rows[0]
    assert row.student_id == active_student.id
    assert row.lesson_id == lesson.id
    assert row.status == "pending"
    assert row.attempts == 0

    expected_text = build_report(refreshed_lesson, att_active, group_obj)
    assert row.text == expected_text
    assert "Ali Valiyev" not in row.text  # report format never names the student
    assert "Present Perfect" in row.text
    assert "⭐ Баҳо: 4/5" in row.text


async def test_confirm_is_idempotent(client, db):
    group = await _seed_group(db)
    lesson = await _seed_lesson(db, group.id)
    student = await _seed_student(db, group.id)
    await _seed_attendance(db, lesson.id, student.id, status="present", grade=5)

    r1 = client.post(f"/api/lessons/{lesson.id}/confirm", headers=AUTH_HEADERS)
    assert r1.status_code == 200

    async with db() as s:
        saved_at_after_first = (await s.get(Lesson, lesson.id)).saved_at
        rows_after_first = (await s.execute(select(Outbox))).scalars().all()
    assert len(rows_after_first) == 1

    r2 = client.post(f"/api/lessons/{lesson.id}/confirm", headers=AUTH_HEADERS)
    assert r2.status_code == 200
    assert r2.json() == {"ok": True}

    async with db() as s:
        refreshed = await s.get(Lesson, lesson.id)
        rows_after_second = (await s.execute(select(Outbox))).scalars().all()

    assert refreshed.status == "saved"
    assert refreshed.saved_at == saved_at_after_first  # unchanged
    assert len(rows_after_second) == 1  # no duplicate outbox row


def test_confirm_unknown_lesson_returns_404(client, db):
    """Idempotency is about a *known* lesson already being confirmed. Returning
    200 for an id that does not exist masks a client bug instead."""
    r = client.post("/api/lessons/99999/confirm", headers=AUTH_HEADERS)
    assert r.status_code == 404


def test_confirm_requires_auth(client, db):
    r = client.post("/api/lessons/1/confirm")
    assert r.status_code == 401


async def test_confirm_skips_inactive_student_entirely(client, db):
    group = await _seed_group(db)
    lesson = await _seed_lesson(db, group.id)
    inactive_student = await _seed_student(db, group.id, telegram_id=2002, is_active=0)
    await _seed_attendance(db, lesson.id, inactive_student.id, status="present", grade=5)

    r = client.post(f"/api/lessons/{lesson.id}/confirm", headers=AUTH_HEADERS)
    assert r.status_code == 200

    async with db() as s:
        rows = (await s.execute(select(Outbox))).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# outbox worker drain pass (_drain_once) -- no sleeping, tested directly
# ---------------------------------------------------------------------------

class FakeBot:
    """A stand-in for aiogram's Bot -- a real Telegram send is impossible and
    undesirable in tests. `responses` is a list of exceptions (or None for
    success) consumed in call order, one per call to send_message."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def send_message(self, chat_id, text, parse_mode=None):
        self.calls.append((chat_id, text))
        outcome = self._responses.pop(0)
        if outcome is not None:
            raise outcome


@pytest.fixture
async def drain_db(tmp_path, monkeypatch):
    """Isolated DB wired directly into app.services.outbox.AsyncSessionLocal,
    since _drain_once uses that module-level session factory rather than a
    FastAPI dependency."""
    db_path = tmp_path / "test_outbox_drain.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(outbox_module, "AsyncSessionLocal", session_maker)

    yield session_maker
    await engine.dispose()


async def test_drain_once_marks_successful_send_as_sent(drain_db):
    group = await _seed_group(drain_db)
    lesson = await _seed_lesson(drain_db, group.id)
    student = await _seed_student(drain_db, group.id, telegram_id=5001)
    row = await _seed_outbox(drain_db, student.id, lesson.id, text="Салом!")

    bot = FakeBot(responses=[None])
    await _drain_once(bot)

    assert bot.calls == [(5001, "Салом!")]
    async with drain_db() as s:
        refreshed = await s.get(Outbox, row.id)
    assert refreshed.status == "sent"
    assert refreshed.sent_at
    assert refreshed.attempts == 0


async def test_drain_once_blocked_student_fails_immediately_no_retry(drain_db):
    group = await _seed_group(drain_db)
    lesson = await _seed_lesson(drain_db, group.id)
    student = await _seed_student(drain_db, group.id, telegram_id=5002)
    row = await _seed_outbox(drain_db, student.id, lesson.id, text="Салом!")

    forbidden = TelegramForbiddenError(method=None, message="Forbidden: bot was blocked by the user")
    bot = FakeBot(responses=[forbidden])
    await _drain_once(bot)

    async with drain_db() as s:
        refreshed = await s.get(Outbox, row.id)
    assert refreshed.status == "failed"
    assert refreshed.attempts == 0  # never counted as a retry-able attempt
    assert "Forbidden" in refreshed.last_error
    assert refreshed.sent_at is None


async def test_drain_once_generic_error_increments_attempts_and_stays_pending(drain_db):
    group = await _seed_group(drain_db)
    lesson = await _seed_lesson(drain_db, group.id)
    student = await _seed_student(drain_db, group.id, telegram_id=5003)
    row = await _seed_outbox(drain_db, student.id, lesson.id, text="Салом!")

    bot = FakeBot(responses=[RuntimeError("network blip")])
    await _drain_once(bot)

    async with drain_db() as s:
        refreshed = await s.get(Outbox, row.id)
    assert refreshed.status == "pending"
    assert refreshed.attempts == 1
    assert "network blip" in refreshed.last_error


async def test_drain_once_becomes_failed_only_after_third_attempt(drain_db):
    group = await _seed_group(drain_db)
    lesson = await _seed_lesson(drain_db, group.id)
    student = await _seed_student(drain_db, group.id, telegram_id=5004)
    row = await _seed_outbox(drain_db, student.id, lesson.id, text="Салом!")

    bot = FakeBot(responses=[RuntimeError("e1")])
    await _drain_once(bot)
    async with drain_db() as s:
        assert (await s.get(Outbox, row.id)).status == "pending"
        assert (await s.get(Outbox, row.id)).attempts == 1

    bot = FakeBot(responses=[RuntimeError("e2")])
    await _drain_once(bot)
    async with drain_db() as s:
        assert (await s.get(Outbox, row.id)).status == "pending"
        assert (await s.get(Outbox, row.id)).attempts == 2

    bot = FakeBot(responses=[RuntimeError("e3")])
    await _drain_once(bot)
    async with drain_db() as s:
        refreshed = await s.get(Outbox, row.id)
    assert refreshed.status == "failed"
    assert refreshed.attempts == 3


async def test_drain_once_only_touches_pending_rows(drain_db):
    group = await _seed_group(drain_db)
    lesson = await _seed_lesson(drain_db, group.id)
    student = await _seed_student(drain_db, group.id, telegram_id=5005)
    other_student = await _seed_student(drain_db, group.id, telegram_id=5006)
    already_sent = await _seed_outbox(
        drain_db, student.id, lesson.id, text="old", status="sent", sent_at="2026-08-10T09:00:00+06:00",
    )
    # A different student: UNIQUE(lesson_id, student_id) now allows only one
    # report per student per lesson.
    already_failed = await _seed_outbox(drain_db, other_student.id, lesson.id, text="old2", status="failed")

    bot = FakeBot(responses=[])
    await _drain_once(bot)

    assert bot.calls == []
    async with drain_db() as s:
        assert (await s.get(Outbox, already_sent.id)).status == "sent"
        assert (await s.get(Outbox, already_failed.id)).status == "failed"


# ---------------------------------------------------------------------------
# Delivery durability and failure handling (docs/audit-2026-08-14.md H2, M10)
# ---------------------------------------------------------------------------

async def test_flood_control_does_not_burn_one_of_the_three_attempts(drain_db, monkeypatch):
    """TelegramRetryAfter is Telegram telling us to slow down, not a delivery
    failure. Counting it meant three flood waits in a row -- plausible for a
    15-student batch sent with no pacing -- permanently marked a student's
    report failed and they silently never received it."""
    monkeypatch.setattr(outbox_module.asyncio, "sleep", AsyncMock())

    group = await _seed_group(drain_db)
    lesson = await _seed_lesson(drain_db, group.id)
    student = await _seed_student(drain_db, group.id, telegram_id=5101)
    row = await _seed_outbox(drain_db, student.id, lesson.id, text="hi")

    bot = FakeBot(responses=[TelegramRetryAfter(
        method=None, message="Flood control exceeded", retry_after=3,
    )])
    await _drain_once(bot)

    async with drain_db() as s:
        stored = await s.get(Outbox, row.id)
    assert stored.status == "pending"
    assert stored.attempts == 0
    assert "flood control" in stored.last_error


async def test_a_missing_student_row_fails_immediately(drain_db):
    """session.get(Student, ...) returning None used to raise AttributeError,
    which burned all three attempts before the row was marked failed."""
    group = await _seed_group(drain_db)
    lesson = await _seed_lesson(drain_db, group.id)
    row = await _seed_outbox(drain_db, 999_999, lesson.id, text="orphan")

    bot = FakeBot(responses=[])
    await _drain_once(bot)

    async with drain_db() as s:
        stored = await s.get(Outbox, row.id)
    assert stored.status == "failed"
    assert stored.attempts == 0
    assert bot.calls == []


async def test_each_row_is_committed_before_the_next_is_sent(drain_db):
    """The pass used to commit once at the end, so a crash or a shutdown
    mid-drain lost the record of every send that had already succeeded and the
    next start re-sent them all."""
    group = await _seed_group(drain_db)
    lesson = await _seed_lesson(drain_db, group.id)
    first = await _seed_student(drain_db, group.id, telegram_id=5201)
    second = await _seed_student(drain_db, group.id, telegram_id=5202)
    row1 = await _seed_outbox(drain_db, first.id, lesson.id, text="one")
    row2 = await _seed_outbox(drain_db, second.id, lesson.id, text="two")

    class CrashingBot(FakeBot):
        async def send_message(self, chat_id, text, parse_mode=None):
            if text == "two":
                raise KeyboardInterrupt("process killed mid-drain")
            return await super().send_message(chat_id, text, parse_mode)

    bot = CrashingBot(responses=[None])
    with pytest.raises(KeyboardInterrupt):
        await _drain_once(bot)

    async with drain_db() as s:
        assert (await s.get(Outbox, row1.id)).status == "sent"
        assert (await s.get(Outbox, row2.id)).status == "pending"


async def test_cancellation_mid_send_still_commits_what_is_known(drain_db):
    """asyncio.CancelledError is a BaseException, so `except Exception` never
    covered the shutdown path -- main.py cancels this task on shutdown."""
    group = await _seed_group(drain_db)
    lesson = await _seed_lesson(drain_db, group.id)
    first = await _seed_student(drain_db, group.id, telegram_id=5301)
    second = await _seed_student(drain_db, group.id, telegram_id=5302)
    row1 = await _seed_outbox(drain_db, first.id, lesson.id, text="one")
    row2 = await _seed_outbox(drain_db, second.id, lesson.id, text="two")

    class CancellingBot(FakeBot):
        async def send_message(self, chat_id, text, parse_mode=None):
            if text == "two":
                raise asyncio.CancelledError()
            return await super().send_message(chat_id, text, parse_mode)

    bot = CancellingBot(responses=[None])
    with pytest.raises(asyncio.CancelledError):
        await _drain_once(bot)

    async with drain_db() as s:
        assert (await s.get(Outbox, row1.id)).status == "sent"
        assert (await s.get(Outbox, row2.id)).status == "pending"


async def test_teacher_is_told_once_a_day_about_undelivered_reports(drain_db, monkeypatch):
    """Spec section 8. Without it a student who blocked the bot fails
    permanently and nothing in the teacher's workflow ever surfaces it."""
    monkeypatch.setattr(outbox_module, "_last_failure_summary_date", None)

    group = await _seed_group(drain_db)
    lesson = await _seed_lesson(drain_db, group.id)
    student = await _seed_student(drain_db, group.id, telegram_id=5401)
    await _seed_outbox(drain_db, student.id, lesson.id, text="x", status="failed")

    bot = FakeBot(responses=[None])
    await outbox_module._report_failures_daily(bot)
    assert bot.calls, "teacher was never told"
    assert "1" in bot.calls[0][1]

    # Once a day, not once every 30 seconds.
    bot2 = FakeBot(responses=[None])
    await outbox_module._report_failures_daily(bot2)
    assert bot2.calls == []


async def test_no_daily_summary_when_nothing_failed(drain_db, monkeypatch):
    monkeypatch.setattr(outbox_module, "_last_failure_summary_date", None)
    bot = FakeBot(responses=[])
    await outbox_module._report_failures_daily(bot)
    assert bot.calls == []
