"""Persistence, export privacy, and week boundary recurrence behavior."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/python'))
from calendar_data import week_data
from store import Store


class DiaryWeekTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'diary.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def test_diary_restart_update_export_and_delete(self):
        first = self.store.save_diary('2026-10-24', '토요일', '오늘은 산책 🌷\n좋았어')
        updated = self.store.save_diary('2026-10-24', '산책', '비밀 일기 본문')
        self.assertEqual(first['created_at'], updated['created_at'])
        self.store.save_diary('2026-10-23', '', '어제의 기록')
        self.store.db.close()
        self.store = Store(self.path)
        entries = json.loads(self.store.export_diary())['entries']
        self.assertEqual([e['date'] for e in entries], ['2026-10-23', '2026-10-24'])
        self.assertEqual(entries[-1]['content'], '비밀 일기 본문')
        self.assertIn('## 2026-10-24 · 산책', self.store.export_diary('markdown'))
        self.assertIn('비밀 일기 본문', json.dumps(self.store.context(), ensure_ascii=False))
        self.store.delete_diary('2026-10-24')
        self.assertIsNone(self.store.diary_entry('2026-10-24'))

    def test_diary_context_bounded_and_draft_uses_requested_date(self):
        from datetime import datetime
        from store import KST
        for index in range(1, 20):
            self.store.save_diary(f"2026-10-{index:02}", "제목", "가"*5000)
        entries = self.store.context()["diaries"]
        self.assertLessEqual(len(entries), 14)
        self.assertLessEqual(sum(len(e["content"]) for e in entries), 24000)
        self.assertTrue(entries[0]["truncated"])
        self.store.message("user", "오늘 산책했어", datetime(2026, 10, 24, 12, tzinfo=KST))
        self.store.message("user", "어제 메시지", datetime(2026, 10, 23, 12, tzinfo=KST))
        context = self.store.diary_draft_context("2026-10-24")
        self.assertEqual([m["content"] for m in context["history"]], ["오늘 산책했어"])
        with self.assertRaises(ValueError):
            self.store.diary_draft_context("2026-10-22")

    def test_invalid_date_size_and_format(self):
        for date in ('2026-02-30', '2026-1-01', None, '<script>'):
            with self.assertRaises(ValueError):
                self.store.save_diary(date, '', '')
        with self.assertRaises(ValueError):
            self.store.save_diary('2026-10-24', '', '가'*30001)
        with self.assertRaises(ValueError):
            self.store.export_diary('html')
        self.assertEqual(json.loads(self.store.export_diary())['entries'], [])

    def test_week_spans_year_and_expands_recurring_and_untimed(self):
        items = [dict(id=1, kind='routine', title='루틴', days=[0, 3, 6], time='09:30', at=None),
                 dict(id=2, kind='schedule', title='종일', at='2027-01-01T05:01:00+09:00'),
                 dict(id=3, kind='todo', title='마감', at='2027-01-01T23:59:00+09:00', done=1),
                 dict(id=4, kind='schedule', title='약속', at='2027-01-01T14:20:00+09:00'),
                 dict(id=5, kind='bucket', title='언젠가', at=None)]
        week = week_data(items, '2027-01-01')
        self.assertEqual((week['start'], week['end']), ('2026-12-27', '2027-01-02'))
        self.assertEqual(sum(e['id']==1 for d in week['days'] for e in d['events']), 3)
        friday = week['days'][5]['events']
        self.assertEqual([e['event_time'] for e in friday], [None, None, '14:20'])
        self.assertEqual(sum(e['id']==5 for d in week['days'] for e in d['events']), 0)
