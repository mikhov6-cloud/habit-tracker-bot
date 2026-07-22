from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# Reply menu labels
BTN_TODAY = "✅ Сегодня"
BTN_STATS = "📊 Статистика"
BTN_HABITS = "📋 Привычки"
BTN_ADD = "➕ Добавить"
BTN_DONE = "✔️ Отметить"
BTN_DELETE = "🗑 Удалить"
BTN_REMINDERS = "🔔 Напоминания"
BTN_HELP = "❓ Помощь"
BTN_CANCEL = "❌ Отмена"
BTN_SKIP = "⏭ Пропустить"

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
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_REMINDERS)],
            [KeyboardButton(text=BTN_DELETE), KeyboardButton(text=BTN_HELP)],
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
            [
                KeyboardButton(text="07:00"),
                KeyboardButton(text="09:00"),
                KeyboardButton(text="12:00"),
            ],
            [
                KeyboardButton(text="15:00"),
                KeyboardButton(text="18:00"),
                KeyboardButton(text="21:00"),
            ],
            [KeyboardButton(text=BTN_SKIP), KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def note_step_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SKIP), KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def habits_inline(
    habits: list[dict],
    prefix: str,
) -> InlineKeyboardMarkup:
    """prefix: done | delete"""
    rows: list[list[InlineKeyboardButton]] = []
    for h in habits:
        label = h["name"]
        if h.get("schedule_time"):
            label = f"{label} ({h['schedule_time']})"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=f"{prefix}:{h['id']}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="Отмена", callback_data=f"{prefix}:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminders_panel_kb(habits: list[dict], timezone: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for h in habits:
        if not h.get("schedule_time"):
            label = f"⚪ {h['name']} · нет времени"
            # tapping opens noop tip via callback rem:needtime:id
            cb = f"rem:needtime:{h['id']}"
        elif h.get("remind"):
            label = f"🔔 {h['name']} · {h['schedule_time']} · вкл"
            cb = f"rem:off:{h['id']}"
        else:
            label = f"🔕 {h['name']} · {h['schedule_time']} · выкл"
            cb = f"rem:on:{h['id']}"
        rows.append([InlineKeyboardButton(text=label[:64], callback_data=cb)])

    rows.append(
        [InlineKeyboardButton(text=f"🌍 Часовой пояс: {timezone}", callback_data="rem:tz")]
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
