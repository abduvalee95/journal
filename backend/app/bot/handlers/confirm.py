"""Inline-keyboard callbacks on the draft-ready message.

Saving is deliberately not done here: POST /api/lessons/{id}/confirm is the
single write path (it is the one that fills the outbox), and the teacher
reaches it from the Mini App. These handlers just acknowledge the tap so the
button stops spinning.
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.config import settings

router = Router()


@router.callback_query(F.data.startswith("confirm:"))
async def cb_confirm(cb: CallbackQuery):
    if cb.from_user.id != settings.teacher_telegram_id:
        return
    await cb.answer("Mini App'да Сақлаш тугмасини босинг.")


@router.callback_query(F.data.startswith("edit:"))
async def cb_edit(cb: CallbackQuery):
    if cb.from_user.id != settings.teacher_telegram_id:
        return
    await cb.answer("Mini App'да таҳрирланг.")
