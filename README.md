# Habit Tracker Telegram Bot

Минимальный Telegram-бот для привычек: добавить, отметить, стрики, статистика.

UI на русском, основное управление кнопками + пошаговый мастер добавления.

Portfolio project for bot / QA / support roles.

## Features

- Русское меню-кнопки (не нужно помнить команды)
- ➕ **Добавить** — wizard: название → время → заметка
- ✔️ **Отметить** / 🗑 **Удалить** — inline-список привычек
- ✅ Сегодня, 📊 Статистика, 📋 Привычки
- Поля: `schedule_time`, `note`
- SQLite (`aiosqlite`), стрики, архив вместо hard-delete
- Unit-тесты DB

## Stack

- Python 3.12
- [aiogram 3](https://docs.aiogram.dev/) + FSM (`MemoryStorage`)
- SQLite via `aiosqlite`
- `python-dotenv`

## Quick start (local)

### 1. Token

1. Telegram → [@BotFather](https://t.me/BotFather)
2. `/newbot` → copy token

### 2. Install

```bash
git clone https://github.com/mikhov6-cloud/habit-tracker-bot.git
cd habit-tracker-bot
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`:

```env
BOT_TOKEN=123456:ABC-DEF_your_token
```

### 3. Run

```bash
python -m bot.main
```

В Telegram: `/start` → кнопки внизу.

### 4. Tests

```bash
python -m unittest discover -s tests -v
```

## How to use (in bot)

1. **➕ Добавить**
   - шаг 1: название (`Зал`)
   - шаг 2: время кнопкой `18:00` или `ЧЧ:ММ` / ⏭ Пропустить
   - шаг 3: заметка / ⏭ Пропустить
2. **✔️ Отметить** → нажать привычку в списке
3. **✅ Сегодня** / **📊 Статистика** / **📋 Привычки**
4. **🗑 Удалить** → выбрать из списка
5. **❌ Отмена** — выйти из мастера

Команды `/add` `/done` `/habits` `/today` `/stats` `/delete` тоже работают.

## Deploy on Railway

Repo includes `Dockerfile` + `railway.toml`.

1. [railway.app](https://railway.app) → Deploy from GitHub → `habit-tracker-bot`
2. Variables: `BOT_TOKEN` (required), optional `DATABASE_PATH=/app/data/habits.db`
3. Builder: Dockerfile
4. Logs: `Habit tracker bot started`
5. Telegram: `/start`

**One bot token = one running instance** (иначе `TelegramConflictError`).

### Persistence

SQLite is inside the container. For real use: Railway Volume on `/app/data` + `DATABASE_PATH=/app/data/habits.db`.

## Project layout

```text
habit-tracker-bot/
├── bot/
│   ├── main.py
│   ├── handlers.py   # RU UI + FSM wizard + callbacks
│   ├── db.py
│   └── keyboards.py
├── tests/
│   └── test_db.py
├── Dockerfile
├── railway.toml
└── requirements.txt
```

## Design notes

- UTC day boundary for check-ins (MSK day flips at 03:00)
- Archive instead of hard delete
- Unique (user, habit name)
- Streak from today or yesterday

## Next steps

- Daily reminders by `schedule_time`
- Postgres / volume-backed SQLite
- EN/UA language switch

## License

MIT
