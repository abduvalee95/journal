"""Teacher voice note -> ASR -> LLM -> draft lesson.

The handler itself stays fast: it only resolves today's group, pins the audio
file id to the lesson and answers, then hands the slow work (two network calls,
10-20s) to `_pipeline` as a background task so aiogram's webhook reply is not
blocked. `_pipeline` opens its own short-lived sessions rather than holding one
across the API calls.

The pipeline never overwrites work the teacher did by hand while it was
running. It records when it started and refuses to write if `manual_edit_at`
moved past that point -- the Mini App's "only auto-fill a pristine form" rule
is a client-side courtesy, and the client is not the only writer.
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from app.config import settings
from app.db.models import AiJob, Attendance, Group, Lesson, Student
from app.db.queries import get_or_create_lesson
from app.db.session import AsyncSessionLocal
from app.services.asr import transcribe
from app.services.events import sse_queues
from app.services.llm import extract_lesson, validate_draft
from app.services.matcher import match_names
from app.utils.localtime import bishkek_now, today, weekday

logger = logging.getLogger(__name__)

router = Router()

# asyncio only keeps a weak reference to a running task, so a fire-and-forget
# pipeline can be garbage-collected mid-flight. Hold a strong reference until
# it finishes.
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _redact(exc: Exception) -> str:
    """A short, credential-free description of a failure.

    httpx puts the full request URL into HTTPStatusError, so `str(e)` on a
    provider that authenticates by query string wrote the API key into
    ai_jobs.error -- which is in the nightly backup -- and into the logs.
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        return f"{type(exc).__name__}: HTTP {status}"
    return type(exc).__name__


@router.message(F.voice)
async def handle_voice(message: Message):
    if message.from_user.id != settings.teacher_telegram_id:
        return

    async with AsyncSessionLocal() as s:
        group = await s.scalar(
            select(Group).where(Group.weekday == weekday(), Group.is_active == 1)
        )
        if not group:
            await message.answer("Бугун дарс гуруҳ топилмади.")
            return
        lesson = await get_or_create_lesson(s, group.id, today())
        lesson.audio_file_id = message.voice.file_id
        await s.commit()
        students = (await s.execute(
            select(Student).where(Student.group_id == group.id, Student.is_active == 1)
        )).scalars().all()
        student_names = [st.full_name for st in students]
        student_map = [{"id": st.id, "full_name": st.full_name} for st in students]
        lesson_id = lesson.id

    await message.answer("⏳ Овоз қайта ишланмоқда...")
    _spawn(_pipeline(
        message.bot, lesson_id, message.voice.file_id,
        student_names, student_map, message.chat.id,
    ))


@router.message(Command("matn"))
async def handle_text_note(message: Message):
    """Run the pipeline over typed text: `/matn <dars haqida ...>`.

    This used to fire on *every* non-command message from the teacher, and to
    await the pipeline inline. Both were wrong: a reply of "rahmat" invented a
    lesson from one word and wiped the topic, homework and summary the teacher
    had entered by hand, and awaiting a 60s LLM call inside the webhook made
    Telegram time out and redeliver the same update, starting a second
    concurrent pipeline for the same lesson.
    """
    if message.from_user.id != settings.teacher_telegram_id:
        return

    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.answer("Матн киритинг: /matn Бугун Present Perfect ўтдик...")
        return

    async with AsyncSessionLocal() as s:
        group = await s.scalar(
            select(Group).where(Group.weekday == weekday(), Group.is_active == 1)
        )
        if not group:
            await message.answer("Бугун дарс гуруҳ топилмади.")
            return
        lesson = await get_or_create_lesson(s, group.id, today())
        students = (await s.execute(
            select(Student).where(Student.group_id == group.id, Student.is_active == 1)
        )).scalars().all()
        student_names = [st.full_name for st in students]
        student_map = [{"id": st.id, "full_name": st.full_name} for st in students]
        lesson_id = lesson.id

    await message.answer("⏳ Матн қайта ишланмоқда...")
    _spawn(_pipeline(
        message.bot, lesson_id, None,
        student_names, student_map, message.chat.id,
        text_note=text,
    ))


async def _pipeline(bot, lesson_id, file_id, student_names, student_map, chat_id, text_note=None):
    t0 = time.time()
    started_at = bishkek_now().isoformat()

    async with AsyncSessionLocal() as s:
        job = AiJob(lesson_id=lesson_id, stage="asr" if file_id else "llm", status="running",
                    created_at=started_at)
        s.add(job)
        await s.commit()
        job_id = job.id

    try:
        if file_id:
            file = await bot.get_file(file_id)
            raw = await bot.download_file(file.file_path)
            prompt = (
                f"O'zbek tili dars jurnali. O'quvchilar: {', '.join(student_names)}. "
                "Mavzu, uyga vazifa, baholar."
            ) if student_names else None
            transcript = await transcribe(raw.read(), prompt=prompt)
        else:
            transcript = text_note or ""

        async with AsyncSessionLocal() as s:
            lesson = await s.get(Lesson, lesson_id)
            lesson.raw_note = transcript
            job = await s.get(AiJob, job_id)
            job.stage = "llm"
            await s.commit()

        draft = validate_draft(await extract_lesson(transcript, student_names))
        per_student = draft["per_student"]
        match = match_names([p["name_mentioned"] for p in per_student], student_map)

        async with AsyncSessionLocal() as s:
            lesson = await s.get(Lesson, lesson_id)
            job = await s.get(AiJob, job_id)
            job.status = "done"
            job.duration_ms = int((time.time() - t0) * 1000)

            if lesson.status != "draft":
                # Already confirmed: student notifications are out, so the AI
                # must not rewrite what those messages were built from.
                await s.commit()
                await bot.send_message(chat_id, "ℹ️ Бу дарс аллақачон сақланган, ўзгартирилмади.")
                return

            if lesson.manual_edit_at and lesson.manual_edit_at >= started_at:
                await s.commit()
                await bot.send_message(
                    chat_id,
                    "ℹ️ Сиз қўлда киритдингиз — AI қораламаси қўлланилмади.",
                )
                return

            lesson.topic = draft["topic"]
            lesson.summary_public = draft["summary_public"]
            lesson.homework = draft["homework"]
            # Written by the model, not seen by anyone: confirm refuses to
            # build reports from it until the teacher reviews it.
            lesson.summary_reviewed = 0

            for p in per_student:
                sid = match.get(p["name_mentioned"])
                if not sid:
                    continue
                existing = await s.scalar(
                    select(Attendance).where(
                        Attendance.lesson_id == lesson_id,
                        Attendance.student_id == sid,
                    )
                )
                # Upsert: a second voice note for the same lesson would
                # otherwise hit UNIQUE(lesson_id, student_id) and fail the
                # whole pipeline.
                if existing:
                    existing.status = p["attendance_hint"]
                    existing.grade = p["grade_suggested"]
                    existing.note_public = p["note_public"]
                else:
                    s.add(Attendance(
                        lesson_id=lesson_id,
                        student_id=sid,
                        status=p["attendance_hint"],
                        grade=p["grade_suggested"],
                        note_public=p["note_public"],
                    ))
            await s.commit()

        queue = sse_queues.get(lesson_id)
        if queue is not None:
            await queue.put({"event": "draft_ready"})

        unmatched = [p["name_mentioned"] for p in per_student
                     if match.get(p["name_mentioned"]) is None]
        msg = "✅ Қоралама тайёр — Mini App'да кўринг"
        if unmatched:
            msg += f"\n⚠️ Топилмаган исмлар: {', '.join(unmatched)}"
        await bot.send_message(chat_id, msg)

    except Exception as e:
        # A traceback from an httpx error re-prints the request URL, which is
        # where the credential was in the first place -- so those get the
        # redacted line only.
        logger.error(
            "AI pipeline failed for lesson %s (%s)",
            lesson_id,
            _redact(e),
            exc_info=not isinstance(e, httpx.HTTPError),
        )
        async with AsyncSessionLocal() as s:
            job = await s.get(AiJob, job_id)
            if job:
                job.status = "error"
                job.error = _redact(e)
                job.duration_ms = int((time.time() - t0) * 1000)
                await s.commit()
        await bot.send_message(chat_id, "❌ AI ишламади, қўлда киритинг")
