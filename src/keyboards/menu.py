from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def quick_menu() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура быстрых действий под полем ввода."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📅 Сегодня"),
                KeyboardButton(text="📆 Завтра"),
            ],
            [
                KeyboardButton(text="🗓 Неделя"),
                KeyboardButton(text="🔄 Сменить группу"),
            ],
            [KeyboardButton(text="➡️ Следующая неделя")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери быстрое действие…",
    )


def cancel_group_menu() -> ReplyKeyboardMarkup:
    """Клавиатура во время смены группы."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_menu() -> InlineKeyboardMarkup:
    """Глубокое главное меню — оставляем как есть."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Расписание", callback_data="menu:schedule")
    kb.button(text="⚙️ Настройки", callback_data="menu:settings")
    kb.adjust(1)
    return kb.as_markup()


def schedule_menu(kind: str | None = None) -> InlineKeyboardMarkup:
    """Подменю расписания."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Сегодня", callback_data="schedule:today")
    kb.button(text="📆 Завтра", callback_data="schedule:tomorrow")
    kb.button(text="🗓 Эта неделя", callback_data="schedule:week:0")
    kb.button(text="➡️ Следующая неделя", callback_data="schedule:week:1")
    kb.button(text="⬅️ Назад", callback_data="nav:menu")
    kb.adjust(2)
    return kb.as_markup()


def schedule_nav_menu(kind: str) -> InlineKeyboardMarkup:
    """Меню навигации при просмотре конкретного расписания."""
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад к расписанию", callback_data="nav:schedule")
    kb.button(text="🔄 Обновить", callback_data=f"schedule:refresh:{kind}")
    kb.adjust(2)
    return kb.as_markup()


def settings_menu() -> InlineKeyboardMarkup:
    """Подменю настроек."""
    kb = InlineKeyboardBuilder()
    kb.button(text="⚙️ Сменить группу", callback_data="group:change")
    kb.button(text="🔄 Обновить расписание", callback_data="schedule:refresh_menu")
    kb.button(text="⬅️ Назад", callback_data="nav:menu")
    kb.adjust(1)
    return kb.as_markup()
