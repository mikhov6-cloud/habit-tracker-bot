from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.db import Database
from bot.handlers import router
from bot.reminders import reminder_loop


async def main() -> None:
    load_dotenv(ROOT / ".env")
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "BOT_TOKEN is missing. Copy .env.example to .env and paste token from @BotFather."
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db_path = os.getenv("DATABASE_PATH", "").strip()
    db = Database(db_path) if db_path else Database()
    await db.connect()

    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())
    dp["db"] = db
    dp.include_router(router)

    remind_task = asyncio.create_task(reminder_loop(bot, db, interval_sec=30.0))
    try:
        logging.info("Habit tracker bot started")
        await dp.start_polling(bot, db=db, drop_pending_updates=True)
    finally:
        remind_task.cancel()
        try:
            await remind_task
        except asyncio.CancelledError:
            pass
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
