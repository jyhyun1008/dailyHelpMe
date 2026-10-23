from appearance import color as themed_color, current, foreground, style as themed_style
"""A roomy, rounded context menu matching the drawer's pink palette."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QMenu


class RoundedMenu(QMenu):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(210)
        self.base_style = """
            QMenu {
                font-family: 'ThinMulmaru'; font-size: 14px;
                background: transparent; border: none; padding: 9px 5px;
            }
            QMenu::item {
                color: #775366; background: transparent;
                padding: 11px 20px 11px 12px; margin: 3px 5px;
                border-radius: 10px;
            }
            QMenu::item:selected { color: #79405d; background: #f4d8e6; }
            QMenu::item:disabled { color: #bda2b0; }
            QMenu::indicator { width: 15px; height: 15px; margin-right: 8px; }
            QMenu::separator { height: 1px; background: #efd3e0; margin: 6px 16px; }
        """
        self.setStyleSheet(themed_style(self.base_style))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(themed_color("#fff0f6"))
        painter.setPen(QPen(themed_color("#edcfdd"), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 17, 17)
        painter.end()
        super().paintEvent(event)
