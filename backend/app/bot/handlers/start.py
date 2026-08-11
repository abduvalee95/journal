from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import Student, Group
from app.bot.keyboards import group_keyboard
from app.utils.localtime import bishkek_now

router = Router()


class Reg(StatesGroup):
    name = State()
    group = State()


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    async with AsyncSessionLocal() as s:
        existing = await s.scalar(select(Student).where(Student.telegram_id == msg.from_user.id))
    if existing:
        await msg.answer(f"Сиз аллақачон рўйхатдасиз: {existing.full_name}")
        return
    await state.set_state(Reg.name)
    await msg.answer("Исмингиз ва фамилиянгиз?")


@router.message(Reg.name)
async def got_name(msg: Message, state: FSMContext):
    await state.update_data(full_name=msg.text.strip())
    async with AsyncSessionLocal() as s:
        groups = (await s.execute(
            select(Group).where(Group.is_active == 1).order_by(Group.weekday)
        )).scalars().all()
    await state.set_state(Reg.group)
    await msg.answer("Гуруҳингизни танланг:", reply_markup=group_keyboard(groups))


@router.callback_query(Reg.group, F.data.startswith("group:"))
async def got_group(cb: CallbackQuery, state: FSMContext):
    group_id = int(cb.data.split(":")[1])
    data = await state.get_data()
    async with AsyncSessionLocal() as s:
        s.add(Student(
            telegram_id=cb.from_user.id,
            full_name=data["full_name"],
            group_id=group_id,
            joined_at=bishkek_now().isoformat(),
        ))
        await s.commit()
    await state.clear()
    await cb.message.edit_text("Рўйхатдан ўтдингиз! Дарс ҳисоботлари шу ерга келади.")
