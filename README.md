# Habit Tracker Telegram Bot

Минимальный Telegram-бот для привычек: добавить, отметить, стрики, статистика, **напоминания**.

UI на русском, управление кнопками + пошаговый мастер.

Portfolio project for bot / QA / support roles.

## Features

- Русское меню-кнопки
- ➕ **Добавить** — wizard: название → время → заметка
- ✔️ **Отметить** / 🗑 **Удалить** — inline-список
- 🔔 **Напоминания**
  - часовой пояс (по умолчанию `Europe/Moscow`)
  - вкл/выкл по каждой привычке
  - пуш в локальное время привычки + кнопка «Сделано»
  - не дублирует, если уже отмечено сегодня
- ✅ Сегодня, 📊 Статистика, 📋 Привычки
- SQLite + unit-тесты

## Stack

- Python 3.12
- aiogram 3 + FSM
- background reminder loop (`asyncio`, every 30s)
- SQLite / aiosqlite
- zoneinfo for timezones

## Quick start (local)

```bash
git clone https://github.com/mikhov6-cloud/habit-tracker-bot.git
cd habit-tracker-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # BOT_TOKEN=...
python -m bot.main
```

Tests:

```bash
python -m unittest discover -s tests -v
```

## How reminders work

1. Добавь привычку с временем (например `18:00`) → 🔔 включается сам.
2. Кнопка **🔔 Напоминания**:
   - смени пояс (Москва / Киев / …)
   - тап по привычке = вкл/выкл
3. В нужную минуту бот пишет:

```text
🔔 Напоминание
Зал · 🔔 18:00 · (ноги)

Пора отметить привычку — жми «Сделано».
[ ✅ Сделано ]
```

4. Один раз в день на привычку. Если уже `/done` — молчит.

Check-ins и «сегодня» считаются в **локальном поясе пользователя** (не UTC).

## Deploy (Railway)

1. Deploy from GitHub `habit-tracker-bot`
2. `BOT_TOKEN=...`
3. optional `DATABASE_PATH=/app/data/habits.db` + volume `/app/data`
4. Logs: `Habit tracker bot started` and `reminder loop started`

One token = one instance.

## Project layout

```text
bot/
  main.py        # polling + reminder task
  handlers.py    # RU UI / FSM / callbacks
  reminders.py   # due checks + send
  db.py
  keyboards.py
```

## License

MIT
