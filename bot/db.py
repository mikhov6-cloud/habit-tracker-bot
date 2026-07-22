from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import aiosqlite

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "habits.db"
DEFAULT_TZ = "Europe/Moscow"

# Mon=0 ... Sun=6
DAY_CODES = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
DAY_LABELS = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}
ALL_DAYS_MASK = "0123456"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_tz(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or DEFAULT_TZ)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def local_now(tz_name: str | None = DEFAULT_TZ) -> datetime:
    return datetime.now(get_tz(tz_name))


def local_today(tz_name: str | None = DEFAULT_TZ) -> str:
    return local_now(tz_name).date().isoformat()


def local_hhmm(tz_name: str | None = DEFAULT_TZ) -> str:
    return local_now(tz_name).strftime("%H:%M")


def local_weekday(tz_name: str | None = DEFAULT_TZ, day: str | None = None) -> int:
    if day:
        return date.fromisoformat(day).weekday()
    return local_now(tz_name).weekday()


def normalize_days_mask(mask: str | None) -> str:
    if not mask:
        return ALL_DAYS_MASK
    digits = sorted({c for c in mask if c.isdigit() and c in "0123456"})
    return "".join(digits) if digits else ALL_DAYS_MASK


def is_due_weekday(mask: str | None, weekday: int) -> bool:
    return str(weekday) in normalize_days_mask(mask)


def format_days(mask: str | None) -> str:
    m = normalize_days_mask(mask)
    if m == ALL_DAYS_MASK:
        return "каждый день"
    if m == "01234":
        return "будни"
    if m == "56":
        return "выходные"
    return " ".join(DAY_LABELS[int(c)] for c in m)


def format_habit_line(habit: dict[str, Any], *, short: bool = False) -> str:
    parts = [habit["name"]]
    if habit.get("paused"):
        parts.append("⏸")
    if habit.get("schedule_time"):
        icon = "🔔" if habit.get("remind") else "⏰"
        parts.append(f"{icon}{habit['schedule_time']}")
    days = format_days(habit.get("days_mask"))
    if days != "каждый день":
        parts.append(days)
    if not short and habit.get("note"):
        parts.append(f"({habit['note']})")
    return " · ".join(parts)


class Database:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._init_schema()

    async def close(self) -> None:
        await self._db.close()

    async def _init_schema(self) -> None:
        await self._db.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                timezone TEXT NOT NULL DEFAULT '{DEFAULT_TZ}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                schedule_time TEXT,
                note TEXT,
                days_mask TEXT NOT NULL DEFAULT '{ALL_DAYS_MASK}',
                remind INTEGER NOT NULL DEFAULT 0,
                paused INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, name),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS checkins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                habit_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(habit_id, day),
                FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reminder_log (
                habit_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (habit_id, day),
                FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
            );
            """
        )
        for table, col_def in (
            ("users", f"timezone TEXT DEFAULT '{DEFAULT_TZ}'"),
            ("habits", "schedule_time TEXT"),
            ("habits", "note TEXT"),
            ("habits", f"days_mask TEXT DEFAULT '{ALL_DAYS_MASK}'"),
            ("habits", "remind INTEGER NOT NULL DEFAULT 0"),
            ("habits", "paused INTEGER NOT NULL DEFAULT 0"),
        ):
            try:
                await self._db.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except aiosqlite.OperationalError:
                pass
        await self._db.execute(
            f"UPDATE habits SET days_mask = '{ALL_DAYS_MASK}' "
            "WHERE days_mask IS NULL OR days_mask = ''"
        )
        await self._db.commit()

    async def upsert_user(self, user_id: int, username: str | None) -> None:
        await self._db.execute(
            """
            INSERT INTO users (user_id, username, timezone, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
            """,
            (user_id, username, DEFAULT_TZ, _utc_now_iso()),
        )
        await self._db.commit()

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        cur = await self._db.execute(
            "SELECT user_id, username, timezone, created_at FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_timezone(self, user_id: int) -> str:
        user = await self.get_user(user_id)
        return (user or {}).get("timezone") or DEFAULT_TZ

    async def set_timezone(self, user_id: int, tz_name: str) -> str:
        ZoneInfo(tz_name)
        await self._db.execute(
            "UPDATE users SET timezone = ? WHERE user_id = ?",
            (tz_name, user_id),
        )
        await self._db.commit()
        return tz_name

    def _habit_select(self) -> str:
        return (
            "SELECT id, user_id, name, schedule_time, note, days_mask, "
            "remind, paused, created_at, is_active FROM habits"
        )

    async def get_habit_by_name(self, user_id: int, name: str) -> dict[str, Any] | None:
        cur = await self._db.execute(
            self._habit_select() + " WHERE user_id = ? AND name = ?",
            (user_id, name),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_habit_by_id(self, user_id: int, habit_id: int) -> dict[str, Any] | None:
        cur = await self._db.execute(
            self._habit_select() + " WHERE user_id = ? AND id = ?",
            (user_id, habit_id),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_habits(self, user_id: int, active_only: bool = True) -> list[dict[str, Any]]:
        sql = self._habit_select() + " WHERE user_id = ?"
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY paused ASC, id ASC"
        cur = await self._db.execute(sql, (user_id,))
        return [dict(r) for r in await cur.fetchall()]

    async def add_habit(
        self,
        user_id: int,
        name: str,
        schedule_time: str | None = None,
        note: str | None = None,
        days_mask: str | None = None,
        remind: bool | None = None,
    ) -> dict[str, Any] | None:
        name = " ".join(name.split()).strip()
        if not name:
            raise ValueError("Пустое название")
        if len(name) > 64:
            raise ValueError("Макс. 64 символа")

        schedule_time = (schedule_time or "").strip() or None
        note = (note or "").strip() or None
        if note and len(note) > 200:
            raise ValueError("Заметка макс. 200")
        days = normalize_days_mask(days_mask)

        if remind is None:
            remind_flag = 1 if schedule_time else 0
        else:
            remind_flag = 1 if remind and schedule_time else 0

        try:
            await self._db.execute(
                """
                INSERT INTO habits (
                    user_id, name, schedule_time, note, days_mask,
                    remind, paused, created_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, 1)
                """,
                (user_id, name, schedule_time, note, days, remind_flag, _utc_now_iso()),
            )
            await self._db.commit()
        except aiosqlite.IntegrityError:
            cur = await self._db.execute(
                """
                UPDATE habits
                SET is_active = 1,
                    paused = 0,
                    schedule_time = COALESCE(?, schedule_time),
                    note = COALESCE(?, note),
                    days_mask = ?,
                    remind = CASE WHEN ? IS NOT NULL THEN ? ELSE remind END
                WHERE user_id = ? AND name = ? AND is_active = 0
                """,
                (
                    schedule_time,
                    note,
                    days,
                    schedule_time,
                    remind_flag,
                    user_id,
                    name,
                ),
            )
            await self._db.commit()
            if cur.rowcount == 0:
                return None
        return await self.get_habit_by_name(user_id, name)

    async def update_habit(
        self,
        user_id: int,
        habit_id: int,
        *,
        name: str | None = None,
        schedule_time: str | None | object = ...,
        note: str | None | object = ...,
        days_mask: str | None = None,
        remind: bool | None = None,
        paused: bool | None = None,
    ) -> dict[str, Any] | None:
        habit = await self.get_habit_by_id(user_id, habit_id)
        if not habit or not habit["is_active"]:
            return None

        new_name = habit["name"] if name is None else " ".join(name.split()).strip()
        if not new_name:
            raise ValueError("Пустое название")
        if len(new_name) > 64:
            raise ValueError("Макс. 64 символа")

        if schedule_time is ...:
            new_time = habit.get("schedule_time")
        else:
            new_time = (schedule_time or "").strip() or None  # type: ignore[arg-type]

        if note is ...:
            new_note = habit.get("note")
        else:
            new_note = (note or "").strip() or None  # type: ignore[arg-type]
            if new_note and len(new_note) > 200:
                raise ValueError("Заметка макс. 200")

        new_days = (
            normalize_days_mask(days_mask)
            if days_mask is not None
            else normalize_days_mask(habit.get("days_mask"))
        )

        if remind is None:
            new_remind = int(habit.get("remind") or 0)
        else:
            new_remind = 1 if remind else 0
        if not new_time:
            new_remind = 0

        new_paused = int(habit.get("paused") or 0) if paused is None else (1 if paused else 0)

        try:
            await self._db.execute(
                """
                UPDATE habits
                SET name = ?, schedule_time = ?, note = ?, days_mask = ?,
                    remind = ?, paused = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    new_name,
                    new_time,
                    new_note,
                    new_days,
                    new_remind,
                    new_paused,
                    habit_id,
                    user_id,
                ),
            )
            await self._db.commit()
        except aiosqlite.IntegrityError as exc:
            raise ValueError("Такое название уже есть") from exc
        return await self.get_habit_by_id(user_id, habit_id)

    async def set_habit_remind(
        self, user_id: int, habit_id: int, enabled: bool
    ) -> dict[str, Any] | None:
        habit = await self.get_habit_by_id(user_id, habit_id)
        if not habit or not habit["is_active"]:
            return None
        if enabled and not habit.get("schedule_time"):
            raise ValueError("Сначала задай время")
        return await self.update_habit(user_id, habit_id, remind=enabled)

    async def set_habit_paused(
        self, user_id: int, habit_id: int, paused: bool
    ) -> dict[str, Any] | None:
        return await self.update_habit(user_id, habit_id, paused=paused)

    async def archive_habit(self, user_id: int, name: str) -> bool:
        cur = await self._db.execute(
            """
            UPDATE habits SET is_active = 0
            WHERE user_id = ? AND name = ? AND is_active = 1
            """,
            (user_id, name),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def archive_habit_by_id(self, user_id: int, habit_id: int) -> dict[str, Any] | None:
        habit = await self.get_habit_by_id(user_id, habit_id)
        if not habit or not habit["is_active"]:
            return None
        await self._db.execute(
            "UPDATE habits SET is_active = 0 WHERE id = ? AND user_id = ?",
            (habit_id, user_id),
        )
        await self._db.commit()
        return habit

    async def checkin(
        self, user_id: int, name: str, day: str | None = None
    ) -> dict[str, Any]:
        habit = await self.get_habit_by_name(user_id, name)
        if not habit or not habit["is_active"]:
            raise KeyError("Habit not found")
        if day is None:
            day = local_today(await self.get_timezone(user_id))
        return await self._checkin_habit(habit, day)

    async def checkin_by_id(
        self, user_id: int, habit_id: int, day: str | None = None
    ) -> dict[str, Any]:
        habit = await self.get_habit_by_id(user_id, habit_id)
        if not habit or not habit["is_active"]:
            raise KeyError("Habit not found")
        if day is None:
            day = local_today(await self.get_timezone(user_id))
        return await self._checkin_habit(habit, day)

    async def undo_checkin_by_id(
        self, user_id: int, habit_id: int, day: str | None = None
    ) -> bool:
        habit = await self.get_habit_by_id(user_id, habit_id)
        if not habit or not habit["is_active"]:
            return False
        if day is None:
            day = local_today(await self.get_timezone(user_id))
        cur = await self._db.execute(
            "DELETE FROM checkins WHERE habit_id = ? AND day = ?",
            (habit_id, day),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def _checkin_habit(self, habit: dict[str, Any], day: str) -> dict[str, Any]:
        date.fromisoformat(day)
        try:
            await self._db.execute(
                "INSERT INTO checkins (habit_id, day, created_at) VALUES (?, ?, ?)",
                (habit["id"], day, _utc_now_iso()),
            )
            await self._db.commit()
            created = True
        except aiosqlite.IntegrityError:
            created = False
        return {
            "habit": habit,
            "day": day,
            "created": created,
            "streak": await self.current_streak(habit, day),
            "total": await self.total_checkins(habit["id"]),
        }

    async def total_checkins(self, habit_id: int) -> int:
        cur = await self._db.execute(
            "SELECT COUNT(*) AS c FROM checkins WHERE habit_id = ?",
            (habit_id,),
        )
        row = await cur.fetchone()
        return int(row["c"])

    async def week_count(self, habit_id: int, anchor_day: str) -> int:
        d = date.fromisoformat(anchor_day)
        start = d - timedelta(days=d.weekday())
        end = start + timedelta(days=6)
        cur = await self._db.execute(
            """
            SELECT COUNT(*) AS c FROM checkins
            WHERE habit_id = ? AND day >= ? AND day <= ?
            """,
            (habit_id, start.isoformat(), end.isoformat()),
        )
        row = await cur.fetchone()
        return int(row["c"])

    async def current_streak(
        self, habit: dict[str, Any] | int, anchor_day: str | None = None
    ) -> int:
        """Streak counts only scheduled days for this habit."""
        if isinstance(habit, int):
            cur = await self._db.execute(self._habit_select() + " WHERE id = ?", (habit,))
            row = await cur.fetchone()
            if not row:
                return 0
            habit = dict(row)

        habit_id = habit["id"]
        mask = normalize_days_mask(habit.get("days_mask"))
        cur = await self._db.execute(
            "SELECT day FROM checkins WHERE habit_id = ? ORDER BY day DESC",
            (habit_id,),
        )
        days = {date.fromisoformat(r["day"]) for r in await cur.fetchall()}
        if not days:
            return 0

        today = date.fromisoformat(anchor_day) if anchor_day else datetime.now(timezone.utc).date()

        def prev_due(d: date) -> date | None:
            for i in range(1, 8):
                cand = d - timedelta(days=i)
                if str(cand.weekday()) in mask:
                    return cand
            return None

        # Start from today if due+done, else previous due day if done
        if str(today.weekday()) in mask and today in days:
            cursor_day: date | None = today
        else:
            cursor_day = prev_due(today)
            if cursor_day is None or cursor_day not in days:
                return 0

        streak = 0
        while cursor_day is not None and cursor_day in days:
            streak += 1
            cursor_day = prev_due(cursor_day)
        return streak

    async def stats(self, user_id: int) -> list[dict[str, Any]]:
        habits = await self.list_habits(user_id, active_only=True)
        day = local_today(await self.get_timezone(user_id))
        result: list[dict[str, Any]] = []
        for habit in habits:
            result.append(
                {
                    **habit,
                    "streak": await self.current_streak(habit, day),
                    "total": await self.total_checkins(habit["id"]),
                    "week": await self.week_count(habit["id"], day),
                }
            )
        return result

    async def today_status(self, user_id: int) -> list[dict[str, Any]]:
        tz = await self.get_timezone(user_id)
        day = local_today(tz)
        wd = local_weekday(tz, day)
        habits = await self.list_habits(user_id, active_only=True)
        result: list[dict[str, Any]] = []
        for habit in habits:
            if habit.get("paused"):
                continue
            if not is_due_weekday(habit.get("days_mask"), wd):
                continue
            cur = await self._db.execute(
                "SELECT 1 FROM checkins WHERE habit_id = ? AND day = ?",
                (habit["id"], day),
            )
            done = await cur.fetchone() is not None
            result.append(
                {
                    **habit,
                    "done": done,
                    "streak": await self.current_streak(habit, day),
                }
            )
        return result

    async def list_due_reminders(self) -> list[dict[str, Any]]:
        cur = await self._db.execute(
            f"""
            SELECT
                h.id AS habit_id,
                h.user_id AS user_id,
                h.name AS name,
                h.schedule_time AS schedule_time,
                h.note AS note,
                h.days_mask AS days_mask,
                h.remind AS remind,
                COALESCE(u.timezone, '{DEFAULT_TZ}') AS timezone
            FROM habits h
            JOIN users u ON u.user_id = h.user_id
            WHERE h.is_active = 1
              AND h.paused = 0
              AND h.remind = 1
              AND h.schedule_time IS NOT NULL
              AND h.schedule_time != ''
            """
        )
        due: list[dict[str, Any]] = []
        for row in await cur.fetchall():
            item = dict(row)
            tz_name = item["timezone"] or DEFAULT_TZ
            try:
                now_hm = local_hhmm(tz_name)
                day = local_today(tz_name)
                wd = local_weekday(tz_name, day)
            except Exception:
                continue
            if item["schedule_time"] != now_hm:
                continue
            if not is_due_weekday(item.get("days_mask"), wd):
                continue

            c1 = await self._db.execute(
                "SELECT 1 FROM checkins WHERE habit_id = ? AND day = ?",
                (item["habit_id"], day),
            )
            if await c1.fetchone():
                continue
            c2 = await self._db.execute(
                "SELECT 1 FROM reminder_log WHERE habit_id = ? AND day = ?",
                (item["habit_id"], day),
            )
            if await c2.fetchone():
                continue
            item["day"] = day
            due.append(item)
        return due

    async def mark_reminder_sent(self, habit_id: int, day: str) -> None:
        await self._db.execute(
            "INSERT OR IGNORE INTO reminder_log (habit_id, day, sent_at) VALUES (?, ?, ?)",
            (habit_id, day, _utc_now_iso()),
        )
        await self._db.commit()
