from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

WEEKDAY_UZ = {1: "Dush", 2: "Sesh", 3: "Chor", 4: "Pay", 5: "Jum", 6: "Shan"}


def group_keyboard(groups) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for g in groups:
        b.button(text=f"{g.name} ({WEEKDAY_UZ[g.weekday]})", callback_data=f"group:{g.id}")
    b.adjust(2)
    return b.as_markup()


def confirm_keyboard(lesson_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Saqlash", callback_data=f"confirm:{lesson_id}")
    b.button(text="✏️ Tahrirlash", callback_data=f"edit:{lesson_id}")
    b.adjust(2)
    return b.as_markup()
