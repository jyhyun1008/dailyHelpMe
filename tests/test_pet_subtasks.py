"""Small manual steps must never implicitly complete or reopen their parent."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/python'))
from store import Store, KST


class SubtaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'db.sqlite3'
        self.store = Store(self.path)
        self.store.apply_reply({'reply': 'saved', 'operations': [
            {'action': 'add', 'kind': 'todo', 'title': 'First task', 'at': '2026-10-24T23:59:00+09:00'},
            {'action': 'add', 'kind': 'routine', 'title': 'Daily work', 'days': list(range(7)), 'time': '09:00'}]})
        self.parent = next(i for i in self.store.items() if i['kind'] == 'todo')
        self.routine = next(i for i in self.store.items() if i['kind'] == 'routine')

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def test_edit_order_restart_and_manual_parent_completion(self):
        parent = self.parent['id']
        first = self.store.change_subtask(parent, 'add', title='Turn on computer')[0]
        second = self.store.change_subtask(parent, 'add', title='Open document')[1]
        self.store.change_subtask(parent, 'update', first['id'], title='Turn on laptop')
        self.store.change_subtask(parent, 'move', second['id'], direction=-1)
        self.assertEqual([s['title'] for s in self.store.subtasks(parent)], ['Open document', 'Turn on laptop'])
        for item in self.store.subtasks(parent):
            self.store.change_subtask(parent, 'toggle', item['id'])
        self.assertEqual({k:v for k,v in next(i for i in self.store.items() if i['id'] == parent).items() if not k.startswith('subtask_')}, {k:v for k,v in self.parent.items() if not k.startswith('subtask_')})
        self.assertNotIn('Turn on laptop', json.dumps(self.store.context()))
        self.store.toggle_completed(parent)
        self.store.change_subtask(parent, 'toggle', first['id'])
        self.assertTrue(next(i for i in self.store.items() if i['id'] == parent)['done'])
        self.store.db.close()
        self.store = Store(self.path)
        self.assertEqual([s['done'] for s in self.store.subtasks(parent)], [1, 0])
        self.store.change_subtask(parent, 'delete', second['id'])
        self.assertEqual(len(self.store.subtasks(parent)), 1)

    def test_validation_scope_and_parent_deletion_cascade(self):
        parent = self.parent['id']
        child = self.store.change_subtask(parent, 'add', title='small step')[0]
        for action in ('update', 'toggle', 'delete', 'move'):
            with self.assertRaises(ValueError):
                self.store.change_subtask(self.routine['id'], action, child['id'], title='changed', direction=-1)
        for title in ('', ' ', 'x'*501, None):
            with self.assertRaises(ValueError):
                self.store.change_subtask(parent, 'add', title=title)
        self.store.apply_reply({'reply':'deleted', 'operations':[{'action':'delete','kind':'todo','id':parent}]})
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM subtasks').fetchone()[0], 0)

    def test_routine_steps_reset_at_five_without_completing_parent(self):
        parent = self.routine['id']
        now = datetime(2026, 10, 24, 4, 59, tzinfo=KST)
        child = self.store.change_subtask(parent, 'add', title='Start small', now=now)[0]
        self.store.change_subtask(parent, 'toggle', child['id'], now=now)
        self.assertTrue(self.store.subtasks(parent, now)[0]['done'])
        self.assertFalse(self.store.subtasks(parent, now+timedelta(minutes=1))[0]['done'])
        self.assertEqual({k:v for k,v in next(i for i in self.store.items() if i['id'] == parent).items() if not k.startswith('subtask_')}, {k:v for k,v in self.routine.items() if not k.startswith('subtask_')})
        self.store.delete(parent)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM subtasks').fetchone()[0], 0)
