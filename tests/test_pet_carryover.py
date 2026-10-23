"""Overdue display preserves original dates and excludes completed work/old routines."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/python'))
from calendar_data import today_items


class CarryoverTests(unittest.TestCase):
    def test_year_boundary_preserves_dates_and_never_carries_old_routines(self):
        def item(id, kind='schedule', at='2026-12-31T14:00:00+09:00', done=0, days=None):
            return dict(id=id, kind=kind, at=at, done=done, days=days or [])
        items = [item('old'), item('deadline', 'todo', '2026-12-30T23:59:00+09:00'),
                 item('done', done=1), item('future', at='2027-01-02T09:00:00+09:00'),
                 item('today', at='2027-01-01T10:00:00+09:00'),
                 item('yesterday-routine', 'routine', None, days=[4]),
                 item('today-routine', 'routine', None, days=[5]),
                 item('undated', 'todo', None), item('bucket', 'bucket', None)]
        snapshot = [dict(item) for item in items]
        visible = today_items(items, '2027-01-01')
        self.assertEqual([item['id'] for item in visible], ['old', 'deadline', 'today', 'today-routine'])
        self.assertEqual([item['id'] for item in visible if item.get('carryover')], ['old', 'deadline'])
        self.assertEqual(visible[0]['at'], '2026-12-31T14:00:00+09:00')
        self.assertEqual(items, snapshot)
        items[0]['done'] = 1
        self.assertNotIn('old', [item['id'] for item in today_items(items, '2027-01-01')])
