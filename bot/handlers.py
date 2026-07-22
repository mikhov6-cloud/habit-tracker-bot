from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from bot.db import Database
from bot.keyboards import main_menu

router = Router()


def _habit_name_from_args(command: CommandObject | None, raw: str = "") -> str:
    if command and command.args:
        return command.args.strip()
    return raw.strip()


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    assert message.from_user
    await db.upsert_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "Habit Tracker bot.\n\n"
        "Commands:\n"
        "/add NAME — create habit\n"
        "/done NAME — check in today\n"
        "/habits — list habits\n"
        "/today — today's progress\n"
        "/stats — streaks and totals\n"
        "/delete NAME — archive habit\n"
        "/help — command list\n\n"
        "Example:\n"
        "/add gym\n"
        "/done gym",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
@router.message(F.text == "❓ Help")
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Commands:\n"
        "/add NAME\n"
        "/done NAME\n"
        "/habits\n"
        "/today\n"
        "/stats\n"
        "/delete NAME\n\n"
        "Names are case-sensitive as you typed them.\n"
        "Check-ins use UTC day boundary."
    )


@router.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject, db: Database) -> None:
    assert message.from_user
    await db.upsert_user(message.from_user.id, message.from_user.username)
    name = _habit_name_from_args(command)
    if not name:
        await message.answer("Usage: /add HABIT_NAME\nExample: /add read 20m")
        return
    try:
        habit = await db.add_habit(message.from_user.id, name)
    except ValueError as exc:
        await message.answer(str(exc))
        return

    if habit is None:
        await message.answer(f"Habit already exists: {name}")
        return
    await message.answer(f"Added: {habit['name']}\nMark done with /done {habit['name']}")


@router.message(Command("done"))
async def cmd_done(message: Message, command: CommandObject, db: Database) -> None:
    assert message.from_user
    name = _habit_name_from_args(command)
    if not name:
        await message.answer("Usage: /done HABIT_NAME\nExample: /done gym")
        return
    try:
        result = await db.checkin(message.from_user.id, name)
    except KeyError:
        await message.answer(f"Habit not found: {name}\nUse /habits")
        return
    except ValueError:
        await message.answer("Invalid date")
        return

    if result["created"]:
        await message.answer(
            f"Checked in: {result['habit']['name']}\n"
            f"Streak: {result['streak']} day(s)\n"
            f"Total: {result['total']}"
        )
    else:
        await message.answer(
            f"Already checked in today: {result['habit']['name']}\n"
            f"Streak: {result['streak']} day(s)\n"
            f"Total: {result['total']}"
        )


@router.message(Command("habits"))
@router.message(F.text == "📋 Habits")
async def cmd_habits(message: Message, db: Database) -> None:
    assert message.from_user
    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer("No habits yet. Add one: /add gym")
        return
    lines = [f"• {h['name']}" for h in habits]
    await message.answer("Your habits:\n" + "\n".join(lines))


@router.message(Command("today"))
@router.message(F.text == "✅ Today")
async def cmd_today(message: Message, db: Database) -> None:
    assert message.from_user
    rows = await db.today_status(message.from_user.id)
    if not rows:
        await message.answer("No habits yet. Add one: /add gym")
        return
    lines = []
    for row in rows:
        mark = "✅" if row["done"] else "⬜"
        lines.append(f"{mark} {row['name']} (streak {row['streak']})")
    done = sum(1 for r in rows if r["done"])
    await message.answer(f"Today ({done}/{len(rows)}):\n" + "\n".join(lines))


@router.message(Command("stats"))
@router.message(F.text == "📊 Stats")
async def cmd_stats(message: Message, db: Database) -> None:
    assert message.from_user
    rows = await db.stats(message.from_user.id)
    if not rows:
        await message.answer("No habits yet. Add one: /add gym")
        return
    lines = [
        f"• {r['name']}: streak {r['streak']}, total {r['total']}"
        for r in rows
    ]
    await message.answer("Stats:\n" + "\n".join(lines))


@router.message(Command("delete"))
async def cmd_delete(message: Message, command: CommandObject, db: Database) -> None:
    assert message.from_user
    name = _habit_name_from_args(command)
    if not name:
        await message.answer("Usage: /delete HABIT_NAME")
        return
    ok = await db.archive_habit(message.from_user.id, name)
    if ok:
        await message.answer(f"Archived: {name}")
    else:
        await message.answer(f"Active habit not found: {name}")
