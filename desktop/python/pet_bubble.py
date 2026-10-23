"""Content-sized pet balloon; long messages remain selectable and scrollable."""
import math
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QTextOption
from PySide6.QtWidgets import QTextBrowser
from appearance import style


class PetBubble(QTextBrowser):
    def __init__(self, pet):
        super().__init__(pet)
        self.pet = pet
        self._scrolling = False
        self._x_shift = self._y_shift = 0
        self.setReadOnly(True)
        self.setOpenExternalLinks(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.document().setDocumentMargin(0)
        option = self.document().defaultTextOption()
        option.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDefaultTextOption(option)
        self.apply_theme()
        self.setText('클릭해서 말을 걸어주세요')

    def apply_theme(self):
        self._set_style()
        if self.toPlainText():
            self.setText(self.toPlainText())

    def _set_style(self):
        # A visible scrollbar occupies 4px on the right; reserve the same on the left.
        left = (14 if self._scrolling else 10) + self._x_shift
        right = 10 - self._x_shift
        top, bottom = 10 + self._y_shift, 10 - self._y_shift
        self.setStyleSheet(style('QTextBrowser { background: #fff0f5; color: #6b4d5a; border: 1px solid #f6b9d1; border-radius: 18px; padding: 10px; padding-left: '+str(left)+'px; padding-right: '+str(right)+'px; padding-top: '+str(top)+'px; padding-bottom: '+str(bottom)+'px; } QScrollBar:vertical { width: 4px; background: transparent; } QScrollBar::handle:vertical { background: #d796b8; border-radius: 2px; min-height: 16px; } QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }'))

    def text(self):
        return self.toPlainText()

    def setText(self, text):
        self._scrolling = False
        self._x_shift = self._y_shift = 0
        self._set_style()
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDefaultFont(self.font())
        self.setPlainText(text)
        # Measure the new document, not the old viewport width. Measuring before
        # resizing previously counted stale wraps and left blank space below.
        self.document().setTextWidth(-1)
        natural_width = math.ceil(self.document().idealWidth())
        width = min(300, max(44, natural_width + 22))
        self.document().setTextWidth(width - 22)
        height = math.ceil(self.document().size().height()) + 22
        self._scrolling = height > 94
        if self._scrolling:
            self._set_style()
            self.document().setTextWidth(width - 30)
        first_line = self.document().begin().layout().lineAt(0)
        if first_line.isValid():
            # ThinMulmaru has extra line leading below the visible glyphs.
            self._y_shift = min(5, max(0, math.ceil((first_line.height()-first_line.ascent()-first_line.descent())/2)))
        if not self._scrolling and self.document().blockCount() == 1 and self.document().begin().layout().lineCount() == 1:
            ink = QFontMetrics(self.font()).tightBoundingRect(text)
            self._x_shift = min(5, max(-5, math.ceil((natural_width-ink.width())/2-ink.left())))
        self._set_style()
        self.setGeometry((320-width)//2, 102-min(94, height), width, min(94, height))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn if self._scrolling else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().setValue(0)
        if hasattr(self.pet, 'settings'):
            self.pet.update_mask()

    def enterEvent(self, event):
        self.pet.hide_bubble.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.pet.hide_bubble.start(25000)
        super().leaveEvent(event)

    def wheelEvent(self, event):
        self.pet.hide_bubble.stop()
        super().wheelEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and not self.textCursor().hasSelection():
            self.pet.clicked.emit()
