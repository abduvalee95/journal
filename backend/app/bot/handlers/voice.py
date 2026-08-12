"""Teacher voice note -> ASR -> Claude -> draft lesson.

The handler itself stays fast: it only resolves today's group, pins the audio
file id to the lesson and answers, then hands the slow work (two network calls,
10-20s) to `_pipeline` as a background task so aiogram's webhook reply is not
blocked. `_pipeline` opens its own short-lived sessions rather than holding one
across the API calls.
"""
import asyncio
import logging
import time

from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import Group, Lesson, Student, Attendance, AiJob
from app.db.queries import get_or_create_lesson
from app.services.asr import transcribe
from app.services.llm import extract_lesson
from app.services.matcher import match_names
from app.services.events import sse_queues
from app.utils.localtime import today, weekday, bishkek_now

logger = logging.getLogger(__name__)

router = Router()

VALID_STATUSES = {"present", "absent", "late"}

# asyncio only keeps a weak reference to a running task, so a fire-and-forget
# pipeline can be garbage-collected mid-flight. Hold a strong reference until
# it finishes.
_background_tasks: set[asyncio.Task] = set()


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
    task = asyncio.create_task(_pipeline(
        message.bot, lesson_id, message.voice.file_id,
        student_names, student_map, message.chat.id,
    ))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _clean_grade(value) -> int | None:
    """Keep only a real 1-5 grade.

    The tool schema asks for 1-5 but nothing enforces it on the model's side,
    and `attendance.grade` has a `BETWEEN 1 AND 5` CHECK constraint -- an
    out-of-range value would blow up the whole pipeline on commit.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= 5 else None


def _clean_status(value) -> str:
    return value if value in VALID_STATUSES else "present"


async def _pipeline(bot, lesson_id, file_id, student_names, student_map, chat_id):
    t0 = time.time()
    async with AsyncSessionLocal() as s:
        job = AiJob(lesson_id=lesson_id, stage="asr", status="running",
                    created_at=bishkek_now().isoformat())
        s.add(job)
        await s.commit()
        job_id = job.id

    try:
        file = await bot.get_file(file_id)
        raw = await bot.download_file(file.file_path)
        transcript = await transcribe(raw.read())

        async with AsyncSessionLocal() as s:
            lesson = await s.get(Lesson, lesson_id)
            lesson.raw_note = transcript
            job = await s.get(AiJob, job_id)
            job.stage = "llm"
            await s.commit()

        draft = await extract_lesson(transcript, student_names)
        per_student = draft.get("per_student") or []
        match = match_names([p["name_mentioned"] for p in per_student], student_map)

        async with AsyncSessionLocal() as s:
            lesson = await s.get(Lesson, lesson_id)
            if lesson.status != "draft":
                # Already confirmed: student notifications are out, so the AI
                # must not rewrite what those messages were built from.
                job = await s.get(AiJob, job_id)
                job.status = "done"
                job.duration_ms = int((time.time() - t0) * 1000)
                await s.commit()
                await bot.send_message(chat_id, "ℹ️ Бу дарс аллақачон сақланган, ўзгартирилмади.")
                return

            lesson.topic = draft.get("topic")
            lesson.summary_public = draft.get("summary_public")
            lesson.homework = draft.get("homework")
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
                # Upsert: a second voice note for the same lesson, or a voice
                # note after a manual save, would otherwise hit
                # UNIQUE(lesson_id, student_id) and fail the whole pipeline.
                if existing:
                    existing.status = _clean_status(p.get("attendance_hint"))
                    existing.grade = _clean_grade(p.get("grade_suggested"))
                    existing.note_public = p.get("note_public")
                else:
                    s.add(Attendance(
                        lesson_id=lesson_id,
                        student_id=sid,
                        status=_clean_status(p.get("attendance_hint")),
                        grade=_clean_grade(p.get("grade_suggested")),
                        note_public=p.get("note_public"),
                    ))
            job = await s.get(AiJob, job_id)
            job.status = "done"
            job.duration_ms = int((time.time() - t0) * 1000)
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
        logger.exception("AI pipeline failed for lesson %s", lesson_id)
        async with AsyncSessionLocal() as s:
            job = await s.get(AiJob, job_id)
            if job:
                job.status = "error"
                job.error = str(e)
                job.duration_ms = int((time.time() - t0) * 1000)
                await s.commit()
        await bot.send_message(chat_id, "❌ AI ишламади, қўлда киритинг")
