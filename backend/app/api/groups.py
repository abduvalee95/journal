from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_teacher
from app.db.models import Group, Student
from app.db.session import get_session
from app.utils.localtime import bishkek_now

router = APIRouter(prefix="/api/groups", tags=["groups"])
students_router = APIRouter(prefix="/api/students", tags=["students"])


# ── Schemas ──────────────────────────────────────────────────


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    weekday: int = Field(ge=1, le=7)
    start_time: str | None = Field(default=None, max_length=10)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Guruh nomi bo'sh bo'lishi mumkin emas")
        return s


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    weekday: int | None = Field(default=None, ge=1, le=7)
    start_time: str | None = Field(default=None, max_length=10)
    is_active: int | None = Field(default=None, ge=0, le=1)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("Guruh nomi bo'sh bo'lishi mumkin emas")
        return s


class StudentCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=60)
    telegram_id: int | None = None


class StudentUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=60)
    group_id: int | None = None
    is_active: int | None = Field(default=None, ge=0, le=1)


# ── Group Endpoints ──────────────────────────────────────────


@router.get("")
async def list_groups(
    include_inactive: Annotated[bool, Query()] = False,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    """List all groups with active student count."""
    subq = (
        select(Student.group_id, func.count(Student.id).label("student_count"))
        .where(Student.is_active == 1)
        .group_by(Student.group_id)
        .subquery()
    )

    stmt = (
        select(Group, func.coalesce(subq.c.student_count, 0).label("student_count"))
        .outerjoin(subq, Group.id == subq.c.group_id)
        .order_by(Group.weekday, Group.id)
    )
    if not include_inactive:
        stmt = stmt.where(Group.is_active == 1)

    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": g.id,
            "name": g.name,
            "weekday": g.weekday,
            "start_time": g.start_time,
            "is_active": g.is_active,
            "student_count": count,
        }
        for g, count in rows
    ]


@router.post("", status_code=201)
async def create_group(
    body: GroupCreate,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    """Create a new group."""
    existing = await session.scalar(
        select(Group).where(Group.weekday == body.weekday, Group.is_active == 1)
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Haftaning bu kuni ({body.weekday}) uchun faol guruh allaqachon mavjud: {existing.name}",
        )

    group = Group(
        name=body.name,
        weekday=body.weekday,
        start_time=body.start_time,
        is_active=1,
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return {
        "id": group.id,
        "name": group.name,
        "weekday": group.weekday,
        "start_time": group.start_time,
        "is_active": group.is_active,
        "student_count": 0,
    }


@router.get("/{group_id}")
async def get_group_detail(
    group_id: int,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    """Get group details including active and inactive students."""
    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Guruh topilmadi")

    students = (
        await session.execute(
            select(Student)
            .where(Student.group_id == group_id)
            .order_by(Student.is_active.desc(), Student.full_name)
        )
    ).scalars().all()

    return {
        "id": group.id,
        "name": group.name,
        "weekday": group.weekday,
        "start_time": group.start_time,
        "is_active": group.is_active,
        "students": [
            {
                "id": s.id,
                "full_name": s.full_name,
                "telegram_id": s.telegram_id,
                "joined_at": s.joined_at,
                "is_active": s.is_active,
            }
            for s in students
        ],
    }


@router.patch("/{group_id}")
async def update_group(
    group_id: int,
    body: GroupUpdate,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    """Update group properties."""
    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Guruh topilmadi")

    target_weekday = body.weekday if body.weekday is not None else group.weekday
    target_active = body.is_active if body.is_active is not None else group.is_active

    if target_active == 1 and (target_weekday != group.weekday or group.is_active == 0):
        existing = await session.scalar(
            select(Group).where(
                Group.weekday == target_weekday,
                Group.is_active == 1,
                Group.id != group_id,
            )
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Haftaning bu kuni ({target_weekday}) uchun boshqa faol guruh mavjud: {existing.name}",
            )

    if body.name is not None:
        group.name = body.name
    if body.weekday is not None:
        group.weekday = body.weekday
    if body.start_time is not None:
        group.start_time = body.start_time
    if body.is_active is not None:
        group.is_active = body.is_active

    await session.commit()
    await session.refresh(group)
    return {
        "id": group.id,
        "name": group.name,
        "weekday": group.weekday,
        "start_time": group.start_time,
        "is_active": group.is_active,
    }


@router.delete("/{group_id}")
async def delete_group(
    group_id: int,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    """Soft-delete / archive a group."""
    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Guruh topilmadi")

    group.is_active = 0
    await session.commit()
    return {"ok": True}


@router.post("/{group_id}/students", status_code=201)
async def add_student_to_group(
    group_id: int,
    body: StudentCreate,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    """Add a student manually to a group."""
    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Guruh topilmadi")

    telegram_id = body.telegram_id
    if telegram_id is None:
        # Generate pseudo telegram_id for manually added students who haven't linked Telegram yet
        min_id = await session.scalar(select(func.min(Student.telegram_id)))
        telegram_id = (min_id - 1) if (min_id and min_id < 0) else -1
    else:
        existing = await session.scalar(
            select(Student).where(Student.telegram_id == telegram_id)
        )
        if existing:
            raise HTTPException(400, "Bu Telegram ID bilan o'quvchi allaqachon ro'yxatdan o'tgan")

    student = Student(
        group_id=group_id,
        full_name=body.full_name.strip(),
        telegram_id=telegram_id,
        joined_at=bishkek_now().isoformat(),
        is_active=1,
    )
    session.add(student)
    await session.commit()
    await session.refresh(student)
    return {
        "id": student.id,
        "group_id": student.group_id,
        "full_name": student.full_name,
        "telegram_id": student.telegram_id,
        "joined_at": student.joined_at,
        "is_active": student.is_active,
    }


# ── Student Endpoints ────────────────────────────────────────


@students_router.patch("/{student_id}")
async def update_student(
    student_id: int,
    body: StudentUpdate,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    """Update student information or move student to another group."""
    student = await session.get(Student, student_id)
    if not student:
        raise HTTPException(404, "O'quvchi topilmadi")

    if body.group_id is not None:
        target_group = await session.get(Group, body.group_id)
        if not target_group:
            raise HTTPException(404, "Ko'chirilayotgan guruh topilmadi")
        student.group_id = body.group_id

    if body.full_name is not None:
        s = body.full_name.strip()
        if not s:
            raise HTTPException(400, "Ism bo'sh bo'lishi mumkin emas")
        student.full_name = s

    if body.is_active is not None:
        student.is_active = body.is_active

    await session.commit()
    await session.refresh(student)
    return {
        "id": student.id,
        "group_id": student.group_id,
        "full_name": student.full_name,
        "telegram_id": student.telegram_id,
        "is_active": student.is_active,
    }


@students_router.delete("/{student_id}")
async def delete_student(
    student_id: int,
    _: int = Depends(require_teacher),
    session: AsyncSession = Depends(get_session),
):
    """Soft-delete / deactivate student."""
    student = await session.get(Student, student_id)
    if not student:
        raise HTTPException(404, "O'quvchi topilmadi")

    student.is_active = 0
    await session.commit()
    return {"ok": True}
