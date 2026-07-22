from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.db import DAY_LABELS, format_days, normalize_days_mask

BTN_TODAY = "✅ Сегодня"
BTN_STATS = "📊 Стата"
BTN_HABITS = "📋 Список"
BTN_ADD = "➕ Добавить"
BTN_DONE = "✔️ Отметить"
BTN_EDIT = "✏️ Править"
BTN_DELETE = "🗑 Удалить"
BTN_REMINDERS = "🔔 Напомин."
BTN_HELP = "❓"
BTN_CANCEL = "❌ Отмена"
BTN_SKIP = "⏭ Пропуск"
BTN_DONE_DAYS = "✅ Готово"

TIMEZONES = [
    ("Москва", "Europe/Moscow"),
    ("Киев", "Europe/Kyiv"),
    ("Минск", "Europe/Minsk"),
    ("Алматы", "Asia/Almaty"),
    ("Тбилиси", "Asia/Tbilisi"),
    ("Ереван", "Asia/Yerevan"),
    ("Стамбул", "Europe/Istanbul"),
    ("UTC", "UTC"),
]


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_TODAY), KeyboardButton(text=BTN_DONE)],
            [KeyboardButton(text=BTN_ADD), KeyboardButton(text=BTN_HABITS)],
            [KeyboardButton(text=BTN_EDIT), KeyboardButton(text=BTN_REMINDERS)],
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_DELETE), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def time_step_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="07:00"), KeyboardButton(text="09:00"), KeyboardButton(text="12:00")],
            [KeyboardButton(text="15:00"), KeyboardButton(text="18:00"), KeyboardButton(text="21:00")],
            [KeyboardButton(text=BTN_SKIP), KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def note_step_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SKIP), KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def days_step_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Каждый день"), KeyboardButton(text="Будни"), KeyboardButton(text="Выходные")],
            [KeyboardButton(text="Выбрать дни"), KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def habits_inline(habits: list[dict], prefix: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for h in habits:
        label = h["name"]
        if h.get("paused"):
            label = f"⏸ {label}"
        if h.get("schedule_time"):
            label = f"{label} {h['schedule_time']}"
        days = format_days(h.get("days_mask"))
        if days != "каждый день":
            label = f"{label} · {days}"
        rows.append(
            [InlineKeyboardButton(text=label[:64], callback_data=f"{prefix}:{h['id']}")]
        )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=f"{prefix}:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def days_picker_kb(mask: str, prefix: str = "days") -> InlineKeyboardMarkup:
    m = set(normalize_days_mask(mask))
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i in range(7):
        mark = "✓" if str(i) in m else "·"
        row.append(
            InlineKeyboardButton(
                text=f"{mark}{DAY_LABELS[i]}",
                callback_data=f"{prefix}:tog:{i}",
            )
        )
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(text="Все", callback_data=f"{prefix}:all"),
            InlineKeyboardButton(text="Будни", callback_data=f"{prefix}:weekdays"),
            InlineKeyboardButton(text="Вых", callback_data=f"{prefix}:weekend"),
        ]
    )
    rows.append([InlineKeyboardButton(text=BTN_DONE_DAYS, callback_data=f"{prefix}:ok")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=f"{prefix}:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_habit_kb(habit_id: int, habit: dict) -> InlineKeyboardMarkup:
    paused = bool(habit.get("paused"))
    remind = bool(habit.get("remind"))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Дни", callback_data=f"edit:days:{habit_id}"),
                InlineKeyboardButton(text="⏰ Время", callback_data=f"edit:time:{habit_id}"),
            ],
            [
                InlineKeyboardButton(text="📝 Заметка", callback_data=f"edit:note:{habit_id}"),
                InlineKeyboardButton(text="✏️ Имя", callback_data=f"edit:name:{habit_id}"),
            ],
            [
                InlineKeyboardButton(
                    text="🔔 Выкл" if remind else "🔔 Вкл",
                    callback_data=f"edit:remind:{habit_id}",
                ),
                InlineKeyboardButton(
                    text="▶️ Вкл" if paused else "⏸ Пауза",
                    callback_data=f"edit:pause:{habit_id}",
                ),
            ],
            [InlineKeyboardButton(text="« К списку", callback_data="edit:list")],
            [InlineKeyboardButton(text="Закрыть", callback_data="edit:close")],
        ]
    )


def reminders_panel_kb(habits: list[dict], timezone: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for h in habits:
        if h.get("paused"):
            label = f"⏸ {h['name']}"
            cb = f"rem:paused:{h['id']}"
        elif not h.get("schedule_time"):
            label = f"· {h['name']} · нет времени"
            cb = f"rem:needtime:{h['id']}"
        elif h.get("remind"):
            label = f"🔔 {h['name']} {h['schedule_time']}"
            cb = f"rem:off:{h['id']}"
        else:
            label = f"🔕 {h['name']} {h['schedule_time']}"
            cb = f"rem:on:{h['id']}"
        days = format_days(h.get("days_mask"))
        if days != "каждый день":
            label = f"{label} · {days}"
        rows.append([InlineKeyboardButton(text=label[:64], callback_data=cb)])
    rows.append(
        [InlineKeyboardButton(text=f"🌍 {timezone}", callback_data="rem:tz")]
    )
    rows.append([InlineKeyboardButton(text="Закрыть", callback_data="rem:close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def timezone_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for title, tz in TIMEZONES:
        row.append(InlineKeyboardButton(text=title, callback_data=f"tz:{tz}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="rem:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def undo_checkin_kb(habit_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩ Отменить отметку", callback_data=f"undo:{habit_id}")]
        ]
    )
