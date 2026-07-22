import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.db import DEFAULT_TZ, Database, format_habit_line, local_hhmm, local_today


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
        self.assertEqual(habit["remind"], 1)
        habits = await self.db.list_habits(1)
        self.assertEqual([h["name"] for h in habits], ["gym"])
        self.assertIn("18:00", format_habit_line(habit))

    async def test_duplicate_habit(self) -> None:
        await self.db.add_habit(1, "gym")
        again = await self.db.add_habit(1, "gym")
        self.assertIsNone(again)

    async def test_checkin_and_streak(self) -> None:
        await self.db.add_habit(1, "read")
        day = local_today(DEFAULT_TZ)
        d = datetime.fromisoformat(day).date()
        yesterday = (d - timedelta(days=1)).isoformat()

        r1 = await self.db.checkin(1, "read", yesterday)
        self.assertTrue(r1["created"])
        r2 = await self.db.checkin(1, "read", day)
        self.assertTrue(r2["created"])
        self.assertEqual(r2["streak"], 2)
        self.assertEqual(r2["total"], 2)

        r3 = await self.db.checkin(1, "read", day)
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

    async def test_timezone_and_remind_toggle(self) -> None:
        await self.db.set_timezone(1, "Europe/Kyiv")
        self.assertEqual(await self.db.get_timezone(1), "Europe/Kyiv")
        habit = await self.db.add_habit(1, "run", schedule_time="07:00")
        assert habit is not None
        self.assertEqual(habit["remind"], 1)
        off = await self.db.set_habit_remind(1, habit["id"], False)
        assert off is not None
        self.assertEqual(off["remind"], 0)
        on = await self.db.set_habit_remind(1, habit["id"], True)
        assert on is not None
        self.assertEqual(on["remind"], 1)

    async def test_due_reminder_once(self) -> None:
        now = local_hhmm(DEFAULT_TZ)
        habit = await self.db.add_habit(1, "nowhabit", schedule_time=now, note="test")
        assert habit is not None
        due = await self.db.list_due_reminders()
        ids = [d["habit_id"] for d in due]
        self.assertIn(habit["id"], ids)

        day = local_today(DEFAULT_TZ)
        await self.db.mark_reminder_sent(habit["id"], day)
        due2 = await self.db.list_due_reminders()
        ids2 = [d["habit_id"] for d in due2]
        self.assertNotIn(habit["id"], ids2)

    async def test_no_reminder_after_checkin(self) -> None:
        now = local_hhmm(DEFAULT_TZ)
        habit = await self.db.add_habit(1, "donehabit", schedule_time=now)
        assert habit is not None
        await self.db.checkin_by_id(1, habit["id"])
        due = await self.db.list_due_reminders()
        ids = [d["habit_id"] for d in due]
        self.assertNotIn(habit["id"], ids)


if __name__ == "__main__":
    unittest.main()
