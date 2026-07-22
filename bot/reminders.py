from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db import Database, format_habit_line

log = logging.getLogger(__name__)


def reminder_keyboard(habit_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Сделано",
                    callback_data=f"done:{habit_id}",
                )
            ]
        ]
    )


def format_reminder_text(item: dict) -> str:
    line = format_habit_line(
        {
            "name": item["name"],
            "schedule_time": item.get("schedule_time"),
            "note": item.get("note"),
            "remind": 1,
        }
    )
    note = f"\n📝 {item['note']}" if item.get("note") else ""
    return (
        "🔔 Напоминание\n"
        f"{line}{note}\n\n"
        "Пора отметить привычку — жми «Сделано»."
    )


async def send_due_reminders(bot: Bot, db: Database) -> int:
    due = await db.list_due_reminders()
    sent = 0
    for item in due:
        text = format_reminder_text(item)
        try:
            await bot.send_message(
                chat_id=item["user_id"],
                text=text,
                reply_markup=reminder_keyboard(item["habit_id"]),
            )
            await db.mark_reminder_sent(item["habit_id"], item["day"])
            sent += 1
            log.info(
                "reminder sent user=%s habit=%s day=%s",
                item["user_id"],
                item["habit_id"],
                item["day"],
            )
        except TelegramRetryAfter as exc:
            log.warning("rate limited, sleep %s", exc.retry_after)
            await asyncio.sleep(exc.retry_after)
        except TelegramForbiddenError:
            log.warning("user %s blocked the bot", item["user_id"])
            await db.mark_reminder_sent(item["habit_id"], item["day"])
        except Exception:
            log.exception(
                "failed reminder user=%s habit=%s",
                item["user_id"],
                item["habit_id"],
            )
    return sent


async def reminder_loop(bot: Bot, db: Database, interval_sec: float = 30.0) -> None:
    log.info("reminder loop started (every %ss)", interval_sec)
    while True:
        try:
            await send_due_reminders(bot, db)
        except Exception:
            log.exception("reminder tick failed")
        await asyncio.sleep(interval_sec)
