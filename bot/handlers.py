from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import DEFAULT_TZ, Database, format_habit_line, local_hhmm, local_today
from bot.keyboards import (
    BTN_ADD,
    BTN_CANCEL,
    BTN_DELETE,
    BTN_DONE,
    BTN_HABITS,
    BTN_HELP,
    BTN_REMINDERS,
    BTN_SKIP,
    BTN_STATS,
    BTN_TODAY,
    cancel_kb,
    habits_inline,
    main_menu,
    note_step_kb,
    reminders_panel_kb,
    time_step_kb,
    timezone_kb,
)

router = Router()

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class AddHabit(StatesGroup):
    name = State()
    time = State()
    note = State()


def _normalize_time(text: str) -> str | None:
    text = text.strip()
    m = TIME_RE.match(text)
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


async def _cancel_state(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_menu())


async def _begin_add_wizard(message: Message, state: FSMContext) -> None:
    await state.set_state(AddHabit.name)
    await message.answer(
        "Шаг 1/3 — название привычки\n"
        "Напиши, например: Зал, Чтение, Вода",
        reply_markup=cancel_kb(),
    )


async def _send_checkin_result(message: Message, result: dict) -> None:
    habit = result["habit"]
    if result["created"]:
        await message.answer(
            f"✅ Отмечено: {format_habit_line(habit)}\n"
            f"Стрик: {result['streak']} дн.\n"
            f"Всего: {result['total']}",
            reply_markup=main_menu(),
        )
    else:
        await message.answer(
            f"Уже отмечено сегодня: {format_habit_line(habit)}\n"
            f"Стрик: {result['streak']} дн.\n"
            f"Всего: {result['total']}",
            reply_markup=main_menu(),
        )


async def _reminders_text(db: Database, user_id: int) -> tuple[str, list[dict], str]:
    tz = await db.get_timezone(user_id)
    habits = await db.list_habits(user_id)
    now = local_hhmm(tz)
    today = local_today(tz)
    lines = [
        "🔔 Напоминания",
        "",
        f"🌍 Пояс: {tz}",
        f"🕒 Сейчас: {now} ({today})",
        "",
        "Как это работает:",
        "• если у привычки есть время и 🔔 вкл — бот напишет в эту минуту",
        "• в сообщении будет кнопка «Сделано»",
        "• если уже отметил сегодня — напоминание не придёт",
        "",
    ]
    if not habits:
        lines.append("Пока нет привычек. Нажми ➕ Добавить.")
    else:
        lines.append("Нажми на привычку, чтобы вкл/выкл напоминание:")
    return "\n".join(lines), habits, tz


# ---------- start / help ----------


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    await db.upsert_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "Трекер привычек.\n\n"
        "Жми кнопки внизу — команды писать не обязательно.\n\n"
        "➕ Добавить — название → время → заметка\n"
        "✔️ Отметить — выбрать из списка\n"
        "🔔 Напоминания — пояс и вкл/выкл по привычкам\n"
        "✅ Сегодня / 📊 Статистика / 📋 Привычки\n"
        "🗑 Удалить\n\n"
        "По умолчанию пояс: Europe/Moscow.",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Как пользоваться:\n\n"
        "1) ➕ Добавить\n"
        "   → название\n"
        "   → время (кнопка / ЧЧ:ММ / пропуск)\n"
        "   → заметка / пропуск\n"
        "   Если указал время — напоминание включится само.\n\n"
        "2) 🔔 Напоминания\n"
        "   → сменить часовой пояс\n"
        "   → вкл/выкл колокольчик у привычки\n\n"
        "3) ✔️ Отметить — список кнопок\n"
        "4) ✅ Сегодня / 📊 Статистика / 📋 Привычки\n"
        "5) 🗑 Удалить\n\n"
        "❌ Отмена — выйти из мастера.\n"
        "Команды: /add /done /habits /today /stats /delete /reminders",
        reply_markup=main_menu(),
    )


@router.message(F.text == BTN_CANCEL)
async def btn_cancel(message: Message, state: FSMContext) -> None:
    await _cancel_state(message, state)


# ---------- add wizard ----------


@router.message(F.text == BTN_ADD)
async def btn_add(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await db.upsert_user(message.from_user.id, message.from_user.username)
    await _begin_add_wizard(message, state)


@router.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await db.upsert_user(message.from_user.id, message.from_user.username)

    name = (command.args or "").strip()
    if name:
        try:
            habit = await db.add_habit(message.from_user.id, name)
        except ValueError as exc:
            await message.answer(str(exc), reply_markup=main_menu())
            return
        if habit is None:
            await message.answer(f"Привычка уже есть: {name}", reply_markup=main_menu())
            return
        await message.answer(
            f"Добавлено: {format_habit_line(habit)}\n"
            "Чтобы были напоминания — добавь время через ➕ или включи в 🔔 Напоминания.",
            reply_markup=main_menu(),
        )
        return

    await _begin_add_wizard(message, state)


@router.message(StateFilter(AddHabit.name), F.text)
async def add_name(message: Message, state: FSMContext) -> None:
    assert message.text
    if message.text == BTN_CANCEL:
        await _cancel_state(message, state)
        return
    name = " ".join(message.text.split()).strip()
    if not name:
        await message.answer("Название не может быть пустым. Напиши ещё раз.")
        return
    if len(name) > 64:
        await message.answer("Слишком длинно (макс. 64). Короче, пожалуйста.")
        return
    if name.startswith("/"):
        await message.answer("Это похоже на команду. Напиши обычное название.")
        return

    await state.update_data(name=name)
    await state.set_state(AddHabit.time)
    await message.answer(
        f"Шаг 2/3 — время для «{name}»\n"
        "Выбери кнопку или напиши ЧЧ:ММ (например 07:30).\n"
        "Если укажешь время — включу ежедневное напоминание.\n"
        "Или ⏭ Пропустить.",
        reply_markup=time_step_kb(),
    )


@router.message(StateFilter(AddHabit.time), F.text)
async def add_time(message: Message, state: FSMContext) -> None:
    assert message.text
    text = message.text.strip()
    if text == BTN_CANCEL:
        await _cancel_state(message, state)
        return

    if text == BTN_SKIP:
        schedule_time = None
    else:
        schedule_time = _normalize_time(text)
        if schedule_time is None:
            await message.answer(
                "Не понял время. Формат ЧЧ:ММ, например 09:00.\n"
                "Или нажми ⏭ Пропустить / ❌ Отмена."
            )
            return

    await state.update_data(schedule_time=schedule_time)
    await state.set_state(AddHabit.note)
    await message.answer(
        "Шаг 3/3 — заметка (необязательно)\n"
        "Например: 3 подхода / 20 страниц / без телефона\n"
        "Или ⏭ Пропустить.",
        reply_markup=note_step_kb(),
    )


@router.message(StateFilter(AddHabit.note), F.text)
async def add_note(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user and message.text
    text = message.text.strip()
    if text == BTN_CANCEL:
        await _cancel_state(message, state)
        return

    note = None if text == BTN_SKIP else text
    if note and len(note) > 200:
        await message.answer("Заметка слишком длинная (макс. 200). Сократи или ⏭ Пропустить.")
        return

    data = await state.get_data()
    name = data.get("name", "")
    schedule_time = data.get("schedule_time")

    try:
        habit = await db.add_habit(
            message.from_user.id,
            name,
            schedule_time=schedule_time,
            note=note,
        )
    except ValueError as exc:
        await state.clear()
        await message.answer(str(exc), reply_markup=main_menu())
        return

    await state.clear()
    if habit is None:
        await message.answer(
            f"Привычка уже есть: {name}",
            reply_markup=main_menu(),
        )
        return

    tz = await db.get_timezone(message.from_user.id)
    extra = ""
    if habit.get("schedule_time") and habit.get("remind"):
        extra = (
            f"\n🔔 Напомню каждый день в {habit['schedule_time']} "
            f"({tz}).\nНастройки: кнопка 🔔 Напоминания"
        )
    elif not habit.get("schedule_time"):
        extra = "\nБез времени — напоминаний не будет. Можно добавить позже."

    await message.answer(
        "✅ Привычка сохранена\n"
        f"{format_habit_line(habit)}{extra}\n\n"
        "Отметить сегодня: ✔️ Отметить",
        reply_markup=main_menu(),
    )


# ---------- reminders panel ----------


@router.message(Command("reminders"))
@router.message(F.text == BTN_REMINDERS)
async def btn_reminders(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    await db.upsert_user(message.from_user.id, message.from_user.username)
    text, habits, tz = await _reminders_text(db, message.from_user.id)
    await message.answer(
        text,
        reply_markup=reminders_panel_kb(habits, tz) if habits else main_menu(),
    )


@router.callback_query(F.data == "rem:close")
async def cb_rem_close(query: CallbackQuery) -> None:
    assert query.message
    await query.message.edit_text("Панель напоминаний закрыта.")
    await query.answer()


@router.callback_query(F.data == "rem:tz")
async def cb_rem_tz(query: CallbackQuery) -> None:
    assert query.message
    await query.message.edit_text(
        "Выбери часовой пояс.\n"
        "Время привычек и напоминаний считается в этом поясе.",
        reply_markup=timezone_kb(),
    )
    await query.answer()


@router.callback_query(F.data == "rem:back")
async def cb_rem_back(query: CallbackQuery, db: Database) -> None:
    assert query.from_user and query.message
    text, habits, tz = await _reminders_text(db, query.from_user.id)
    await query.message.edit_text(text, reply_markup=reminders_panel_kb(habits, tz))
    await query.answer()


@router.callback_query(F.data.startswith("tz:"))
async def cb_set_tz(query: CallbackQuery, db: Database) -> None:
    assert query.from_user and query.data and query.message
    tz = query.data.split(":", 1)[1]
    await db.upsert_user(query.from_user.id, query.from_user.username)
    try:
        await db.set_timezone(query.from_user.id, tz)
    except Exception:
        await query.answer("Некорректный пояс", show_alert=True)
        return
    text, habits, tz_now = await _reminders_text(db, query.from_user.id)
    await query.message.edit_text(text, reply_markup=reminders_panel_kb(habits, tz_now))
    await query.answer(f"Пояс: {tz}")


@router.callback_query(F.data.startswith("rem:on:"))
@router.callback_query(F.data.startswith("rem:off:"))
@router.callback_query(F.data.startswith("rem:needtime:"))
async def cb_rem_toggle(query: CallbackQuery, db: Database) -> None:
    assert query.from_user and query.data and query.message
    parts = query.data.split(":")
    # rem:on:ID / rem:off:ID / rem:needtime:ID
    if len(parts) != 3:
        await query.answer("Ошибка", show_alert=True)
        return
    action, raw_id = parts[1], parts[2]
    try:
        habit_id = int(raw_id)
    except ValueError:
        await query.answer("Ошибка", show_alert=True)
        return

    if action == "needtime":
        await query.answer(
            "Сначала задай время: удали и добавь привычку заново с временем.",
            show_alert=True,
        )
        return

    try:
        habit = await db.set_habit_remind(
            query.from_user.id,
            habit_id,
            enabled=(action == "on"),
        )
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    if not habit:
        await query.answer("Привычка не найдена", show_alert=True)
        return

    text, habits, tz = await _reminders_text(db, query.from_user.id)
    await query.message.edit_text(text, reply_markup=reminders_panel_kb(habits, tz))
    await query.answer("🔔 вкл" if action == "on" else "🔕 выкл")


# ---------- done / delete ----------


@router.message(F.text == BTN_DONE)
async def btn_done(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer(
            "Пока нет привычек. Нажми ➕ Добавить.",
            reply_markup=main_menu(),
        )
        return
    await message.answer(
        "Что отметить сегодня?",
        reply_markup=habits_inline(habits, "done"),
    )


@router.message(Command("done"))
async def cmd_done(message: Message, command: CommandObject, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    name = (command.args or "").strip()
    if name:
        try:
            result = await db.checkin(message.from_user.id, name)
        except KeyError:
            await message.answer(f"Не найдено: {name}", reply_markup=main_menu())
            return
        await _send_checkin_result(message, result)
        return

    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer(
            "Пока нет привычек. Нажми ➕ Добавить.",
            reply_markup=main_menu(),
        )
        return
    await message.answer(
        "Что отметить сегодня?",
        reply_markup=habits_inline(habits, "done"),
    )


@router.callback_query(F.data.startswith("done:"))
async def cb_done(query: CallbackQuery, db: Database) -> None:
    assert query.from_user and query.data and query.message
    raw = query.data.split(":", 1)[1]
    if raw == "cancel":
        await query.message.edit_text("Отменено.")
        await query.answer()
        return

    try:
        habit_id = int(raw)
    except ValueError:
        await query.answer("Ошибка", show_alert=True)
        return

    try:
        result = await db.checkin_by_id(query.from_user.id, habit_id)
    except KeyError:
        await query.answer("Привычка не найдена", show_alert=True)
        return

    habit = result["habit"]
    if result["created"]:
        text = (
            f"✅ Отмечено: {format_habit_line(habit)}\n"
            f"Стрик: {result['streak']} дн.\n"
            f"Всего: {result['total']}"
        )
    else:
        text = (
            f"Уже отмечено сегодня: {format_habit_line(habit)}\n"
            f"Стрик: {result['streak']} дн.\n"
            f"Всего: {result['total']}"
        )
    await query.message.edit_text(text)
    await query.answer("Готово")


@router.message(F.text == BTN_DELETE)
async def btn_delete(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer("Нечего удалять.", reply_markup=main_menu())
        return
    await message.answer(
        "Какую привычку удалить?",
        reply_markup=habits_inline(habits, "delete"),
    )


@router.message(Command("delete"))
async def cmd_delete(message: Message, command: CommandObject, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    name = (command.args or "").strip()
    if name:
        ok = await db.archive_habit(message.from_user.id, name)
        if ok:
            await message.answer(f"Удалено (в архив): {name}", reply_markup=main_menu())
        else:
            await message.answer(
                f"Активная привычка не найдена: {name}",
                reply_markup=main_menu(),
            )
        return

    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer("Нечего удалять.", reply_markup=main_menu())
        return
    await message.answer(
        "Какую привычку удалить?",
        reply_markup=habits_inline(habits, "delete"),
    )


@router.callback_query(F.data.startswith("delete:"))
async def cb_delete(query: CallbackQuery, db: Database) -> None:
    assert query.from_user and query.data and query.message
    raw = query.data.split(":", 1)[1]
    if raw == "cancel":
        await query.message.edit_text("Отменено.")
        await query.answer()
        return

    try:
        habit_id = int(raw)
    except ValueError:
        await query.answer("Ошибка", show_alert=True)
        return

    habit = await db.archive_habit_by_id(query.from_user.id, habit_id)
    if not habit:
        await query.answer("Уже удалено или не найдено", show_alert=True)
        return

    await query.message.edit_text(f"🗑 Удалено: {habit['name']}")
    await query.answer("Удалено")


# ---------- lists ----------


@router.message(Command("habits"))
@router.message(F.text == BTN_HABITS)
async def cmd_habits(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer(
            "Пока пусто. Нажми ➕ Добавить.",
            reply_markup=main_menu(),
        )
        return
    lines = [f"• {format_habit_line(h)}" for h in habits]
    await message.answer("Твои привычки:\n" + "\n".join(lines), reply_markup=main_menu())


@router.message(Command("today"))
@router.message(F.text == BTN_TODAY)
async def cmd_today(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    rows = await db.today_status(message.from_user.id)
    if not rows:
        await message.answer(
            "Пока пусто. Нажми ➕ Добавить.",
            reply_markup=main_menu(),
        )
        return
    lines = []
    for row in rows:
        mark = "✅" if row["done"] else "⬜"
        extra = f" · 🔔 {row['schedule_time']}" if row.get("schedule_time") and row.get("remind") else (
            f" · ⏰ {row['schedule_time']}" if row.get("schedule_time") else ""
        )
        lines.append(f"{mark} {row['name']}{extra} (стрик {row['streak']})")
    done = sum(1 for r in rows if r["done"])
    await message.answer(
        f"Сегодня ({done}/{len(rows)}):\n" + "\n".join(lines),
        reply_markup=main_menu(),
    )


@router.message(Command("stats"))
@router.message(F.text == BTN_STATS)
async def cmd_stats(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    rows = await db.stats(message.from_user.id)
    if not rows:
        await message.answer(
            "Пока пусто. Нажми ➕ Добавить.",
            reply_markup=main_menu(),
        )
        return
    lines = []
    for r in rows:
        line = f"• {r['name']}: стрик {r['streak']}, всего {r['total']}"
        if r.get("schedule_time"):
            icon = "🔔" if r.get("remind") else "⏰"
            line += f", {icon} {r['schedule_time']}"
        lines.append(line)
    await message.answer("Статистика:\n" + "\n".join(lines), reply_markup=main_menu())


@router.message(StateFilter(AddHabit.name, AddHabit.time, AddHabit.note))
async def add_fallback(message: Message) -> None:
    await message.answer(
        "Сейчас идёт добавление привычки.\n"
        "Ответь текстом на текущий шаг или нажми ❌ Отмена."
    )
