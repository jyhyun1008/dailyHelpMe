"""Aggregate activity detection never inspects individual key values."""
import os
import sys
import unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/python'))
from PySide6.QtWidgets import QApplication
from keyboard_activity import KeyboardActivity


class Counter:
    value = 100
    def read(self):
        return self.value


class KeyboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_counter_baseline_changes_disable_and_reset(self):
        counter, ticks = Counter(), [1.0]
        activity = KeyboardActivity(counter=counter, clock=lambda:ticks[0])
        taps = []
        activity.tapped.connect(lambda:taps.append(True))
        try:
            activity.poll()
            self.assertEqual(taps, [])
            counter.value += 1
            activity.poll()
            self.assertEqual(len(taps), 1)
            ticks[0] += .1
            activity.poll()
            self.assertEqual(len(taps), 1)
            counter.value += 3
            activity.poll()
            self.assertEqual(len(taps), 2)
            activity.set_enabled(False)
            counter.value += 1
            activity.poll()
            self.assertEqual(len(taps), 2)
            activity.set_enabled(True)
            activity.poll()  # Starting again must not animate historical activity.
            self.assertEqual(len(taps), 2)
        finally:
            activity.close()

    def test_counter_wraparound_and_missing_native_api(self):
        counter, ticks = Counter(), [1.0]
        counter.value = 0xffffffff
        activity = KeyboardActivity(counter=counter, clock=lambda:ticks[0])
        taps = []
        activity.tapped.connect(lambda:taps.append(True))
        try:
            activity.poll()
            counter.value = 0
            activity.poll()
            self.assertEqual(len(taps), 1)
            ticks[0] += .1
            counter.value = None
            activity.poll()
            self.assertEqual(len(taps), 1)
            activity.close()
            counter.value = 5
            activity.poll()
            self.assertEqual(len(taps), 1)
        finally:
            activity.close()
