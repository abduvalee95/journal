import asyncio
import json
from datetime import date as date_cls
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_teacher
from app.config import settings
from app.db.models import Attendance, Group, Lesson, Outbox, Student
from app.db.queries import get_or_create_lesson
from app.db.session import get_session
from app.services.events import sse_queues
from app.services.outbox import wake_outbox
from app.services.report import build_report
from app.utils.localtime import bishkek_now, today, weekday

router = APIRouter()

# ── Schemas ──────────────────────────────────────────────────

AttendanceStatus = Literal["present", "absent", "late"]


class AttendanceItem(BaseModel):
    student_id: int
    status: AttendanceStatus
    grade: int | None = Field(default=None, ge=1, le=5)
    note_public: str | None = Field(default=None, max_length=settings.max_note_chars)

    @model_validator(mode="after")
    def _absent_has_no_grade(self):
        # The spec says a grade is meaningless for a student who wasn't there,
        # and build_report omits it -- so storing one is a silent
        # inconsistency between the database and what the student receives.
        if self.status == "absent":
            self.grade = None
        return self


class AttendanceBatch(BaseModel):
    items: list[AttendanceItem]
    topic: str | None = Field(default=None, max_length=200)
    homework: str | None = Field(default=None, max_length=settings.max_note_chars)


class LessonPatch(BaseModel):
    """Teacher edits to the lesson's own fields.

    summary_public is here because it is the body of every student's message
    and was previously unreachable: the AI wrote it, the Mini App never
    displayed it, and no endpoint could change it.
    """
    topic: str | None = Field(default=None, max_length=200)
    homework: str | None = Field(default=None, max_length=settings.max_note_chars)
    summary_public: str | None = Field(default=None, max_length=settings.max_summary_chars)

# ── Helpers ──────────────────────────────────────────────────


def _lesson_out(lesson: Lesson) -> dict:
    return {
        "id": lesson.id,
        "date": lesson.lesson_date,
        "topic": lesson.topic,
        "homework": lesson.homework,
        "summary_public": lesson.summary_public,
        "summary_reviewed": bool(lesson.summary_reviewed),
        "status": lesson.status,
        # Whether a voice note has been received for this lesson. The Mini App
        # uses it to decide whether an AI draft is actually on its way before
        # showing a spinner. A boolean rather than audio_file_id itself: the
        # client has no use for a Telegram file id.
        "has_audio": lesson.audio_file_id is not None,
    }


def _att_out(a: Attendance) -> dict:
    return {
        "id": a.id,
        "student_id": a.student_id,
        "status": a.status,
        "grade": a.grade,
        "note_public": a.note_public,
    }


async def _students_and_attendance(session: AsyncSession, group_id: int, lesson_id: int):
    students = (await session.execute(
        select(Student).where(Student.group_id == group_id, Student.is_active == 1)
    )).scalars().all()
    attendance = (await session.execute(
        select(Attendance).where(Attendance.lesson_id == lesson_id)
    )).scalars().all()
    return students, attendance

# ── Endpoints ────────────────────────────────────────────────


@router.get("/api/today")
async def get_today(
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    group = await session.scalar(
        select(Group).where(Group.weekday == weekday(), Group.is_active == 1)
    )
    if not group:
        return {"group": None, "lesson": None, "students": [], "attendance": []}
    lesson = await get_or_create_lesson(session, group.id, today())
    students, attendance = await _students_and_attendance(session, group.id, lesson.id)
    return {
        "group": {"id": group.id, "name": group.name},
        "lesson": _lesson_out(lesson),
        "students": [{"id": s.id, "full_name": s.full_name} for s in students],
        "attendance": [_att_out(a) for a in attendance],
    }


@router.get("/api/lessons")
async def get_lesson_by_date(
    date: str,
    group_id: int | None = None,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    try:
        date_cls.fromisoformat(date)
    except ValueError:
        raise HTTPException(422, "date must be YYYY-MM-DD") from None

    query = select(Lesson).where(Lesson.lesson_date == date)
    if group_id is not None:
        query = query.where(Lesson.group_id == group_id)
    else:
        # Without a group the query returned whichever row came first. That is
        # unique only while one group owns each weekday; scope it to the group
        # whose weekday matches the requested date so it stays correct after.
        iso_weekday = date_cls.fromisoformat(date).isoweekday()
        scoped = await session.scalar(
            select(Group).where(Group.weekday == iso_weekday, Group.is_active == 1)
        )
        if scoped:
            query = query.where(Lesson.group_id == scoped.id)

    lesson = await session.scalar(query.order_by(Lesson.id).limit(1))
    if not lesson:
        return {"group": None, "lesson": None, "students": [], "attendance": []}
    group = await session.get(Group, lesson.group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    students, attendance = await _students_and_attendance(session, group.id, lesson.id)
    return {
        "group": {"id": group.id, "name": group.name},
        "lesson": _lesson_out(lesson),
        "students": [{"id": s.id, "full_name": s.full_name} for s in students],
        "attendance": [_att_out(a) for a in attendance],
    }


@router.patch("/api/lessons/{lesson_id}")
async def patch_lesson(
    lesson_id: int,
    body: LessonPatch,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    """Edit the lesson's own fields, and record that a human did so.

    Writing summary_public here is what marks it reviewed: until then confirm
    refuses to build reports from AI-authored text nobody has read.
    """
    lesson = await session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    if lesson.status != "draft":
        raise HTTPException(409, "Lesson already confirmed")

    if body.topic is not None:
        lesson.topic = body.topic
    if body.homework is not None:
        lesson.homework = body.homework
    if body.summary_public is not None:
        lesson.summary_public = body.summary_public
        lesson.summary_reviewed = 1
    lesson.manual_edit_at = bishkek_now().isoformat()
    await session.commit()
    return {"ok": True, "lesson": _lesson_out(lesson)}


@router.post("/api/lessons/{lesson_id}/summary/approve")
async def approve_summary(
    lesson_id: int,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    """Accept the AI's summary as written, without editing it."""
    lesson = await session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    lesson.summary_reviewed = 1
    lesson.manual_edit_at = bishkek_now().isoformat()
    await session.commit()
    return {"ok": True}


@router.put("/api/lessons/{lesson_id}/attendance")
async def save_attendance(
    lesson_id: int,
    body: AttendanceBatch,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    lesson = await session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    if lesson.status != "draft":
        # Reports for a confirmed lesson are already out; corrections go
        # through PATCH /api/attendance/{id}, which does not re-notify.
        raise HTTPException(409, "Lesson already confirmed")

    roster = set((await session.execute(
        select(Student.id).where(
            Student.group_id == lesson.group_id, Student.is_active == 1
        )
    )).scalars().all())
    unknown = [i.student_id for i in body.items if i.student_id not in roster]
    if unknown:
        # Otherwise confirm would build this lesson's report for a student who
        # was never in the class and DM it to them.
        raise HTTPException(400, f"Students not in this group: {unknown}")

    if body.topic is not None:
        lesson.topic = body.topic
    if body.homework is not None:
        lesson.homework = body.homework
    lesson.manual_edit_at = bishkek_now().isoformat()

    for item in body.items:
        existing = await session.scalar(
            select(Attendance).where(
                Attendance.lesson_id == lesson_id,
                Attendance.student_id == item.student_id,
            )
        )
        if existing:
            existing.status = item.status
            existing.grade = item.grade
            existing.note_public = item.note_public
        else:
            session.add(Attendance(
                lesson_id=lesson_id,
                student_id=item.student_id,
                status=item.status,
                grade=item.grade,
                note_public=item.note_public,
            ))
    await session.commit()
    return {"ok": True}


@router.patch("/api/attendance/{att_id}")
async def patch_attendance(
    att_id: int,
    body: AttendanceItem,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    """Silent correction: saves, and never re-notifies the student."""
    att = await session.get(Attendance, att_id)
    if not att:
        raise HTTPException(404, "Not found")
    att.status = body.status
    att.grade = body.grade
    att.note_public = body.note_public
    await session.commit()
    return {"ok": True}


@router.post("/api/lessons/{lesson_id}/confirm")
async def confirm_lesson(
    lesson_id: int,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    """Finalise a lesson and queue one report per student.

    The draft -> saved transition is claimed with a conditional UPDATE rather
    than a read, a check and a write: two overlapping requests both used to
    pass the status check and both insert a full set of outbox rows, so every
    student received their report twice. UNIQUE(lesson_id, student_id) on
    outbox is the database-level backstop for the same thing.
    """
    lesson = await session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    if lesson.status != "draft":
        return {"ok": True}   # already confirmed

    if lesson.summary_public and not lesson.summary_reviewed:
        # summary_public goes verbatim to every student in the group and is
        # written straight from model output. Nothing else in the pipeline
        # inspects it, so a human has to.
        raise HTTPException(409, {
            "error": "summary_not_reviewed",
            "message": "Умумий хулосани кўриб чиқинг ва тасдиқланг.",
        })

    result = await session.execute(
        update(Lesson)
        .where(Lesson.id == lesson_id, Lesson.status == "draft")
        .values(status="saved", saved_at=bishkek_now().isoformat())
    )
    if result.rowcount == 0:
        await session.rollback()
        return {"ok": True}   # a concurrent request won the transition

    await session.refresh(lesson)
    group = await session.get(Group, lesson.group_id)
    att_rows = (await session.execute(
        select(Attendance).where(Attendance.lesson_id == lesson_id)
    )).scalars().all()
    for att in att_rows:
        student = await session.get(Student, att.student_id)
        if not student or not student.is_active:
            continue
        session.add(Outbox(
            student_id=att.student_id,
            lesson_id=lesson_id,
            text=build_report(lesson, att, group),
            created_at=bishkek_now().isoformat(),
        ))
    await session.commit()
    # Don't make the class wait out the retry interval for a report that is
    # already written and ready to go.
    wake_outbox()
    return {"ok": True}


# ── SSE: voice draft ready ───────────────────────────────────

STREAM_TIMEOUT_SECONDS = 90
HEARTBEAT_SECONDS = 15


async def _event_stream(lesson_id: int, timeout: float = STREAM_TIMEOUT_SECONDS):  # noqa: ASYNC109 -- the caller never passes one; it is a seam so tests need not wait 90s
    """Yield SSE frames for one lesson until its draft lands or we time out.

    Registers a queue in `sse_queues` for the voice pipeline to push into, and
    always unregisters it on the way out so a disconnected browser doesn't leak
    a queue the pipeline would then fill forever.

    A keepalive goes out every 15s: an idle connection is a connection proxies
    are free to drop, and the client cannot tell that apart from a stalled AI.
    """
    queue: asyncio.Queue = asyncio.Queue()
    sse_queues[lesson_id] = queue
    deadline = asyncio.get_event_loop().time() + timeout
    try:
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                yield 'data: {"event": "timeout"}\n\n'
                return
            wait = min(HEARTBEAT_SECONDS, remaining)
            try:
                data = await asyncio.wait_for(queue.get(), timeout=wait)
            except TimeoutError:
                # Only a heartbeat if there is still time left to wait in;
                # hitting the deadline is the stream giving up.
                if wait >= remaining:
                    yield 'data: {"event": "timeout"}\n\n'
                    return
                yield 'data: {"event": "keepalive"}\n\n'
                continue
            yield f"data: {json.dumps(data)}\n\n"
            if data.get("event") == "draft_ready":
                return
    finally:
        # Only drop our own queue: a later listener for the same lesson has
        # already replaced this entry and still needs it.
        if sse_queues.get(lesson_id) is queue:
            del sse_queues[lesson_id]


@router.get("/api/lessons/{lesson_id}/stream")
async def stream_lesson(
    lesson_id: int,
    _: int = Depends(require_teacher),
):
    return StreamingResponse(_event_stream(lesson_id), media_type="text/event-stream")
