"""Transparent Bongo Cat frames and keyboard prop drawn as application UI."""
from pathlib import Path
import sys
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from appearance import color as themed_color

ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])) / 'desktop/python/assets/bongocat'


def load_frames():
    return [QPixmap(str(ASSETS / name)) for name in ('idle.png', 'typing-left.png', 'typing-right.png')]


def draw_bongo(painter, rect, frames, frame=0):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.translate(rect.x(), rect.y())
    painter.scale(rect.width()/250, rect.height()/150)
    # All three source frames share the cat/desk alignment. Keep the original alpha.
    painter.setPen(QPen(QColor('#403b40'), 2))
    painter.setBrush(themed_color('#efdfe7'))
    painter.drawRoundedRect(QRectF(25, 102, 204, 46), 6, 6)
    painter.setBrush(themed_color('#fffafd'))
    painter.drawRoundedRect(QRectF(25, 99, 204, 45), 6, 6)
    for row, count in enumerate((12, 12, 11)):
        for column in range(count):
            painter.setPen(QPen(QColor('#b9afb5'), .6))
            pressed = frame == 1 and column < 5 or frame == 2 and column >= 6
            painter.setBrush(themed_color('#f3d4e4') if pressed and row == 1 else QColor('#ffffff'))
            painter.drawRoundedRect(QRectF(31+column*16, 104+row*10, 13, 7), 1.5, 1.5)
    painter.setBrush(themed_color('#f8edf3'))
    painter.drawRoundedRect(QRectF(86, 134, 86, 6), 1.5, 1.5)
    painter.drawPixmap(QRectF(0, 0, 250, 150), frames[frame], QRectF(frames[frame].rect()))
    painter.restore()


def preview(frames):
    pixmap = QPixmap(500, 300)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    draw_bongo(painter, QRectF(0, 0, 500, 300), frames)
    painter.end()
    return pixmap
