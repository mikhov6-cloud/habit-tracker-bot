import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from bot.db import (
    DEFAULT_TZ,
    Database,
    format_days,
    format_habit_line,
    is_due_weekday,
    local_hhmm,
    local_today,
    local_weekday,
)


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")
        await self.db.connect()
        await self.db.upsert_user(1, "tester")

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp.cleanup()

    async def test_add_with_days(self) -> None:
        habit = await self.db.add_habit(
            1, "зал", schedule_time="18:00", note="ноги", days_mask="024"
        )
        assert habit is not None
        self.assertEqual(habit["schedule_time"], "18:00")
        self.assertEqual(habit["days_mask"], "024")
        self.assertEqual(habit["remind"], 1)
        self.assertEqual(format_days("024"), "Пн Ср Пт")
        self.assertIn("Пн", format_habit_line(habit))

    async def test_duplicate_habit(self) -> None:
        await self.db.add_habit(1, "gym")
        self.assertIsNone(await self.db.add_habit(1, "gym"))

    async def test_checkin_streak_every_day(self) -> None:
        await self.db.add_habit(1, "read")
        day = local_today(DEFAULT_TZ)
        d = datetime.fromisoformat(day).date()
        y = (d - timedelta(days=1)).isoformat()
        r1 = await self.db.checkin(1, "read", y)
        r2 = await self.db.checkin(1, "read", day)
        self.assertTrue(r1["created"])
        self.assertTrue(r2["created"])
        self.assertEqual(r2["streak"], 2)

    async def test_streak_only_scheduled_days(self) -> None:
        # Mon/Wed/Fri only
        habit = await self.db.add_habit(1, "зал", days_mask="024")
        assert habit is not None
        # pick a Friday as anchor
        # find a Friday
        d = datetime.fromisoformat(local_today(DEFAULT_TZ)).date()
        while d.weekday() != 4:
            d -= timedelta(days=1)
        fri = d
        wed = fri - timedelta(days=2)
        mon = fri - timedelta(days=4)
        await self.db.checkin_by_id(1, habit["id"], mon.isoformat())
        await self.db.checkin_by_id(1, habit["id"], wed.isoformat())
        r = await self.db.checkin_by_id(1, habit["id"], fri.isoformat())
        self.assertEqual(r["streak"], 3)

    async def test_today_filters_days_and_paused(self) -> None:
        wd = local_weekday(DEFAULT_TZ)
        other = str((wd + 1) % 7)
        await self.db.add_habit(1, "today_ok", days_mask=str(wd))
        await self.db.add_habit(1, "other_day", days_mask=other)
        paused = await self.db.add_habit(1, "paused_h", days_mask=str(wd))
        assert paused is not None
        await self.db.set_habit_paused(1, paused["id"], True)
        rows = await self.db.today_status(1)
        names = {r["name"] for r in rows}
        self.assertIn("today_ok", names)
        self.assertNotIn("other_day", names)
        self.assertNotIn("paused_h", names)

    async def test_undo_checkin(self) -> None:
        habit = await self.db.add_habit(1, "water")
        assert habit is not None
        await self.db.checkin_by_id(1, habit["id"])
        self.assertTrue(await self.db.undo_checkin_by_id(1, habit["id"]))
        self.assertEqual(await self.db.total_checkins(habit["id"]), 0)

    async def test_update_days_and_time(self) -> None:
        habit = await self.db.add_habit(1, "run", schedule_time="07:00")
        assert habit is not None
        h2 = await self.db.update_habit(
            1, habit["id"], days_mask="56", schedule_time="09:30"
        )
        assert h2 is not None
        self.assertEqual(h2["days_mask"], "56")
        self.assertEqual(h2["schedule_time"], "09:30")

    async def test_due_reminder_respects_weekday(self) -> None:
        now = local_hhmm(DEFAULT_TZ)
        wd = local_weekday(DEFAULT_TZ)
        other = str((wd + 1) % 7)
        ok = await self.db.add_habit(1, "due_ok", schedule_time=now, days_mask=str(wd))
        bad = await self.db.add_habit(1, "due_bad", schedule_time=now, days_mask=other)
        assert ok and bad
        due_ids = {d["habit_id"] for d in await self.db.list_due_reminders()}
        self.assertIn(ok["id"], due_ids)
        self.assertNotIn(bad["id"], due_ids)

    async def test_no_reminder_after_checkin(self) -> None:
        now = local_hhmm(DEFAULT_TZ)
        habit = await self.db.add_habit(1, "donehabit", schedule_time=now)
        assert habit is not None
        await self.db.checkin_by_id(1, habit["id"])
        due_ids = {d["habit_id"] for d in await self.db.list_due_reminders()}
        self.assertNotIn(habit["id"], due_ids)

    async def test_is_due_helper(self) -> None:
        self.assertTrue(is_due_weekday("024", 0))
        self.assertFalse(is_due_weekday("024", 1))
        self.assertTrue(is_due_weekday(None, 3))

    async def test_best_streak_survives_a_broken_run(self) -> None:
        # daily habit: an older 4-day streak, a gap, then a shorter, more
        # recent 2-day streak ending today. best_streak scans from
        # created_at, so backdate creation too -- otherwise there's no
        # "history" before today to find the older run in.
        habit = await self.db.add_habit(1, "read2")
        assert habit is not None
        day = datetime.fromisoformat(local_today(DEFAULT_TZ)).date()
        old_created = f"{(day - timedelta(days=12)).isoformat()}T00:00:00+00:00"
        await self.db._db.execute(
            "UPDATE habits SET created_at = ? WHERE id = ?", (old_created, habit["id"])
        )
        await self.db._db.commit()
        for offset in (9, 8, 7, 6, 1, 0):  # gap at offsets 5..2
            d = (day - timedelta(days=offset)).isoformat()
            await self.db.checkin_by_id(1, habit["id"], d)
        # pass the id, not the stale dict, so created_at is re-read from the db
        best = await self.db.best_streak(habit["id"], day.isoformat())
        current = await self.db.current_streak(habit["id"], day.isoformat())
        self.assertEqual(best, 4)
        self.assertEqual(current, 2)

    async def test_reactivate_preserves_days_mask(self) -> None:
        # regression test: re-adding a deleted habit by name via the /add
        # shortcut (no days_mask passed) used to silently reset it to daily
        habit = await self.db.add_habit(1, "зал2", days_mask="024")
        assert habit is not None
        self.assertTrue(await self.db.archive_habit(1, "зал2"))
        revived = await self.db.add_habit(1, "зал2")  # no days_mask this time
        assert revived is not None
        self.assertEqual(revived["days_mask"], "024")

    async def test_export_rows(self) -> None:
        habit = await self.db.add_habit(1, "export_me")
        assert habit is not None
        await self.db.checkin_by_id(1, habit["id"], local_today(DEFAULT_TZ))
        rows = await self.db.export_rows(1)
        self.assertTrue(any(r["habit"] == "export_me" for r in rows))


if __name__ == "__main__":
    unittest.main()
