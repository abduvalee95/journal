"""Background worker that drains the `outbox` table into Telegram DMs.

`run_outbox(bot)` is started once from main.py's lifespan and loops forever.
The drain pass itself is factored into `_drain_once(bot)` so tests can call it
directly without sleeping.

Failure handling per pending row:
  - success                       -> "sent", sent_at set
  - TelegramForbiddenError        -> "failed" immediately (student blocked the
                                      bot; retrying can't help)
  - TelegramRetryAfter            -> wait out the flood limit, attempts
                                      unchanged (this is a normal response,
                                      not a failure)
  - missing student row           -> "failed" immediately
  - any other exception           -> attempts += 1, stays "pending" until
                                      attempts >= 3, then "failed"

Each row is committed as soon as its outcome is known. Committing once at the
end of the pass meant a shutdown or a crash mid-drain lost the record of every
send that had already succeeded, and the next start re-sent them all -- and
because asyncio.CancelledError is a BaseException, `except Exception` did not
catch the shutdown path either.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import func, select

from app.config import settings
from app.db.models import Outbox, Student
from app.db.session import AsyncSessionLocal
from app.utils.localtime import bishkek_now, today

logger = logging.getLogger(__name__)

DRAIN_INTERVAL_SECONDS = 30

# Telegram tolerates roughly 30 messages/second overall; a 15-student batch
# fired with no gap is what provokes the flood limit in the first place.
SEND_SPACING_SECONDS = 0.05

_last_failure_summary_date: str | None = None

# Set by whoever queues work, so the worker drains immediately instead of
# waiting out the retry interval. Only correct because the API and the worker
# share one process -- which the Dockerfile's `--workers 1` enforces, for the
# separate reason that two workers would send every report twice.
_wake = asyncio.Event()


def wake_outbox() -> None:
    """Ask the worker to drain now rather than on its next tick."""
    _wake.set()


async def _drain_once(bot: Bot) -> None:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(Outbox).where(Outbox.status == "pending").order_by(Outbox.created_at)
        )).scalars().all()

        for row in rows:
            student = await session.get(Student, row.student_id)
            if student is None:
                # Retrying cannot conjure the student back; three passes of
                # AttributeError used to be the only way this ended.
                row.status = "failed"
                row.last_error = "student row missing"
                await session.commit()
                continue

            try:
                await bot.send_message(student.telegram_id, row.text, parse_mode=None)
                row.status = "sent"
                row.sent_at = bishkek_now().isoformat()
            except TelegramForbiddenError as e:
                row.status = "failed"
                row.last_error = str(e)
            except TelegramRetryAfter as e:
                # Flood control is an instruction to slow down, not a delivery
                # failure. Counting it burned the row's three attempts and the
                # student silently never got their report.
                row.last_error = f"flood control: retry after {e.retry_after}s"
                await session.commit()
                await asyncio.sleep(min(e.retry_after, 60))
                continue
            except asyncio.CancelledError:
                # Shutdown landed inside send_message. The message may well
                # have gone out; commit what we know before unwinding.
                await session.commit()
                raise
            except Exception as e:
                row.attempts += 1
                row.last_error = str(e)
                if row.attempts >= 3:
                    row.status = "failed"

            await session.commit()
            await asyncio.sleep(SEND_SPACING_SECONDS)


async def _report_failures_daily(bot: Bot) -> None:
    """Once per day, tell the teacher how many reports never arrived.

    Without this a student who blocked the bot fails permanently and silently:
    nothing in the teacher's workflow ever surfaces a `failed` row.
    """
    global _last_failure_summary_date
    day = today()
    if _last_failure_summary_date == day:
        return

    async with AsyncSessionLocal() as session:
        failed = await session.scalar(
            select(func.count()).select_from(Outbox).where(Outbox.status == "failed")
        )
    _last_failure_summary_date = day
    if failed:
        await bot.send_message(
            settings.teacher_telegram_id,
            f"⚠️ {failed} та хабар етказилмади.",
            parse_mode=None,
        )


async def run_outbox(bot: Bot):
    while True:
        # Drain first: sleeping up front meant the very first report after a
        # restart was always at least 30 seconds late.
        try:
            await _drain_once(bot)
            await _report_failures_daily(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Outbox drain pass failed; will retry next cycle")

        # Wait for either new work or the retry tick. On a fixed sleep alone,
        # a report queued one second after a drain waited the full interval:
        # measured at 26s from the teacher tapping Сақлаш to the first send,
        # of which 0.8s was actual work.
        try:
            await asyncio.wait_for(_wake.wait(), timeout=DRAIN_INTERVAL_SECONDS)
        except TimeoutError:
            pass
        _wake.clear()
