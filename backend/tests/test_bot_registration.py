"""
Verification tests for Task 4: bot skeleton + student registration FSM.

The brief's own verification step (send /start to the bot over ngrok) is not
available in this environment, so these tests drive the same code paths
directly:
  - app.main imports cleanly and GET /api/health still works
  - the webhook route enforces both secret checks
  - the lifespan's webhook (de)registration is resilient to failure and logs it
  - group_keyboard() renders one button per group with the right callback_data
  - the full three-step /start FSM against a real (isolated) SQLite database,
    including the already-registered short-circuit on a second /start
"""
import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.db.models import Base, Group, Student
from app.db.seed import GROUPS
from app.bot.keyboards import group_keyboard
import app.bot.handlers.start as start_module
from app.bot.handlers.start import Reg, cmd_start, got_name, got_group


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
async def isolated_db(tmp_path, monkeypatch):
    """A throwaway SQLite DB seeded with the project's real group list,
    wired into app.bot.handlers.start in place of the shared AsyncSessionLocal
    so these tests never touch backend/data/journal.db."""
    db_path = tmp_path / "test_registration.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as s:
        s.add_all([Group(**g) for g in GROUPS])
        await s.commit()

    monkeypatch.setattr(start_module, "AsyncSessionLocal", session_maker)

    yield session_maker

    await engine.dispose()


def make_fsm_context(telegram_id: int) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def fake_message(telegram_id: int, text: str = None):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=telegram_id),
        text=text,
        answer=AsyncMock(),
    )


def fake_callback(telegram_id: int, data: str):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=telegram_id),
        data=data,
        message=SimpleNamespace(edit_text=AsyncMock()),
    )


# ---------------------------------------------------------------------------
# app.main import / health check
# ---------------------------------------------------------------------------

def test_health_check_ok_without_triggering_lifespan():
    """app.main must import cleanly and /api/health must keep working.
    Calling the client without the `with` block keeps Starlette from running
    the lifespan, so this exercises only the import + routing, no network."""
    from app.main import app
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# webhook route secret checks
# ---------------------------------------------------------------------------

def test_webhook_rejects_wrong_path_secret():
    from app.main import app
    client = TestClient(app)
    response = client.post(
        "/webhook/telegram/wrong-secret",
        json={},
        headers={"X-Telegram-Bot-Api-Secret-Token": settings.webhook_secret},
    )
    assert response.status_code == 403


def test_webhook_rejects_missing_header():
    from app.main import app
    client = TestClient(app)
    response = client.post(f"/webhook/telegram/{settings.webhook_secret}", json={})
    assert response.status_code == 403


def test_webhook_rejects_wrong_header():
    from app.main import app
    client = TestClient(app)
    response = client.post(
        f"/webhook/telegram/{settings.webhook_secret}",
        json={},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-header-value"},
    )
    assert response.status_code == 403


class _NoopBotSession:
    """Stands in for aiogram's real (aiohttp) Bot session. Every outbound
    Telegram API call -- send_message, edit_message_text, etc. -- funnels
    through `Bot.__call__` -> `self.session(bot, method, timeout=...)`, so
    replacing the session here is the single choke point that keeps this
    test off the real network while leaving the webhook route, Update
    parsing, dp.feed_update, and router filter matching all real."""

    async def __call__(self, bot, method, timeout=None):
        return None


async def test_webhook_success_dispatches_start_through_real_router(isolated_db, monkeypatch):
    """End-to-end happy path for the wiring this task produces: a real
    POST with a real Telegram Update body for "/start", through the real
    route (both secret checks passing), Update.model_validate, and
    dp.feed_update -- landing in the real router's CommandStart() filter
    and running the real cmd_start handler. Asserts on the resulting FSM
    state via the same dp.fsm.get_context() aiogram itself uses, not a
    self-asserting mock."""
    from app import main as main_module

    monkeypatch.setattr(main_module.bot, "session", _NoopBotSession())

    telegram_id = 999777
    update_payload = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1_700_000_000,
            "chat": {"id": telegram_id, "type": "private"},
            "from": {"id": telegram_id, "is_bot": False, "first_name": "Test"},
            "text": "/start",
        },
    }

    client = TestClient(main_module.app)
    response = client.post(
        f"/webhook/telegram/{settings.webhook_secret}",
        json=update_payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": settings.webhook_secret},
    )
    assert response.status_code == 200

    state = main_module.dp.fsm.get_context(
        bot=main_module.bot, chat_id=telegram_id, user_id=telegram_id
    )
    assert await state.get_state() == Reg.name.state


# ---------------------------------------------------------------------------
# lifespan resilience (correction #2)
# ---------------------------------------------------------------------------

def test_lifespan_survives_webhook_registration_failure_and_logs_it(monkeypatch, caplog):
    """set_webhook/delete_webhook must be attempted but a failure must not
    crash startup, and must be visible in the log."""
    from app import main as main_module

    monkeypatch.setattr(
        main_module.bot,
        "set_webhook",
        AsyncMock(side_effect=RuntimeError("network unreachable")),
    )
    monkeypatch.setattr(
        main_module.bot,
        "delete_webhook",
        AsyncMock(side_effect=RuntimeError("network unreachable")),
    )

    with caplog.at_level(logging.ERROR, logger="app.main"):
        with TestClient(main_module.app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200

    messages = [record.getMessage().lower() for record in caplog.records]
    assert any("webhook" in m for m in messages), f"no webhook failure logged: {messages}"


# ---------------------------------------------------------------------------
# keyboards
# ---------------------------------------------------------------------------

def test_group_keyboard_renders_one_button_per_active_group():
    groups = [
        Group(id=1, name="Beginners A", weekday=1, start_time="09:00", is_active=1),
        Group(id=2, name="Elementary B", weekday=2, start_time="11:00", is_active=1),
    ]
    markup = group_keyboard(groups)
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert len(buttons) == 2
    assert buttons[0].callback_data == "group:1"
    assert buttons[1].callback_data == "group:2"


# ---------------------------------------------------------------------------
# /start FSM against a real database
# ---------------------------------------------------------------------------

async def test_full_registration_flow_creates_student(isolated_db):
    telegram_id = 999001
    state = make_fsm_context(telegram_id)

    msg1 = fake_message(telegram_id)
    await cmd_start(msg1, state)
    assert await state.get_state() == Reg.name.state
    msg1.answer.assert_awaited_once_with("Исмингиз ва фамилиянгиз?")

    msg2 = fake_message(telegram_id, text="  Ali Valiyev  ")
    await got_name(msg2, state)
    assert await state.get_state() == Reg.group.state
    data = await state.get_data()
    assert data["full_name"] == "Ali Valiyev"
    msg2.answer.assert_awaited_once()
    assert msg2.answer.await_args.args[0] == "Гуруҳингизни танланг:"
    assert "reply_markup" in msg2.answer.await_args.kwargs

    cb = fake_callback(telegram_id, data="group:1")  # id 1 == GROUPS[0] ("Beginners A")
    await got_group(cb, state)
    assert await state.get_state() is None
    cb.message.edit_text.assert_awaited_once_with(
        "Рўйхатдан ўтдингиз! Дарс ҳисоботлари шу ерга келади."
    )

    async with isolated_db() as s:
        student = await s.scalar(select(Student).where(Student.telegram_id == telegram_id))
    assert student is not None
    assert student.full_name == "Ali Valiyev"
    assert student.group_id == 1
    assert student.joined_at
    datetime.fromisoformat(student.joined_at)  # must be a real ISO timestamp


async def test_second_start_from_same_telegram_id_does_not_duplicate(isolated_db):
    telegram_id = 999002
    state = make_fsm_context(telegram_id)

    await cmd_start(fake_message(telegram_id), state)
    await got_name(fake_message(telegram_id, text="Vali Aliyev"), state)
    await got_group(fake_callback(telegram_id, "group:2"), state)

    async with isolated_db() as s:
        rows = (
            await s.execute(select(Student).where(Student.telegram_id == telegram_id))
        ).scalars().all()
    assert len(rows) == 1

    # a second /start from the same telegram_id must not re-register
    msg = fake_message(telegram_id)
    state2 = make_fsm_context(telegram_id)
    await cmd_start(msg, state2)

    msg.answer.assert_awaited_once_with("Сиз аллақачон рўйхатдасиз: Vali Aliyev")
    assert await state2.get_state() is None  # never entered Reg.name

    async with isolated_db() as s:
        rows = (
            await s.execute(select(Student).where(Student.telegram_id == telegram_id))
        ).scalars().all()
    assert len(rows) == 1
