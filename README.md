# Habit Tracker Telegram Bot

Telegram-бот привычек: кнопки, дни недели, напоминания, правка, пауза.

## Умеет

- Меню в два уровня: **Сегодня / Отметить / Напоминания** — на виду; **Привычки** (➕ добавить, 📋 список, ✏️ править, 🗑 удалить, 📊 статистика, 📤 экспорт) — за одной кнопкой, чтобы не мешать
- ➕ wizard: имя → **дни** → время → заметка
- дни: каждый / будни / выходные / свои (Пн–Вс)
- ✔️ отметить + ↩ отменить отметку
- ✏️ править: дни, время, заметка, имя, 🔔, ⏸ пауза
- 🔔 напоминания только в нужные дни + локальный пояс
- ✅ сегодня — только привычки на этот день (без паузы)
- стрик считается **только по своим дням** (зал Пн/Ср/Пт не ломается во вторник)
- стата: стрик · рекорд · за неделю · всего
- 📤 `/export` — CSV со всеми отметками (бэкап / свой анализ)
- `/cancel` — выйти из любого шага, даже если клавиатура не видна

## Стек

Python 3.12 · aiogram 3 · SQLite · asyncio reminder loop

## Локально

```bash
git clone https://github.com/mikhov6-cloud/habit-tracker-bot.git
cd habit-tracker-bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # BOT_TOKEN=...
python -m bot.main
python -m unittest discover -s tests -v
```

## Railway

`Dockerfile` + `railway.toml`  
Vars: `BOT_TOKEN`, optional `DATABASE_PATH=/app/data/habits.db` + volume `/app/data`  
Один токен = один инстанс.

## Пример: зал 3 раза в неделю

1. ➕ Добавить → `Зал`
2. дни → **Выбрать дни** → Пн Ср Пт → Готово
3. время `18:00` → заметка `ноги/груд/спина`
4. 🔔 придёт только в эти дни

## License

MIT
