from typing import Optional, List, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.db.models import Group, Lesson, Student, Attendance, Outbox
from app.api.deps import require_teacher
from app.utils.localtime import today, weekday, bishkek_now
from app.services.report import build_report

router = APIRouter()

# ── Schemas ──────────────────────────────────────────────────

AttendanceStatus = Literal["present", "absent", "late"]


class AttendanceItem(BaseModel):
    student_id: int
    status: AttendanceStatus
    grade: Optional[int] = Field(default=None, ge=1, le=5)
    note_public: Optional[str] = None


class AttendanceBatch(BaseModel):
    items: List[AttendanceItem]
    topic: Optional[str] = None
    homework: Optional[str] = None

# ── Helpers ──────────────────────────────────────────────────


def _lesson_out(lesson: Lesson) -> dict:
    return {
        "id": lesson.id,
        "date": lesson.lesson_date,
        "topic": lesson.topic,
        "homework": lesson.homework,
        "summary_public": lesson.summary_public,
        "status": lesson.status,
    }


def _att_out(a: Attendance) -> dict:
    return {
        "id": a.id,
        "student_id": a.student_id,
        "status": a.status,
        "grade": a.grade,
        "note_public": a.note_public,
    }


async def _get_or_create_lesson(session: AsyncSession, group_id: int, date: str) -> Lesson:
    lesson = await session.scalar(
        select(Lesson).where(Lesson.group_id == group_id, Lesson.lesson_date == date)
    )
    if not lesson:
        lesson = Lesson(group_id=group_id, lesson_date=date, created_at=bishkek_now().isoformat())
        session.add(lesson)
        await session.commit()
        await session.refresh(lesson)
    return lesson


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
    lesson = await _get_or_create_lesson(session, group.id, today())
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
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    lesson = await session.scalar(select(Lesson).where(Lesson.lesson_date == date))
    if not lesson:
        return {"group": None, "lesson": None, "students": [], "attendance": []}
    group = await session.get(Group, lesson.group_id)
    students, attendance = await _students_and_attendance(session, group.id, lesson.id)
    return {
        "group": {"id": group.id, "name": group.name},
        "lesson": _lesson_out(lesson),
        "students": [{"id": s.id, "full_name": s.full_name} for s in students],
        "attendance": [_att_out(a) for a in attendance],
    }


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
    if body.topic is not None:
        lesson.topic = body.topic
    if body.homework is not None:
        lesson.homework = body.homework
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
    lesson = await session.get(Lesson, lesson_id)
    if not lesson or lesson.status != "draft":
        return {"ok": True}   # idempotent: unknown lesson or already confirmed
    lesson.status = "saved"
    lesson.saved_at = bishkek_now().isoformat()
    group = await session.get(Group, lesson.group_id)
    att_rows = (await session.execute(
        select(Attendance).where(Attendance.lesson_id == lesson_id)
    )).scalars().all()
    for att in att_rows:
        student = await session.get(Student, att.student_id)
        if not student or not student.is_active:
            continue
        text = build_report(lesson, att, group)
        session.add(Outbox(
            student_id=att.student_id,
            lesson_id=lesson_id,
            text=text,
            created_at=bishkek_now().isoformat(),
        ))
    await session.commit()
    return {"ok": True}
