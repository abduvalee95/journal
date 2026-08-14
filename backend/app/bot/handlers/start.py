import re

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message, WebAppInfo)
from sqlalchemy import select

from app.bot.keyboards import group_keyboard
from app.config import settings
from app.db.models import Group, Student
from app.db.session import AsyncSessionLocal
from app.utils.localtime import bishkek_now

router = Router()

MAX_NAME_LENGTH = 60

# Letters (any script, so Cyrillic and Latin both work), spaces, apostrophes,
# hyphens and dots only. A student's name is attacker-chosen -- registration is
# open -- and it is interpolated into the prompt that writes every student's
# report for that group, for as long as they stay enrolled. Newlines and
# brackets in a name are how that prompt gets rewritten.
_NAME_RE = re.compile(r"^[^\W\d_][\w\s'’\-.]*$", re.UNICODE)


def clean_full_name(raw: str | None) -> str | None:
    """Return a storable name, or None if it isn't one."""
    if not isinstance(raw, str):
        return None
    name = " ".join(raw.split())          # collapse all whitespace, incl. newlines
    if not 2 <= len(name) <= MAX_NAME_LENGTH:
        return None
    if not _NAME_RE.match(name):
        return None
    return name


class Reg(StatesGroup):
    name = State()
    group = State()


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    if msg.from_user and msg.from_user.id == settings.teacher_telegram_id:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📱 Jurnalni ochish", web_app=WebAppInfo(url=settings.miniapp_url))
        ]])
        await msg.answer("Assalomu alaykum, Ustoz! Jurnalni ochish uchun quyidagi tugmani bosing:", reply_markup=kb)
        return

    async with AsyncSessionLocal() as s:
        existing = await s.scalar(select(Student).where(Student.telegram_id == msg.from_user.id))
    if existing:
        await msg.answer(f"Сиз аллақачон рўйхатдасиз: {existing.full_name}")
        return
    await state.set_state(Reg.name)
    await msg.answer("Исмингиз ва фамилиянгиз?")


@router.message(Reg.name, F.text)
async def got_name(msg: Message, state: FSMContext):
    name = clean_full_name(msg.text)
    if name is None:
        await msg.answer(
            "Исм-фамилиянгизни ҳарфлар билан ёзинг (2-60 та белги)."
        )
        return
    await state.update_data(full_name=name)
    async with AsyncSessionLocal() as s:
        groups = (await s.execute(
            select(Group).where(Group.is_active == 1).order_by(Group.weekday)
        )).scalars().all()
    await state.set_state(Reg.group)
    await msg.answer("Гуруҳингизни танланг:", reply_markup=group_keyboard(groups))


@router.message(Reg.name)
async def got_non_text_name(msg: Message):
    """Anything that isn't text while we're waiting for a name.

    Without this the handler above ran on stickers and photos and raised
    AttributeError on `msg.text.strip()`, which becomes a 500 -- and Telegram
    redelivers 5xx, so the same update looped.
    """
    await msg.answer("Илтимос, исм-фамилиянгизни матн кўринишида юборинг.")


@router.callback_query(Reg.group, F.data.startswith("group:"))
async def got_group(cb: CallbackQuery, state: FSMContext):
    try:
        group_id = int(cb.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await cb.answer("Гуруҳ танланмади.")
        return

    data = await state.get_data()
    full_name = data.get("full_name")
    if not full_name:
        # FSM state is in memory, so a restart mid-registration loses it and
        # this used to raise KeyError, stranding the student.
        await state.clear()
        await cb.message.edit_text("Рўйхатдан ўтиш бекор бўлди. /start ни қайта юборинг.")
        return

    async with AsyncSessionLocal() as s:
        group = await s.scalar(
            select(Group).where(Group.id == group_id, Group.is_active == 1)
        )
        if not group:
            await cb.answer("Бу гуруҳ мавжуд эмас.")
            return

        existing = await s.scalar(
            select(Student).where(Student.telegram_id == cb.from_user.id)
        )
        if existing:
            # students.telegram_id is UNIQUE: a double tap on the group button
            # would otherwise raise IntegrityError out of the webhook.
            await state.clear()
            await cb.message.edit_text(f"Сиз аллақачон рўйхатдасиз: {existing.full_name}")
            return

        s.add(Student(
            telegram_id=cb.from_user.id,
            full_name=full_name,
            group_id=group_id,
            joined_at=bishkek_now().isoformat(),
        ))
        await s.commit()

    await state.clear()
    await cb.message.edit_text("Рўйхатдан ўтдингиз! Дарс ҳисоботлари шу ерга келади.")


@router.message(F.text & ~F.text.startswith("/"))
async def fallback_prompt_registration(msg: Message, state: FSMContext):
    """Any other text from someone who isn't the teacher.

    The spec says a student sending *any* message should start registration;
    previously only /start did, and everything else was met with silence.
    """
    if msg.from_user and msg.from_user.id == settings.teacher_telegram_id:
        return
    if await state.get_state() is not None:
        return
    async with AsyncSessionLocal() as s:
        existing = await s.scalar(select(Student).where(Student.telegram_id == msg.from_user.id))
    if existing:
        await msg.answer(f"Сиз аллақачон рўйхатдасиз: {existing.full_name}")
        return
    await state.set_state(Reg.name)
    await msg.answer("Исмингиз ва фамилиянгиз?")
