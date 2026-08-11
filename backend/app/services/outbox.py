"""Background worker that drains the `outbox` table into Telegram DMs.

`run_outbox(bot)` is started once from main.py's lifespan and loops forever,
draining every 30 seconds. The drain pass itself is factored into
`_drain_once(bot)` so tests can call it directly without sleeping.

Failure handling per pending row:
  - success                       -> "sent", sent_at set
  - TelegramForbiddenError        -> "failed" immediately (student blocked the
                                      bot; retrying can't help)
  - any other exception           -> attempts += 1, stays "pending" until
                                      attempts >= 3, then "failed"

An unexpected exception in the drain pass itself (e.g. a DB error) must not
kill the worker permanently -- it's logged and the loop continues to the next
pass.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import select

from app.db.models import Outbox, Student
from app.db.session import AsyncSessionLocal
from app.utils.localtime import bishkek_now

logger = logging.getLogger(__name__)


async def _drain_once(bot: Bot) -> None:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(Outbox).where(Outbox.status == "pending").order_by(Outbox.created_at)
        )).scalars().all()
        for row in rows:
            student = await session.get(Student, row.student_id)
            try:
                await bot.send_message(student.telegram_id, row.text, parse_mode=None)
                row.status = "sent"
                row.sent_at = bishkek_now().isoformat()
            except TelegramForbiddenError as e:
                row.status = "failed"
                row.last_error = str(e)
            except Exception as e:
                row.attempts += 1
                row.last_error = str(e)
                if row.attempts >= 3:
                    row.status = "failed"
        await session.commit()


async def run_outbox(bot: Bot):
    while True:
        await asyncio.sleep(30)
        try:
            await _drain_once(bot)
        except Exception:
            logger.exception("Outbox drain pass failed; will retry next cycle")
