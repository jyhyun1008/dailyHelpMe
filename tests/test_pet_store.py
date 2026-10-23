import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop/python"))
from store import KST, Store


def operation(kind="schedule", action="add", **kwargs):
    return dict(kind=kind, action=action, id=kwargs.get("id"), title=kwargs.get("title", "공부"),
                at=kwargs.get("at", "2026-10-22T14:00:00+09:00"),
                days=kwargs.get("days"), time=kwargs.get("time"))


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "doa.sqlite3"
        self.store = Store(self.path)
        self.now = datetime(2026, 10, 22, 14, 0, tzinfo=KST)

    def tearDown(self):
        self.store.db.close()
        self.directory.cleanup()

    def test_creation_links_persist_skip_duplicates_and_survive_deleted_items(self):
        result = {"reply":"등록했어요", "operations":[operation(title="첫 작업"), operation(title="다음 작업")]}
        self.store.apply_reply(result, link_created=True)
        cards = self.store.history()[-1]["created_items"]
        self.assertEqual(len(cards),2)
        self.store.apply_reply(result, link_created=True)
        self.assertEqual(self.store.history()[-1]["created_items"],[])
        self.store.db.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.history()[0]["created_items"],cards)
        self.store.delete(cards[0]["id"])
        self.assertFalse(self.store.history()[0]["created_items"][0]["available"])
        before = len(self.store.history())
        with self.assertRaises(ValueError):
            self.store.apply_reply({"reply":"실패", "operations":[operation(title="취소될 일정"), {"action":"bad","kind":"bad"}]},link_created=True)
        self.assertEqual(len(self.store.history()),before)
        self.assertFalse(any(i["title"]=="취소될 일정" for i in self.store.items()))

    def test_subtask_progress_resets_with_routine_day(self):
        self.store.apply_reply({"reply":"루틴", "operations":[operation(kind="routine",title="루틴",days=list(range(7)),time="09:00")]})
        parent = self.store.items()[0]["id"]
        self.store.change_subtask(parent,"add",title="시작",now=self.now)
        step = self.store.subtasks(parent)[0]["id"]
        self.store.change_subtask(parent,"toggle",subtask_id=step,now=self.now)
        self.assertEqual(self.store.items(now=self.now)[0]["subtask_done"],1)
        self.assertEqual(self.store.items(now=self.now+timedelta(days=1))[0]["subtask_done"],0)
        self.assertEqual(self.store.items(now=self.now)[0]["subtask_total"],1)
        self.assertEqual(self.store.items()[0]["done"],0)

    def apply(self, *operations):
        return self.store.apply_reply({"reply": "기억했어요!", "operations": list(operations)})

    def test_memory_edits_and_profile_append(self):
        self.apply(operation(), operation(kind="profile", title="민트를 좋아함"))
        item = self.store.items()[0]
        self.apply(operation(action="update", id=item["id"], at="2026-10-22T16:00:00+09:00"))
        self.assertIn("16:00", self.store.items()[0]["at"])
        self.apply(operation(kind="profile", title="아침에 졸림"))
        self.assertEqual(self.store.get("profile"), "민트를 좋아함\n아침에 졸림")
        self.apply(operation(action="complete", id=item["id"]))
        self.assertEqual(self.store.items()[0]["done"], 1)
        self.apply(operation(action="delete", id=item["id"]))
        self.assertEqual(self.store.items(), [])

    def test_invalid_batch_rolls_back_memory_and_assistant_message(self):
        with self.assertRaises(ValueError):
            self.apply(operation(kind="profile", title="유효한 메모"), operation(at="2026-10-22T14:00:00"))
        self.assertEqual(self.store.get("profile"), "")
        self.assertEqual(self.store.items(), [])
        self.assertEqual(self.store.history(), [])

    def test_duplicate_prevention_and_exact_id_validation(self):
        self.apply(operation(), operation())
        self.assertEqual(len(self.store.items()), 1)
        with self.assertRaises(ValueError):
            self.apply(operation(action="delete", id="unknown"))
        self.assertEqual(len(self.store.items()), 1)

    def test_reminders_survive_restart_and_edit_reschedules(self):
        self.apply(operation())
        self.assertEqual(len(self.store.reminders(self.now)), 1)
        self.store.db.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.reminders(self.now + timedelta(minutes=1)), [])
        item = self.store.items()[0]
        self.apply(operation(action="update", id=item["id"], at="2026-10-22T16:00:00+09:00"))
        self.assertEqual(self.store.reminders(self.now), [])
        self.assertEqual(len(self.store.reminders(self.now + timedelta(hours=2))), 1)

    def test_deadline_noon_day_before_and_no_expired_ping(self):
        self.apply(operation(kind="todo", at="2026-10-23T23:59:00+09:00"))
        self.assertEqual(self.store.reminders(self.now.replace(hour=11)), [])
        self.assertEqual(len(self.store.reminders(self.now.replace(hour=12))), 1)
        self.apply(operation(kind="todo", title="이미 지난 것", at="2026-10-21T23:59:00+09:00"))
        self.assertEqual(self.store.reminders(self.now), [])

    def test_routine_weekday_catchup_and_five_am_completion(self):
        # Thursday is 4 in the original application's Sunday-first scheme.
        self.apply(operation(kind="routine", at=None, days=[4], time="09:00"))
        self.assertEqual(len(self.store.reminders(self.now)), 1)
        self.assertEqual(self.store.reminders(self.now + timedelta(minutes=15)), [])
        self.assertEqual(self.store.reminders(self.now + timedelta(days=1)), [])
        item = self.store.items()[0]
        self.store.complete(item["id"], self.now.replace(hour=4))
        self.assertEqual(self.store.items()[0]["completed_day"], "2026-10-21")
        self.assertEqual(self.store.items()[0]["done"], 0)
        self.store.complete(item["id"], self.now.replace(hour=5))
        self.assertEqual(self.store.items()[0]["completed_day"], "2026-10-22")

    def test_idle_daily_rate_limit_and_user_reset(self):
        self.store.message("user", "안녕", self.now)
        self.assertEqual(self.store.reminders(self.now + timedelta(hours=23)), [])
        self.assertEqual(len(self.store.reminders(self.now + timedelta(hours=24))), 1)
        self.assertEqual(self.store.reminders(self.now + timedelta(hours=25)), [])
        self.store.message("user", "왔어", self.now + timedelta(hours=26))
        self.assertEqual(self.store.reminders(self.now + timedelta(hours=48)), [])

    def test_confirmation_is_local(self):
        self.store.message("assistant", "안녕하세요", self.now)
        row = self.store.history()[0]
        self.store.confirm(row["id"])
        self.assertEqual(self.store.history()[0]["confirmed"], 1)
        self.store.confirm(row["id"])
        self.assertEqual(self.store.history()[0]["confirmed"], 0)


if __name__ == "__main__":
    unittest.main()
