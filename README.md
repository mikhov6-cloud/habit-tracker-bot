# Habit Tracker Telegram Bot

Minimal Telegram bot for daily habits: add habits, check in, track streaks, view stats.

Built as a portfolio project for bot development / QA / support roles.

## Features

- `/add <name>` — create a habit
- `/done <name>` — check in for today (UTC)
- `/habits` — list active habits
- `/today` — today's completion status
- `/stats` — current streak + total check-ins
- `/delete <name>` — archive a habit
- SQLite storage (`aiosqlite`)
- Reply keyboard shortcuts
- Unit tests for core DB logic

## Stack

- Python 3.11+
- [aiogram 3](https://docs.aiogram.dev/)
- SQLite via `aiosqlite`
- `python-dotenv`

## Quick start

### 1. Create a bot token

1. Open Telegram → [@BotFather](https://t.me/BotFather)
2. `/newbot` → choose name and username
3. Copy the token

### 2. Install

```bash
git clone https://github.com/mikhov6-cloud/habit-tracker-bot.git
cd habit-tracker-bot
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Put your token into `.env`:

```env
BOT_TOKEN=123456:ABC-DEF_your_token
```

### 3. Run

```bash
python -m bot.main
```

Open your bot in Telegram → `/start` → `/add gym` → `/done gym`.

### 4. Tests

```bash
python -m unittest discover -s tests -v
```

## Project layout

```text
habit-tracker-bot/
├── bot/
│   ├── main.py        # entrypoint, polling
│   ├── handlers.py    # commands
│   ├── db.py          # SQLite layer
│   └── keyboards.py   # reply keyboard
├── tests/
│   └── test_db.py
├── requirements.txt
├── .env.example
└── README.md
```

## Design notes

- **UTC day boundary** for check-ins (simple, predictable; local TZ can be added later)
- **Archive instead of hard delete** so history is kept
- **Unique (user, habit name)** to avoid duplicates
- Streak counts consecutive days ending today or yesterday

## Possible next steps

- Daily reminder job (`/remind 21:00`)
- Inline buttons for one-tap `/done`
- Export stats to CSV
- Docker + Railway/Fly.io deploy
- Multi-language UI (EN/RU/UA)

## License

MIT
