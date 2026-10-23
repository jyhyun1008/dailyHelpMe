"""Validate bounded balloon sizing, portable appearance and contrast."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/python'))
from appearance import validate, map_color, foreground


class AppearanceTests(unittest.TestCase):
    def test_validation_and_palette(self):
        self.assertEqual(validate('  Luna  ', '#3979AE'), ('Luna', '#3979ae'))
        for name, color in [('', '#123456'), ('a\nb', '#123456'), ('a'*31, '#123456'), ('ok', 'red'), ('ok', '#fff; url(x)')]:
            with self.assertRaises(ValueError):
                validate(name, color)
        self.assertEqual(map_color('#d64289', '#3979ae'), '#3979ae')
        self.assertNotEqual(map_color('#fffafd', '#3979ae'), '#fffafd')
        self.assertEqual(foreground('#ffffff'), '#352431')
        self.assertEqual(foreground('#000000'), '#ffffff')
