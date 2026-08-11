from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

WEEKDAY_UZ = {1: "Душ", 2: "Сеш", 3: "Чор", 4: "Пай", 5: "Жум", 6: "Шан"}


def group_keyboard(groups) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for g in groups:
        b.button(text=f"{g.name} ({WEEKDAY_UZ[g.weekday]})", callback_data=f"group:{g.id}")
    b.adjust(2)
    return b.as_markup()


def confirm_keyboard(lesson_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Сақлаш", callback_data=f"confirm:{lesson_id}")
    b.button(text="✏️ Таҳрирлаш", callback_data=f"edit:{lesson_id}")
    b.adjust(2)
    return b.as_markup()
