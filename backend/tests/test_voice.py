"""
Verification tests for Task 10: voice handler, AI pipeline, SSE stream.

The brief's own verification step (send a real voice note to the bot over
ngrok, then inspect data/journal.db) needs a live bot token plus real
ElevenLabs/Anthropic keys, so these tests drive the same code paths directly:
the real handler and the real `_pipeline` against a real (isolated) SQLite
database, with only the two network boundaries -- `transcribe` /
`extract_lesson` -- and the aiogram Bot replaced.

`app.services.events.sse_queues` is process-global, so `clean_sse_queues`
below keeps one test's leftovers out of the next.
"""
import asyncio
import io
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.db.models import Base, Group, Student, Lesson, Attendance, AiJob
import app.bot.handlers.voice as voice
from app.bot.handlers.confirm import cb_confirm, cb_edit
from app.api.lessons import _event_stream, stream_lesson
from app.services.events import sse_queues

# 2026-08-10 is a Monday (isoweekday 1), matching the seeded group below.
FIXED_DATE = "2026-08-10"
FIXED_WEEKDAY = 1

TEACHER_ID = settings.teacher_telegram_id
NOT_TEACHER_ID = TEACHER_ID + 12345

# What the LLM is stubbed to return unless a test overrides it.
DRAFT = {
    "topic": "Present Perfect",
    "summary_public": "Бугун Present Perfect ўргандик.",
    "homework": "Workbook 42-43",
    "per_student": [
        {
            "name_mentioned": "Aziza",
            "note_public": "Aziza яхши ишлади.",
            "grade_suggested": 5,
            "attendance_hint": "present",
        },
        {
            "name_mentioned": "Bobur",
            "note_public": "Bobur дарсда бўлмади.",
            "attendance_hint": "absent",
        },
    ],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_sse_queues():
    sse_queues.clear()
    yield
    sse_queues.clear()


@pytest.fixture
async def db(tmp_path, monkeypatch):
    """Throwaway SQLite wired into the voice handler in place of the shared
    AsyncSessionLocal, so nothing here touches backend/data/journal.db.
    `today`/`weekday` are patched in the voice namespace (imported by name)
    to pin the run to FIXED_DATE."""
    db_path = tmp_path / "test_voice.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(voice, "AsyncSessionLocal", session_maker)
    monkeypatch.setattr(voice, "today", lambda: FIXED_DATE)
    monkeypatch.setattr(voice, "weekday", lambda: FIXED_WEEKDAY)

    yield session_maker

    await engine.dispose()


async def seed_group_and_students(db, *, weekday=FIXED_WEEKDAY, is_active=1):
    async with db() as s:
        group = Group(name="Beginners A", weekday=weekday, start_time="09:00", is_active=is_active)
        s.add(group)
        await s.commit()
        await s.refresh(group)
        s.add_all([
            Student(group_id=group.id, full_name="Aziza Karimova",
                    telegram_id=5001, joined_at="2026-08-01T09:00:00", is_active=1),
            Student(group_id=group.id, full_name="Bobur Toshmatov",
                    telegram_id=5002, joined_at="2026-08-01T09:00:00", is_active=1),
        ])
        await s.commit()
        students = (await s.execute(
            select(Student).where(Student.group_id == group.id).order_by(Student.id)
        )).scalars().all()
        return group, students


async def seed_lesson(db, group_id, *, status="draft") -> Lesson:
    async with db() as s:
        lesson = Lesson(group_id=group_id, lesson_date=FIXED_DATE, status=status,
                        created_at="2026-08-10T09:00:00")
        s.add(lesson)
        await s.commit()
        await s.refresh(lesson)
        return lesson


def fake_bot() -> SimpleNamespace:
    return SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="voice/file_1.oga")),
        download_file=AsyncMock(return_value=io.BytesIO(b"fake-ogg-bytes")),
        send_message=AsyncMock(),
    )


def voice_message(telegram_id: int, *, bot=None, file_id="voice-file-1", chat_id=777):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=telegram_id),
        voice=SimpleNamespace(file_id=file_id),
        chat=SimpleNamespace(id=chat_id),
        bot=bot or fake_bot(),
        answer=AsyncMock(),
    )


def stub_pipeline(monkeypatch) -> list:
    """Replace _pipeline with a recorder so handler tests stay off the network
    but the real asyncio.create_task scheduling is still exercised."""
    calls = []

    async def _recorder(*args):
        calls.append(args)

    monkeypatch.setattr(voice, "_pipeline", _recorder)
    return calls


def stub_ai(monkeypatch, *, transcript="Aziza yaxshi ishladi. Bobur kelmadi.", draft=None,
            transcribe_error=None, llm_error=None):
    async def _transcribe(audio_bytes, *a, **kw):
        if transcribe_error:
            raise transcribe_error
        return transcript

    async def _extract(transcript_arg, student_names, *a, **kw):
        if llm_error:
            raise llm_error
        return DRAFT if draft is None else draft

    monkeypatch.setattr(voice, "transcribe", _transcribe)
    monkeypatch.setattr(voice, "extract_lesson", _extract)


# ---------------------------------------------------------------------------
# handle_voice
# ---------------------------------------------------------------------------

async def test_non_teacher_voice_is_ignored(db, monkeypatch):
    await seed_group_and_students(db)
    calls = stub_pipeline(monkeypatch)

    msg = voice_message(NOT_TEACHER_ID)
    await voice.handle_voice(msg)

    msg.answer.assert_not_awaited()
    assert calls == []
    async with db() as s:
        assert (await s.execute(select(Lesson))).scalars().all() == []


async def test_no_group_today_answers_and_creates_nothing(db, monkeypatch):
    # Group exists but on another weekday, so today has no lesson.
    await seed_group_and_students(db, weekday=FIXED_WEEKDAY + 1)
    calls = stub_pipeline(monkeypatch)

    msg = voice_message(TEACHER_ID)
    await voice.handle_voice(msg)

    msg.answer.assert_awaited_once_with("Бугун дарс гуруҳ топилмади.")
    assert calls == []
    async with db() as s:
        assert (await s.execute(select(Lesson))).scalars().all() == []


async def test_teacher_voice_creates_lesson_and_schedules_pipeline(db, monkeypatch):
    group, students = await seed_group_and_students(db)
    calls = stub_pipeline(monkeypatch)

    msg = voice_message(TEACHER_ID, file_id="voice-abc", chat_id=4242)
    await voice.handle_voice(msg)
    await asyncio.sleep(0)  # let the created task run the recorder

    msg.answer.assert_awaited_once_with("⏳ Овоз қайта ишланмоқда...")

    async with db() as s:
        lesson = await s.scalar(select(Lesson).where(Lesson.lesson_date == FIXED_DATE))
    assert lesson is not None
    assert lesson.group_id == group.id
    assert lesson.audio_file_id == "voice-abc"
    assert lesson.status == "draft"

    assert len(calls) == 1
    _bot, lesson_id, file_id, names, student_map, chat_id = calls[0]
    assert lesson_id == lesson.id
    assert file_id == "voice-abc"
    assert names == [st.full_name for st in students]
    assert student_map == [{"id": st.id, "full_name": st.full_name} for st in students]
    assert chat_id == 4242


async def test_pipeline_task_is_referenced_until_it_finishes(db, monkeypatch):
    """Without a strong reference, asyncio can garbage-collect the in-flight
    pipeline task and the draft silently never appears."""
    await seed_group_and_students(db)

    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_pipeline(*args):
        started.set()
        await release.wait()

    monkeypatch.setattr(voice, "_pipeline", _slow_pipeline)

    await voice.handle_voice(voice_message(TEACHER_ID))
    await started.wait()
    assert len(voice._background_tasks) == 1
    task = next(iter(voice._background_tasks))

    release.set()
    await task
    await asyncio.sleep(0)  # let the done-callback run
    assert voice._background_tasks == set()


async def test_second_voice_note_reuses_same_lesson(db, monkeypatch):
    await seed_group_and_students(db)
    stub_pipeline(monkeypatch)

    await voice.handle_voice(voice_message(TEACHER_ID, file_id="voice-1"))
    await voice.handle_voice(voice_message(TEACHER_ID, file_id="voice-2"))
    await asyncio.sleep(0)

    async with db() as s:
        lessons = (await s.execute(select(Lesson))).scalars().all()
    assert len(lessons) == 1  # UNIQUE(group_id, lesson_date) respected
    assert lessons[0].audio_file_id == "voice-2"


# ---------------------------------------------------------------------------
# _pipeline
# ---------------------------------------------------------------------------

async def _run_pipeline(db, monkeypatch, *, lesson=None, bot=None, chat_id=777, **stub_kw):
    group, students = (None, None)
    if lesson is None:
        group, students = await seed_group_and_students(db)
        lesson = await seed_lesson(db, group.id)
    stub_ai(monkeypatch, **stub_kw)
    bot = bot or fake_bot()
    async with db() as s:
        students = (await s.execute(select(Student).order_by(Student.id))).scalars().all()
    student_map = [{"id": st.id, "full_name": st.full_name} for st in students]
    await voice._pipeline(
        bot, lesson.id, "voice-file-1",
        [st.full_name for st in students], student_map, chat_id,
    )
    return lesson, students, bot


async def test_pipeline_happy_path_writes_draft(db, monkeypatch):
    lesson, students, bot = await _run_pipeline(db, monkeypatch)
    aziza, bobur = students

    async with db() as s:
        stored = await s.get(Lesson, lesson.id)
        rows = (await s.execute(
            select(Attendance).where(Attendance.lesson_id == lesson.id)
            .order_by(Attendance.student_id)
        )).scalars().all()
        job = await s.scalar(select(AiJob).where(AiJob.lesson_id == lesson.id))

    assert stored.raw_note == "Aziza yaxshi ishladi. Bobur kelmadi."
    assert stored.topic == "Present Perfect"
    assert stored.summary_public == "Бугун Present Perfect ўргандик."
    assert stored.homework == "Workbook 42-43"
    assert stored.status == "draft"

    assert [r.student_id for r in rows] == [aziza.id, bobur.id]
    assert (rows[0].status, rows[0].grade) == ("present", 5)
    assert rows[0].note_public == "Aziza яхши ишлади."
    assert (rows[1].status, rows[1].grade) == ("absent", None)

    assert job.status == "done"
    assert job.stage == "llm"
    assert job.duration_ms is not None and job.duration_ms >= 0
    assert job.error is None

    bot.get_file.assert_awaited_once_with("voice-file-1")
    bot.download_file.assert_awaited_once_with("voice/file_1.oga")
    sent = bot.send_message.await_args.args[1]
    assert sent == "✅ Қоралама тайёр — Mini App'да кўринг"


async def test_pipeline_reports_unmatched_names(db, monkeypatch):
    draft = {
        **DRAFT,
        "per_student": [
            DRAFT["per_student"][0],
            {"name_mentioned": "Xurshid", "attendance_hint": "present", "grade_suggested": 4},
        ],
    }
    lesson, students, bot = await _run_pipeline(db, monkeypatch, draft=draft)

    async with db() as s:
        rows = (await s.execute(
            select(Attendance).where(Attendance.lesson_id == lesson.id)
        )).scalars().all()
    assert [r.student_id for r in rows] == [students[0].id]  # nothing for Xurshid

    sent = bot.send_message.await_args.args[1]
    assert "⚠️ Топилмаган исмлар: Xurshid" in sent


async def test_pipeline_upserts_existing_attendance(db, monkeypatch):
    group, students = await seed_group_and_students(db)
    lesson = await seed_lesson(db, group.id)
    aziza = students[0]
    async with db() as s:  # teacher already saved something manually
        s.add(Attendance(lesson_id=lesson.id, student_id=aziza.id,
                         status="absent", grade=2, note_public="qo'lda"))
        await s.commit()

    await _run_pipeline(db, monkeypatch, lesson=lesson)

    async with db() as s:
        rows = (await s.execute(
            select(Attendance).where(Attendance.lesson_id == lesson.id,
                                     Attendance.student_id == aziza.id)
        )).scalars().all()
    assert len(rows) == 1  # updated in place, no UNIQUE violation
    assert (rows[0].status, rows[0].grade) == ("present", 5)
    assert rows[0].note_public == "Aziza яхши ишлади."


async def test_pipeline_rejects_out_of_range_grade(db, monkeypatch):
    draft = {
        **DRAFT,
        "per_student": [{**DRAFT["per_student"][0], "grade_suggested": 7}],
    }
    lesson, students, bot = await _run_pipeline(db, monkeypatch, draft=draft)

    async with db() as s:
        row = await s.scalar(select(Attendance).where(Attendance.lesson_id == lesson.id))
        job = await s.scalar(select(AiJob).where(AiJob.lesson_id == lesson.id))
    assert row.grade is None  # CHECK(grade BETWEEN 1 AND 5) never gets a chance to fire
    assert row.status == "present"
    assert job.status == "done"


async def test_pipeline_falls_back_to_present_on_bad_attendance_hint(db, monkeypatch):
    draft = {
        **DRAFT,
        "per_student": [{**DRAFT["per_student"][0], "attendance_hint": "maybe"}],
    }
    lesson, _students, _bot = await _run_pipeline(db, monkeypatch, draft=draft)

    async with db() as s:
        row = await s.scalar(select(Attendance).where(Attendance.lesson_id == lesson.id))
    assert row.status == "present"


async def test_pipeline_handles_missing_per_student(db, monkeypatch):
    draft = {"topic": "Reading", "summary_public": "Ўқиш машқлари."}
    lesson, _students, bot = await _run_pipeline(db, monkeypatch, draft=draft)

    async with db() as s:
        stored = await s.get(Lesson, lesson.id)
        rows = (await s.execute(
            select(Attendance).where(Attendance.lesson_id == lesson.id)
        )).scalars().all()
    assert stored.topic == "Reading"
    assert stored.homework is None
    assert rows == []
    assert bot.send_message.await_args.args[1] == "✅ Қоралама тайёр — Mini App'да кўринг"


async def test_pipeline_leaves_saved_lesson_untouched(db, monkeypatch):
    group, _students = await seed_group_and_students(db)
    lesson = await seed_lesson(db, group.id, status="saved")
    async with db() as s:
        stored = await s.get(Lesson, lesson.id)
        stored.topic = "Manually confirmed topic"
        await s.commit()

    _lesson, _students2, bot = await _run_pipeline(db, monkeypatch, lesson=lesson)

    async with db() as s:
        stored = await s.get(Lesson, lesson.id)
        rows = (await s.execute(
            select(Attendance).where(Attendance.lesson_id == lesson.id)
        )).scalars().all()
        job = await s.scalar(select(AiJob).where(AiJob.lesson_id == lesson.id))

    assert stored.topic == "Manually confirmed topic"
    assert stored.summary_public is None
    assert stored.status == "saved"
    assert rows == []
    assert job.status == "done"
    assert bot.send_message.await_args.args[1] == (
        "ℹ️ Бу дарс аллақачон сақланган, ўзгартирилмади."
    )


async def test_pipeline_records_asr_failure(db, monkeypatch):
    lesson, _students, bot = await _run_pipeline(
        db, monkeypatch, transcribe_error=RuntimeError("scribe exploded")
    )

    async with db() as s:
        job = await s.scalar(select(AiJob).where(AiJob.lesson_id == lesson.id))
        stored = await s.get(Lesson, lesson.id)
    assert job.status == "error"
    assert job.stage == "asr"
    # Redacted: exception text can carry the request URL, and a provider
    # that authenticates by query string would put its key in the backup.
    assert job.error == "RuntimeError"
    assert "scribe exploded" not in job.error
    assert job.duration_ms is not None
    assert stored.raw_note is None
    assert bot.send_message.await_args.args[1] == "❌ AI ишламади, қўлда киритинг"


async def test_pipeline_records_llm_failure_after_transcript_is_saved(db, monkeypatch):
    lesson, _students, bot = await _run_pipeline(
        db, monkeypatch, llm_error=RuntimeError("claude exploded")
    )

    async with db() as s:
        job = await s.scalar(select(AiJob).where(AiJob.lesson_id == lesson.id))
        stored = await s.get(Lesson, lesson.id)
    assert job.status == "error"
    assert job.stage == "llm"
    assert job.error == "RuntimeError"
    # transcript survives the LLM failure so the teacher's words are not lost
    assert stored.raw_note == "Aziza yaxshi ishladi. Bobur kelmadi."
    assert bot.send_message.await_args.args[1] == "❌ AI ишламади, қўлда киритинг"


async def test_pipeline_notifies_sse_listener(db, monkeypatch):
    group, _students = await seed_group_and_students(db)
    lesson = await seed_lesson(db, group.id)
    queue: asyncio.Queue = asyncio.Queue()
    sse_queues[lesson.id] = queue

    await _run_pipeline(db, monkeypatch, lesson=lesson)

    assert queue.get_nowait() == {"event": "draft_ready"}


async def test_pipeline_without_listener_does_not_fail(db, monkeypatch):
    lesson, _students, bot = await _run_pipeline(db, monkeypatch)
    assert sse_queues == {}
    assert bot.send_message.await_args.args[1] == "✅ Қоралама тайёр — Mini App'да кўринг"


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

async def test_event_stream_delivers_draft_ready_then_unregisters():
    gen = _event_stream(11, timeout=5)
    pending = asyncio.create_task(gen.__anext__())
    await asyncio.sleep(0)  # let the generator body register its queue
    assert 11 in sse_queues

    await sse_queues[11].put({"event": "draft_ready"})
    assert await pending == 'data: {"event": "draft_ready"}\n\n'

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
    assert 11 not in sse_queues


async def test_event_stream_times_out_and_unregisters():
    gen = _event_stream(12, timeout=0.01)
    t0 = time.monotonic()
    frame = await gen.__anext__()
    assert frame == 'data: {"event": "timeout"}\n\n'
    assert time.monotonic() - t0 < 5  # came from the timeout, not a real 90s wait

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
    assert 12 not in sse_queues


async def test_event_stream_unregisters_when_client_disconnects():
    gen = _event_stream(13, timeout=5)
    pending = asyncio.create_task(gen.__anext__())
    await asyncio.sleep(0)
    assert 13 in sse_queues

    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await gen.aclose()  # what Starlette does when the response is torn down
    assert 13 not in sse_queues


def test_stream_endpoint_requires_auth():
    from app.main import app
    client = TestClient(app)
    r = client.get("/api/lessons/1/stream")
    assert r.status_code == 401


async def test_stream_endpoint_returns_live_sse_response():
    """The endpoint is exercised by calling it directly rather than over
    TestClient: starlette's test transport runs the ASGI app to completion
    before handing back a response (testclient.py `portal.call(self.app, ...)`),
    so an SSE endpoint can never be read incrementally through it -- the request
    would just block until the 90s timeout."""
    response = await stream_lesson(99, _=TEACHER_ID)
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"

    pending = asyncio.create_task(response.body_iterator.__anext__())
    await asyncio.sleep(0)
    assert 99 in sse_queues

    await sse_queues[99].put({"event": "draft_ready"})
    assert await pending == 'data: {"event": "draft_ready"}\n\n'

    await response.body_iterator.aclose()
    assert 99 not in sse_queues


# ---------------------------------------------------------------------------
# confirm / edit callbacks
# ---------------------------------------------------------------------------

def fake_callback(telegram_id: int, data: str):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=telegram_id),
        data=data,
        answer=AsyncMock(),
    )


async def test_confirm_callback_answers_teacher():
    cb = fake_callback(TEACHER_ID, "confirm:5")
    await cb_confirm(cb)
    cb.answer.assert_awaited_once_with("Mini App'да Сақлаш тугмасини босинг.")


async def test_edit_callback_answers_teacher():
    cb = fake_callback(TEACHER_ID, "edit:5")
    await cb_edit(cb)
    cb.answer.assert_awaited_once_with("Mini App'да таҳрирланг.")


async def test_callbacks_ignore_non_teacher():
    cb1 = fake_callback(NOT_TEACHER_ID, "confirm:5")
    cb2 = fake_callback(NOT_TEACHER_ID, "edit:5")
    await cb_confirm(cb1)
    await cb_edit(cb2)
    cb1.answer.assert_not_awaited()
    cb2.answer.assert_not_awaited()
