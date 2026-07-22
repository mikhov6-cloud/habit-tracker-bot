import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.db import Database, format_habit_line


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")
        await self.db.connect()
        await self.db.upsert_user(1, "tester")

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp.cleanup()

    async def test_add_and_list_habit(self) -> None:
        habit = await self.db.add_habit(1, "gym", schedule_time="18:00", note="ноги")
        assert habit is not None
        self.assertEqual(habit["schedule_time"], "18:00")
        self.assertEqual(habit["note"], "ноги")
        habits = await self.db.list_habits(1)
        self.assertEqual([h["name"] for h in habits], ["gym"])
        self.assertIn("18:00", format_habit_line(habit))

    async def test_duplicate_habit(self) -> None:
        await self.db.add_habit(1, "gym")
        again = await self.db.add_habit(1, "gym")
        self.assertIsNone(again)

    async def test_checkin_and_streak(self) -> None:
        await self.db.add_habit(1, "read")
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)

        r1 = await self.db.checkin(1, "read", yesterday.isoformat())
        self.assertTrue(r1["created"])
        r2 = await self.db.checkin(1, "read", today.isoformat())
        self.assertTrue(r2["created"])
        self.assertEqual(r2["streak"], 2)
        self.assertEqual(r2["total"], 2)

        r3 = await self.db.checkin(1, "read", today.isoformat())
        self.assertFalse(r3["created"])

    async def test_checkin_by_id(self) -> None:
        habit = await self.db.add_habit(1, "water")
        assert habit is not None
        result = await self.db.checkin_by_id(1, habit["id"])
        self.assertTrue(result["created"])
        self.assertEqual(result["total"], 1)

    async def test_archive_habit(self) -> None:
        await self.db.add_habit(1, "water")
        ok = await self.db.archive_habit(1, "water")
        self.assertTrue(ok)
        self.assertEqual(await self.db.list_habits(1), [])

    async def test_archive_by_id(self) -> None:
        habit = await self.db.add_habit(1, "sleep")
        assert habit is not None
        archived = await self.db.archive_habit_by_id(1, habit["id"])
        assert archived is not None
        self.assertEqual(archived["name"], "sleep")
        self.assertEqual(await self.db.list_habits(1), [])


if __name__ == "__main__":
    unittest.main()
