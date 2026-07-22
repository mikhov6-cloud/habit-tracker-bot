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

- Python 3.12
- [aiogram 3](https://docs.aiogram.dev/)
- SQLite via `aiosqlite`
- `python-dotenv`

## Quick start (local)

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

## Deploy on Railway (phone-friendly, no laptop 24/7)

This repo includes `Dockerfile` + `railway.toml` so Railway builds with Docker instead of the flaky Metal/Railpack path.

1. Open [railway.app](https://railway.app) → login with GitHub
2. **New Project** → **Deploy from GitHub repo** → `habit-tracker-bot`
3. Open the service → **Variables** → add:
   - `BOT_TOKEN` = token from BotFather
   - optional: `DATABASE_PATH` = `/app/data/habits.db`
4. **Settings**:
   - Builder should pick up `Dockerfile` automatically via `railway.toml`
   - If not: set **Builder = Dockerfile**, Dockerfile path = `Dockerfile`
   - Start command (if asked): `python -m bot.main`
5. **Deploy** / **Redeploy**
6. Open **Deployments → Logs**. You want: `Habit tracker bot started`
7. In Telegram: `/start`

### If you see "Infrastructure Error" / Metal builder failed instantly

That error is on Railway's side, not this code. Do this in order:

1. **Redeploy** once (often enough)
2. Service → **Settings** → Builder → force **Dockerfile** (not Railpack/Metal)
3. Disconnect + reconnect the GitHub repo, or create a **new** Railway service from the same repo
4. Fallback hosts if Railway keeps dying:
   - [Render](https://render.com) → Background Worker → start `python -m bot.main` → env `BOT_TOKEN`
   - [Fly.io](https://fly.io) with the included Dockerfile

### Persistence note

SQLite file is inside the container. On free/ephemeral disks a redeploy can wipe habits. For real use later: attach a Railway Volume at `/app/data` and set `DATABASE_PATH=/app/data/habits.db`.

## Project layout

```text
habit-tracker-bot/
├── bot/
│   ├── main.py
│   ├── handlers.py
│   ├── db.py
│   └── keyboards.py
├── tests/
│   └── test_db.py
├── Dockerfile
├── railway.toml
├── Procfile
├── nixpacks.toml
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
- Volume-backed SQLite or Postgres
- Multi-language UI (EN/RU/UA)

## License

MIT
