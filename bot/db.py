from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "habits.db"


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


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
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                schedule_time TEXT,
                note TEXT,
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
            """
        )
        # Soft migrate older DBs created before schedule_time/note existed.
        for col_def in ("schedule_time TEXT", "note TEXT"):
            col = col_def.split()[0]
            try:
                await self._db.execute(f"ALTER TABLE habits ADD COLUMN {col_def}")
            except aiosqlite.OperationalError:
                pass
        await self._db.commit()

    async def upsert_user(self, user_id: int, username: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """
            INSERT INTO users (user_id, username, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
            """,
            (user_id, username, now),
        )
        await self._db.commit()

    async def add_habit(
        self,
        user_id: int,
        name: str,
        schedule_time: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        name = " ".join(name.split()).strip()
        if not name:
            raise ValueError("Название привычки пустое")
        if len(name) > 64:
            raise ValueError("Название слишком длинное (макс. 64)")

        schedule_time = (schedule_time or "").strip() or None
        note = (note or "").strip() or None
        if note and len(note) > 200:
            raise ValueError("Заметка слишком длинная (макс. 200)")

        now = datetime.now(timezone.utc).isoformat()
        try:
            await self._db.execute(
                """
                INSERT INTO habits (user_id, name, schedule_time, note, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (user_id, name, schedule_time, note, now),
            )
            await self._db.commit()
        except aiosqlite.IntegrityError:
            cursor = await self._db.execute(
                """
                UPDATE habits
                SET is_active = 1,
                    schedule_time = COALESCE(?, schedule_time),
                    note = COALESCE(?, note)
                WHERE user_id = ? AND name = ? AND is_active = 0
                """,
                (schedule_time, note, user_id, name),
            )
            await self._db.commit()
            if cursor.rowcount == 0:
                return None

        return await self.get_habit_by_name(user_id, name)

    async def get_habit_by_name(self, user_id: int, name: str) -> dict[str, Any] | None:
        cursor = await self._db.execute(
            """
            SELECT id, user_id, name, schedule_time, note, created_at, is_active
            FROM habits
            WHERE user_id = ? AND name = ?
            """,
            (user_id, name),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_habit_by_id(self, user_id: int, habit_id: int) -> dict[str, Any] | None:
        cursor = await self._db.execute(
            """
            SELECT id, user_id, name, schedule_time, note, created_at, is_active
            FROM habits
            WHERE user_id = ? AND id = ?
            """,
            (user_id, habit_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_habits(self, user_id: int, active_only: bool = True) -> list[dict[str, Any]]:
        sql = """
            SELECT id, user_id, name, schedule_time, note, created_at, is_active
            FROM habits
            WHERE user_id = ?
        """
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY id ASC"
        cursor = await self._db.execute(sql, (user_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def archive_habit(self, user_id: int, name: str) -> bool:
        cursor = await self._db.execute(
            """
            UPDATE habits
            SET is_active = 0
            WHERE user_id = ? AND name = ? AND is_active = 1
            """,
            (user_id, name),
        )
        await self._db.commit()
        return cursor.rowcount > 0

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

    async def checkin(self, user_id: int, name: str, day: str | None = None) -> dict[str, Any]:
        habit = await self.get_habit_by_name(user_id, name)
        if not habit or not habit["is_active"]:
            raise KeyError("Habit not found")
        return await self._checkin_habit(habit, day)

    async def checkin_by_id(
        self, user_id: int, habit_id: int, day: str | None = None
    ) -> dict[str, Any]:
        habit = await self.get_habit_by_id(user_id, habit_id)
        if not habit or not habit["is_active"]:
            raise KeyError("Habit not found")
        return await self._checkin_habit(habit, day)

    async def _checkin_habit(self, habit: dict[str, Any], day: str | None = None) -> dict[str, Any]:
        day = day or _utc_today()
        date.fromisoformat(day)

        now = datetime.now(timezone.utc).isoformat()
        try:
            await self._db.execute(
                """
                INSERT INTO checkins (habit_id, day, created_at)
                VALUES (?, ?, ?)
                """,
                (habit["id"], day, now),
            )
            await self._db.commit()
            created = True
        except aiosqlite.IntegrityError:
            created = False

        streak = await self.current_streak(habit["id"])
        total = await self.total_checkins(habit["id"])
        return {
            "habit": habit,
            "day": day,
            "created": created,
            "streak": streak,
            "total": total,
        }

    async def total_checkins(self, habit_id: int) -> int:
        cursor = await self._db.execute(
            "SELECT COUNT(*) AS c FROM checkins WHERE habit_id = ?",
            (habit_id,),
        )
        row = await cursor.fetchone()
        return int(row["c"])

    async def current_streak(self, habit_id: int) -> int:
        cursor = await self._db.execute(
            """
            SELECT day FROM checkins
            WHERE habit_id = ?
            ORDER BY day DESC
            """,
            (habit_id,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0

        days = {date.fromisoformat(r["day"]) for r in rows}
        today = datetime.now(timezone.utc).date()
        if today in days:
            cursor_day = today
        elif today.fromordinal(today.toordinal() - 1) in days:
            cursor_day = today.fromordinal(today.toordinal() - 1)
        else:
            return 0

        streak = 0
        while cursor_day in days:
            streak += 1
            cursor_day = cursor_day.fromordinal(cursor_day.toordinal() - 1)
        return streak

    async def stats(self, user_id: int) -> list[dict[str, Any]]:
        habits = await self.list_habits(user_id, active_only=True)
        result: list[dict[str, Any]] = []
        for habit in habits:
            result.append(
                {
                    "id": habit["id"],
                    "name": habit["name"],
                    "schedule_time": habit.get("schedule_time"),
                    "note": habit.get("note"),
                    "streak": await self.current_streak(habit["id"]),
                    "total": await self.total_checkins(habit["id"]),
                }
            )
        return result

    async def today_status(self, user_id: int) -> list[dict[str, Any]]:
        today = _utc_today()
        habits = await self.list_habits(user_id, active_only=True)
        result: list[dict[str, Any]] = []
        for habit in habits:
            cursor = await self._db.execute(
                """
                SELECT 1 FROM checkins
                WHERE habit_id = ? AND day = ?
                """,
                (habit["id"], today),
            )
            done = await cursor.fetchone() is not None
            result.append(
                {
                    "id": habit["id"],
                    "name": habit["name"],
                    "schedule_time": habit.get("schedule_time"),
                    "note": habit.get("note"),
                    "done": done,
                    "streak": await self.current_streak(habit["id"]),
                }
            )
        return result


def format_habit_line(habit: dict[str, Any]) -> str:
    parts = [habit["name"]]
    if habit.get("schedule_time"):
        parts.append(f"⏰ {habit['schedule_time']}")
    if habit.get("note"):
        parts.append(f"({habit['note']})")
    return " · ".join(parts)
