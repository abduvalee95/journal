"""Queries shared by more than one entry point (API routes, bot handlers)."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson
from app.utils.localtime import bishkek_now


async def get_or_create_lesson(session: AsyncSession, group_id: int, date: str) -> Lesson:
    """Fetch the lesson for (group, date), creating it if absent.

    Lives here rather than in lessons.py because both the Mini App
    (GET /api/today) and the voice handler can be the first to touch a given
    day's lesson, and `UNIQUE(group_id, lesson_date)` means they must agree
    on how that row is created.

    That same pairing is why the insert is guarded: this is a SELECT, an
    await, then an INSERT, so the two callers really can both find nothing and
    both try to create it. The loser's IntegrityError used to surface as a 500
    to the Mini App, or crash the voice handler inside the webhook.
    """
    lesson = await session.scalar(
        select(Lesson).where(Lesson.group_id == group_id, Lesson.lesson_date == date)
    )
    if lesson:
        return lesson

    lesson = Lesson(group_id=group_id, lesson_date=date, created_at=bishkek_now().isoformat())
    session.add(lesson)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        lesson = await session.scalar(
            select(Lesson).where(Lesson.group_id == group_id, Lesson.lesson_date == date)
        )
        if lesson is None:
            raise
        return lesson
    await session.refresh(lesson)
    return lesson
