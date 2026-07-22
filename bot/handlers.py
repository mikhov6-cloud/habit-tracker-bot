from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import (
    ALL_DAYS_MASK,
    Database,
    format_days,
    format_habit_line,
    local_hhmm,
    local_today,
    normalize_days_mask,
)
from bot.keyboards import (
    BTN_ADD,
    BTN_CANCEL,
    BTN_DELETE,
    BTN_DONE,
    BTN_EDIT,
    BTN_HABITS,
    BTN_HELP,
    BTN_REMINDERS,
    BTN_SKIP,
    BTN_STATS,
    BTN_TODAY,
    cancel_kb,
    days_picker_kb,
    days_step_kb,
    edit_habit_kb,
    habits_inline,
    main_menu,
    note_step_kb,
    reminders_panel_kb,
    time_step_kb,
    timezone_kb,
    undo_checkin_kb,
)

router = Router()
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class AddHabit(StatesGroup):
    name = State()
    days = State()
    time = State()
    note = State()


class EditHabit(StatesGroup):
    time = State()
    note = State()
    name = State()
    days = State()


def _norm_time(text: str) -> str | None:
    m = TIME_RE.match(text.strip())
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


async def _cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ок.", reply_markup=main_menu())


async def _checkin_text(result: dict) -> str:
    h = result["habit"]
    if result["created"]:
        return f"✅ {format_habit_line(h)}\nстрик {result['streak']} · всего {result['total']}"
    return f"Уже ✅ {format_habit_line(h)}\nстрик {result['streak']} · всего {result['total']}"


async def _reminders_text(db: Database, user_id: int) -> tuple[str, list[dict], str]:
    tz = await db.get_timezone(user_id)
    habits = await db.list_habits(user_id)
    text = f"🔔 Напоминания\n{tz} · сейчас {local_hhmm(tz)}\nтап = вкл/выкл"
    return text, habits, tz


async def _edit_card(db: Database, user_id: int, habit_id: int) -> tuple[str, dict] | None:
    h = await db.get_habit_by_id(user_id, habit_id)
    if not h or not h["is_active"]:
        return None
    text = (
        f"✏️ {format_habit_line(h)}\n"
        f"дни: {format_days(h.get('days_mask'))}\n"
        f"пауза: {'да' if h.get('paused') else 'нет'} · "
        f"напомин.: {'да' if h.get('remind') else 'нет'}"
    )
    return text, h


# ----- start / help / cancel -----


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    await db.upsert_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "Трекер привычек.\n"
        "➕ добавить · ✔️ отметить · ✏️ править · 🔔 напомин.",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "➕ имя → дни → время → заметка\n"
        "📅 дни: каждый / будни / вых / свои\n"
        "✔️ отметить · ✏️ править · 🔔 вкл/выкл\n"
        "⏸ пауза в правке · стрик только по своим дням",
        reply_markup=main_menu(),
    )


@router.message(F.text == BTN_CANCEL)
async def btn_cancel(message: Message, state: FSMContext) -> None:
    await _cancel(message, state)


# ----- add wizard -----


@router.message(F.text == BTN_ADD)
async def btn_add(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await db.upsert_user(message.from_user.id, message.from_user.username)
    await state.set_state(AddHabit.name)
    await message.answer("Название:", reply_markup=cancel_kb())


@router.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await db.upsert_user(message.from_user.id, message.from_user.username)
    name = (command.args or "").strip()
    if not name:
        await state.set_state(AddHabit.name)
        await message.answer("Название:", reply_markup=cancel_kb())
        return
    try:
        habit = await db.add_habit(message.from_user.id, name)
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=main_menu())
        return
    if habit is None:
        await message.answer("Уже есть.", reply_markup=main_menu())
        return
    await message.answer(
        f"+ {format_habit_line(habit)}\nдни/время — через ✏️",
        reply_markup=main_menu(),
    )


@router.message(StateFilter(AddHabit.name), F.text)
async def add_name(message: Message, state: FSMContext) -> None:
    assert message.text
    if message.text == BTN_CANCEL:
        await _cancel(message, state)
        return
    name = " ".join(message.text.split()).strip()
    if not name or name.startswith("/"):
        await message.answer("Другое название.")
        return
    if len(name) > 64:
        await message.answer("Макс. 64.")
        return
    await state.update_data(name=name, days_mask=ALL_DAYS_MASK)
    await state.set_state(AddHabit.days)
    await message.answer(
        f"«{name}» — какие дни?",
        reply_markup=days_step_kb(),
    )


@router.message(StateFilter(AddHabit.days), F.text)
async def add_days_text(message: Message, state: FSMContext) -> None:
    assert message.text
    t = message.text.strip()
    if t == BTN_CANCEL:
        await _cancel(message, state)
        return
    if t == "Каждый день":
        await state.update_data(days_mask=ALL_DAYS_MASK)
        await state.set_state(AddHabit.time)
        await message.answer("Время (или пропуск):", reply_markup=time_step_kb())
        return
    if t == "Будни":
        await state.update_data(days_mask="01234")
        await state.set_state(AddHabit.time)
        await message.answer("Время (или пропуск):", reply_markup=time_step_kb())
        return
    if t == "Выходные":
        await state.update_data(days_mask="56")
        await state.set_state(AddHabit.time)
        await message.answer("Время (или пропуск):", reply_markup=time_step_kb())
        return
    if t == "Выбрать дни":
        data = await state.get_data()
        mask = data.get("days_mask", ALL_DAYS_MASK)
        await message.answer(
            f"Дни: {format_days(mask)}\nтап = вкл/выкл",
            reply_markup=days_picker_kb(mask, "addays"),
        )
        return
    await message.answer("Кнопка из меню или «Выбрать дни».")


@router.callback_query(StateFilter(AddHabit.days), F.data.startswith("addays:"))
async def cb_add_days(query: CallbackQuery, state: FSMContext) -> None:
    assert query.data and query.message
    action = query.data.split(":", 1)[1]
    data = await state.get_data()
    mask = normalize_days_mask(data.get("days_mask"))

    if action == "cancel":
        await state.clear()
        await query.message.edit_text("Ок.")
        await query.message.answer("Меню.", reply_markup=main_menu())
        await query.answer()
        return
    if action == "all":
        mask = ALL_DAYS_MASK
    elif action == "weekdays":
        mask = "01234"
    elif action == "weekend":
        mask = "56"
    elif action.startswith("tog:"):
        day = action.split(":")[1]
        s = set(mask)
        if day in s:
            s.remove(day)
        else:
            s.add(day)
        mask = normalize_days_mask("".join(sorted(s)))
    elif action == "ok":
        await state.update_data(days_mask=mask)
        await state.set_state(AddHabit.time)
        await query.message.edit_text(f"Дни: {format_days(mask)}")
        await query.message.answer("Время (или пропуск):", reply_markup=time_step_kb())
        await query.answer()
        return
    else:
        await query.answer()
        return

    await state.update_data(days_mask=mask)
    await query.message.edit_text(
        f"Дни: {format_days(mask)}\nтап = вкл/выкл",
        reply_markup=days_picker_kb(mask, "addays"),
    )
    await query.answer()


@router.message(StateFilter(AddHabit.time), F.text)
async def add_time(message: Message, state: FSMContext) -> None:
    assert message.text
    t = message.text.strip()
    if t == BTN_CANCEL:
        await _cancel(message, state)
        return
    if t == BTN_SKIP:
        schedule_time = None
    else:
        schedule_time = _norm_time(t)
        if schedule_time is None:
            await message.answer("Формат ЧЧ:ММ или пропуск.")
            return
    await state.update_data(schedule_time=schedule_time)
    await state.set_state(AddHabit.note)
    await message.answer("Заметка (или пропуск):", reply_markup=note_step_kb())


@router.message(StateFilter(AddHabit.note), F.text)
async def add_note(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user and message.text
    t = message.text.strip()
    if t == BTN_CANCEL:
        await _cancel(message, state)
        return
    note = None if t == BTN_SKIP else t
    if note and len(note) > 200:
        await message.answer("Макс. 200.")
        return
    data = await state.get_data()
    try:
        habit = await db.add_habit(
            message.from_user.id,
            data.get("name", ""),
            schedule_time=data.get("schedule_time"),
            note=note,
            days_mask=data.get("days_mask"),
        )
    except ValueError as exc:
        await state.clear()
        await message.answer(str(exc), reply_markup=main_menu())
        return
    await state.clear()
    if habit is None:
        await message.answer("Уже есть.", reply_markup=main_menu())
        return
    extra = ""
    if habit.get("schedule_time") and habit.get("remind"):
        extra = f"\n🔔 {habit['schedule_time']} · {format_days(habit.get('days_mask'))}"
    await message.answer(
        f"+ {format_habit_line(habit)}{extra}",
        reply_markup=main_menu(),
    )


@router.message(StateFilter(AddHabit.name, AddHabit.days, AddHabit.time, AddHabit.note))
async def add_fallback(message: Message) -> None:
    await message.answer("Ответь на шаг или ❌")


# ----- done / undo -----


@router.message(F.text == BTN_DONE)
async def btn_done(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    habits = [h for h in await db.list_habits(message.from_user.id) if not h.get("paused")]
    if not habits:
        await message.answer("Пусто.", reply_markup=main_menu())
        return
    await message.answer("Что отметить?", reply_markup=habits_inline(habits, "done"))


@router.message(Command("done"))
async def cmd_done(message: Message, command: CommandObject, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    name = (command.args or "").strip()
    if name:
        try:
            result = await db.checkin(message.from_user.id, name)
        except KeyError:
            await message.answer("Не найдено.", reply_markup=main_menu())
            return
        await message.answer(
            await _checkin_text(result),
            reply_markup=main_menu(),
        )
        if result["created"]:
            await message.answer(
                "Отменить?",
                reply_markup=undo_checkin_kb(result["habit"]["id"]),
            )
        return
    habits = [h for h in await db.list_habits(message.from_user.id) if not h.get("paused")]
    if not habits:
        await message.answer("Пусто.", reply_markup=main_menu())
        return
    await message.answer("Что отметить?", reply_markup=habits_inline(habits, "done"))


@router.callback_query(F.data.startswith("done:"))
async def cb_done(query: CallbackQuery, db: Database) -> None:
    assert query.from_user and query.data and query.message
    raw = query.data.split(":", 1)[1]
    if raw == "cancel":
        await query.message.edit_text("Ок.")
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
        await query.answer("Нет", show_alert=True)
        return
    text = await _checkin_text(result)
    kb = undo_checkin_kb(habit_id) if result["created"] else None
    await query.message.edit_text(text, reply_markup=kb)
    await query.answer("Ок")


@router.callback_query(F.data.startswith("undo:"))
async def cb_undo(query: CallbackQuery, db: Database) -> None:
    assert query.from_user and query.data and query.message
    try:
        habit_id = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.answer("Ошибка", show_alert=True)
        return
    ok = await db.undo_checkin_by_id(query.from_user.id, habit_id)
    if ok:
        await query.message.edit_text("↩ отметка снята")
        await query.answer("Снято")
    else:
        await query.answer("Нечего снимать", show_alert=True)


# ----- delete -----


@router.message(F.text == BTN_DELETE)
async def btn_delete(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer("Пусто.", reply_markup=main_menu())
        return
    await message.answer("Удалить:", reply_markup=habits_inline(habits, "delete"))


@router.message(Command("delete"))
async def cmd_delete(message: Message, command: CommandObject, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    name = (command.args or "").strip()
    if name:
        ok = await db.archive_habit(message.from_user.id, name)
        await message.answer("Удалено." if ok else "Нет.", reply_markup=main_menu())
        return
    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer("Пусто.", reply_markup=main_menu())
        return
    await message.answer("Удалить:", reply_markup=habits_inline(habits, "delete"))


@router.callback_query(F.data.startswith("delete:"))
async def cb_delete(query: CallbackQuery, db: Database) -> None:
    assert query.from_user and query.data and query.message
    raw = query.data.split(":", 1)[1]
    if raw == "cancel":
        await query.message.edit_text("Ок.")
        await query.answer()
        return
    try:
        habit_id = int(raw)
    except ValueError:
        await query.answer("Ошибка", show_alert=True)
        return
    habit = await db.archive_habit_by_id(query.from_user.id, habit_id)
    if not habit:
        await query.answer("Нет", show_alert=True)
        return
    await query.message.edit_text(f"🗑 {habit['name']}")
    await query.answer("Ок")


# ----- edit -----


@router.message(F.text == BTN_EDIT)
@router.message(Command("edit"))
async def btn_edit(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer("Пусто.", reply_markup=main_menu())
        return
    await message.answer("Что править?", reply_markup=habits_inline(habits, "editpick"))


@router.callback_query(F.data.startswith("editpick:"))
async def cb_edit_pick(query: CallbackQuery, state: FSMContext, db: Database) -> None:
    assert query.from_user and query.data and query.message
    raw = query.data.split(":", 1)[1]
    if raw == "cancel":
        await query.message.edit_text("Ок.")
        await query.answer()
        return
    try:
        habit_id = int(raw)
    except ValueError:
        await query.answer("Ошибка", show_alert=True)
        return
    card = await _edit_card(db, query.from_user.id, habit_id)
    if not card:
        await query.answer("Нет", show_alert=True)
        return
    text, h = card
    await state.update_data(edit_id=habit_id)
    await query.message.edit_text(text, reply_markup=edit_habit_kb(habit_id, h))
    await query.answer()


@router.callback_query(F.data == "edit:close")
async def cb_edit_close(query: CallbackQuery, state: FSMContext) -> None:
    assert query.message
    await state.clear()
    await query.message.edit_text("Ок.")
    await query.answer()


@router.callback_query(F.data == "edit:list")
async def cb_edit_list(query: CallbackQuery, state: FSMContext, db: Database) -> None:
    assert query.from_user and query.message
    await state.clear()
    habits = await db.list_habits(query.from_user.id)
    await query.message.edit_text("Что править?", reply_markup=habits_inline(habits, "editpick"))
    await query.answer()


@router.callback_query(F.data.startswith("edit:pause:"))
async def cb_edit_pause(query: CallbackQuery, db: Database) -> None:
    assert query.from_user and query.data and query.message
    habit_id = int(query.data.rsplit(":", 1)[1])
    h = await db.get_habit_by_id(query.from_user.id, habit_id)
    if not h:
        await query.answer("Нет", show_alert=True)
        return
    h2 = await db.set_habit_paused(query.from_user.id, habit_id, not bool(h.get("paused")))
    assert h2
    text = (
        f"✏️ {format_habit_line(h2)}\n"
        f"дни: {format_days(h2.get('days_mask'))}\n"
        f"пауза: {'да' if h2.get('paused') else 'нет'} · "
        f"напомин.: {'да' if h2.get('remind') else 'нет'}"
    )
    await query.message.edit_text(text, reply_markup=edit_habit_kb(habit_id, h2))
    await query.answer("⏸" if h2.get("paused") else "▶️")


@router.callback_query(F.data.startswith("edit:remind:"))
async def cb_edit_remind(query: CallbackQuery, db: Database) -> None:
    assert query.from_user and query.data and query.message
    habit_id = int(query.data.rsplit(":", 1)[1])
    h = await db.get_habit_by_id(query.from_user.id, habit_id)
    if not h:
        await query.answer("Нет", show_alert=True)
        return
    try:
        h2 = await db.set_habit_remind(query.from_user.id, habit_id, not bool(h.get("remind")))
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    assert h2
    text = (
        f"✏️ {format_habit_line(h2)}\n"
        f"дни: {format_days(h2.get('days_mask'))}\n"
        f"пауза: {'да' if h2.get('paused') else 'нет'} · "
        f"напомин.: {'да' if h2.get('remind') else 'нет'}"
    )
    await query.message.edit_text(text, reply_markup=edit_habit_kb(habit_id, h2))
    await query.answer("🔔" if h2.get("remind") else "🔕")


@router.callback_query(F.data.startswith("edit:days:"))
async def cb_edit_days_open(query: CallbackQuery, state: FSMContext, db: Database) -> None:
    assert query.from_user and query.data and query.message
    habit_id = int(query.data.rsplit(":", 1)[1])
    h = await db.get_habit_by_id(query.from_user.id, habit_id)
    if not h:
        await query.answer("Нет", show_alert=True)
        return
    mask = normalize_days_mask(h.get("days_mask"))
    await state.set_state(EditHabit.days)
    await state.update_data(edit_id=habit_id, days_mask=mask)
    await query.message.edit_text(
        f"Дни «{h['name']}»: {format_days(mask)}",
        reply_markup=days_picker_kb(mask, "edays"),
    )
    await query.answer()


@router.callback_query(StateFilter(EditHabit.days), F.data.startswith("edays:"))
async def cb_edit_days(query: CallbackQuery, state: FSMContext, db: Database) -> None:
    assert query.from_user and query.data and query.message
    action = query.data.split(":", 1)[1]
    data = await state.get_data()
    habit_id = int(data["edit_id"])
    mask = normalize_days_mask(data.get("days_mask"))

    if action == "cancel":
        await state.clear()
        card = await _edit_card(db, query.from_user.id, habit_id)
        if card:
            text, h = card
            await query.message.edit_text(text, reply_markup=edit_habit_kb(habit_id, h))
        await query.answer()
        return
    if action == "all":
        mask = ALL_DAYS_MASK
    elif action == "weekdays":
        mask = "01234"
    elif action == "weekend":
        mask = "56"
    elif action.startswith("tog:"):
        day = action.split(":")[1]
        s = set(mask)
        if day in s:
            s.remove(day)
        else:
            s.add(day)
        mask = normalize_days_mask("".join(sorted(s)))
    elif action == "ok":
        h2 = await db.update_habit(query.from_user.id, habit_id, days_mask=mask)
        await state.clear()
        if not h2:
            await query.answer("Нет", show_alert=True)
            return
        text = (
            f"✏️ {format_habit_line(h2)}\n"
            f"дни: {format_days(h2.get('days_mask'))}\n"
            f"пауза: {'да' if h2.get('paused') else 'нет'} · "
            f"напомин.: {'да' if h2.get('remind') else 'нет'}"
        )
        await query.message.edit_text(text, reply_markup=edit_habit_kb(habit_id, h2))
        await query.answer("Сохранено")
        return
    else:
        await query.answer()
        return

    await state.update_data(days_mask=mask)
    h = await db.get_habit_by_id(query.from_user.id, habit_id)
    name = h["name"] if h else ""
    await query.message.edit_text(
        f"Дни «{name}»: {format_days(mask)}",
        reply_markup=days_picker_kb(mask, "edays"),
    )
    await query.answer()


@router.callback_query(F.data.startswith("edit:time:"))
async def cb_edit_time(query: CallbackQuery, state: FSMContext, db: Database) -> None:
    assert query.from_user and query.data and query.message
    habit_id = int(query.data.rsplit(":", 1)[1])
    await state.set_state(EditHabit.time)
    await state.update_data(edit_id=habit_id)
    await query.message.answer("Новое время ЧЧ:ММ или «-» чтобы убрать:", reply_markup=cancel_kb())
    await query.answer()


@router.callback_query(F.data.startswith("edit:note:"))
async def cb_edit_note(query: CallbackQuery, state: FSMContext) -> None:
    assert query.data and query.message
    habit_id = int(query.data.rsplit(":", 1)[1])
    await state.set_state(EditHabit.note)
    await state.update_data(edit_id=habit_id)
    await query.message.answer("Новая заметка или «-»:", reply_markup=cancel_kb())
    await query.answer()


@router.callback_query(F.data.startswith("edit:name:"))
async def cb_edit_name(query: CallbackQuery, state: FSMContext) -> None:
    assert query.data and query.message
    habit_id = int(query.data.rsplit(":", 1)[1])
    await state.set_state(EditHabit.name)
    await state.update_data(edit_id=habit_id)
    await query.message.answer("Новое имя:", reply_markup=cancel_kb())
    await query.answer()


@router.message(StateFilter(EditHabit.time), F.text)
async def edit_time_msg(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user and message.text
    if message.text == BTN_CANCEL:
        await _cancel(message, state)
        return
    data = await state.get_data()
    habit_id = int(data["edit_id"])
    t = message.text.strip()
    new_time: str | None
    if t in {"-", "—", "нет", "убрать"}:
        new_time = None
    else:
        new_time = _norm_time(t)
        if new_time is None:
            await message.answer("ЧЧ:ММ или -")
            return
    try:
        h = await db.update_habit(message.from_user.id, habit_id, schedule_time=new_time)
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=main_menu())
        await state.clear()
        return
    await state.clear()
    if not h:
        await message.answer("Нет.", reply_markup=main_menu())
        return
    await message.answer(f"Ок · {format_habit_line(h)}", reply_markup=main_menu())


@router.message(StateFilter(EditHabit.note), F.text)
async def edit_note_msg(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user and message.text
    if message.text == BTN_CANCEL:
        await _cancel(message, state)
        return
    data = await state.get_data()
    habit_id = int(data["edit_id"])
    t = message.text.strip()
    note = None if t in {"-", "—", "нет"} else t
    try:
        h = await db.update_habit(message.from_user.id, habit_id, note=note)
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=main_menu())
        await state.clear()
        return
    await state.clear()
    if not h:
        await message.answer("Нет.", reply_markup=main_menu())
        return
    await message.answer(f"Ок · {format_habit_line(h)}", reply_markup=main_menu())


@router.message(StateFilter(EditHabit.name), F.text)
async def edit_name_msg(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user and message.text
    if message.text == BTN_CANCEL:
        await _cancel(message, state)
        return
    data = await state.get_data()
    habit_id = int(data["edit_id"])
    try:
        h = await db.update_habit(message.from_user.id, habit_id, name=message.text)
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=main_menu())
        await state.clear()
        return
    await state.clear()
    if not h:
        await message.answer("Нет.", reply_markup=main_menu())
        return
    await message.answer(f"Ок · {format_habit_line(h)}", reply_markup=main_menu())


# ----- reminders -----


@router.message(Command("reminders"))
@router.message(F.text == BTN_REMINDERS)
async def btn_reminders(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    await db.upsert_user(message.from_user.id, message.from_user.username)
    text, habits, tz = await _reminders_text(db, message.from_user.id)
    if not habits:
        await message.answer("Пусто.", reply_markup=main_menu())
        return
    await message.answer(text, reply_markup=reminders_panel_kb(habits, tz))


@router.callback_query(F.data == "rem:close")
async def cb_rem_close(query: CallbackQuery) -> None:
    assert query.message
    await query.message.edit_text("Ок.")
    await query.answer()


@router.callback_query(F.data == "rem:tz")
async def cb_rem_tz(query: CallbackQuery) -> None:
    assert query.message
    await query.message.edit_text("Пояс:", reply_markup=timezone_kb())
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
        await query.answer("Плохой пояс", show_alert=True)
        return
    text, habits, tz_now = await _reminders_text(db, query.from_user.id)
    await query.message.edit_text(text, reply_markup=reminders_panel_kb(habits, tz_now))
    await query.answer(tz)


@router.callback_query(F.data.startswith("rem:on:"))
@router.callback_query(F.data.startswith("rem:off:"))
@router.callback_query(F.data.startswith("rem:needtime:"))
@router.callback_query(F.data.startswith("rem:paused:"))
async def cb_rem_toggle(query: CallbackQuery, db: Database) -> None:
    assert query.from_user and query.data and query.message
    parts = query.data.split(":")
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
        await query.answer("Сначала время в ✏️", show_alert=True)
        return
    if action == "paused":
        await query.answer("Сними паузу в ✏️", show_alert=True)
        return
    try:
        habit = await db.set_habit_remind(
            query.from_user.id, habit_id, enabled=(action == "on")
        )
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    if not habit:
        await query.answer("Нет", show_alert=True)
        return
    text, habits, tz = await _reminders_text(db, query.from_user.id)
    await query.message.edit_text(text, reply_markup=reminders_panel_kb(habits, tz))
    await query.answer("🔔" if action == "on" else "🔕")


# ----- lists -----


@router.message(Command("habits"))
@router.message(F.text == BTN_HABITS)
async def cmd_habits(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer("Пусто.", reply_markup=main_menu())
        return
    lines = [f"• {format_habit_line(h)}" for h in habits]
    await message.answer("\n".join(lines), reply_markup=main_menu())


@router.message(Command("today"))
@router.message(F.text == BTN_TODAY)
async def cmd_today(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    rows = await db.today_status(message.from_user.id)
    if not rows:
        await message.answer("На сегодня пусто.", reply_markup=main_menu())
        return
    lines = []
    for row in rows:
        mark = "✅" if row["done"] else "⬜"
        lines.append(f"{mark} {format_habit_line(row, short=True)} · {row['streak']}")
    done = sum(1 for r in rows if r["done"])
    await message.answer(
        f"Сегодня {done}/{len(rows)}\n" + "\n".join(lines),
        reply_markup=main_menu(),
    )


@router.message(Command("stats"))
@router.message(F.text == BTN_STATS)
async def cmd_stats(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    await state.clear()
    rows = await db.stats(message.from_user.id)
    if not rows:
        await message.answer("Пусто.", reply_markup=main_menu())
        return
    lines = []
    for r in rows:
        pause = " ⏸" if r.get("paused") else ""
        lines.append(
            f"• {r['name']}{pause}: стрик {r['streak']} · нед {r['week']} · всего {r['total']}"
        )
    await message.answer("\n".join(lines), reply_markup=main_menu())
