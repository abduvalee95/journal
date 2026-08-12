"""Queries shared by more than one entry point (API routes, bot handlers)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson
from app.utils.localtime import bishkek_now


async def get_or_create_lesson(session: AsyncSession, group_id: int, date: str) -> Lesson:
    """Fetch the lesson for (group, date), creating it if absent.

    Lives here rather than in lessons.py because both the Mini App
    (GET /api/today) and the voice handler can be the first to touch a given
    day's lesson, and `UNIQUE(group_id, lesson_date)` means they must agree
    on how that row is created.
    """
    lesson = await session.scalar(
        select(Lesson).where(Lesson.group_id == group_id, Lesson.lesson_date == date)
    )
    if not lesson:
        lesson = Lesson(group_id=group_id, lesson_date=date, created_at=bishkek_now().isoformat())
        session.add(lesson)
        await session.commit()
        await session.refresh(lesson)
    return lesson
