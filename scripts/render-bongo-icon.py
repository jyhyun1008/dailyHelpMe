"""Render the application's default pet composition for its macOS bundle icon."""
import os
import sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'desktop/python'))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtCore import QRectF, Qt
from bongo_pet import draw_bongo, load_frames
app = QApplication([])
icon = QPixmap(1024, 1024)
icon.fill(Qt.GlobalColor.transparent)
painter = QPainter(icon)
draw_bongo(painter, QRectF(30, 200, 964, 578), load_frames())
painter.end()
path = root / 'build/BongoPet.png'
path.parent.mkdir(parents=True, exist_ok=True)
if not icon.save(str(path)):
    raise SystemExit('Could not save the default Bongo Cat icon')
