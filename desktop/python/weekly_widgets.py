from appearance import color as themed_color, current, foreground, style as themed_style
"""Scrollable weekly time grid; dates and repetitions match the original web."""
from PySide6.QtCore import QDate, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea, QToolTip
from calendar_data import week_data
from store import now_kst
from ui_widgets import font, COLORS


class WeekCanvas(QWidget):
    selected = Signal(QDate)
    def __init__(self):
        super().__init__()
        self.setFixedSize(358, 1220)
        self.data = None
        self.hits = []
        self.untimed_height = 0
        self.setMouseTracking(True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(font(11))
        p.fillRect(self.rect(), themed_color('#fffafd'))
        self.hits = []
        if not self.data:
            return
        offset = self.untimed_height
        if offset:
            p.setPen(themed_color('#a18b97'))
            p.drawText(QRectF(0, 5, 32, offset-5), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, '시간\n미지정')
            for column, day in enumerate(self.data['days']):
                x = 36 + column * 46
                p.setPen(themed_color('#f0e1e9'))
                p.drawLine(x, 0, x, offset)
                untimed = [item for item in day['events'] if not item['event_time']]
                for index, item in enumerate(untimed):
                    box = QRectF(x+2, 4+index*23, 42, 21)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(themed_color('#fae8f1'))
                    p.drawRoundedRect(box, 5, 5)
                    p.setPen(themed_color(COLORS[item['kind']]))
                    p.drawText(box.adjusted(3, 1, -2, 0), Qt.AlignmentFlag.AlignVCenter, p.fontMetrics().elidedText(item['title'], Qt.TextElideMode.ElideRight, 37))
                    self.hits.append((box, day['date'], f"시간 미지정 · {item['title']}"))
        for hour in range(25):
            y = offset + 10 + hour * 50
            p.setPen(themed_color('#f0e1e9'))
            p.drawLine(36, y, 358, y)
            if hour < 24:
                p.setPen(themed_color('#a18b97'))
                p.drawText(QRectF(0, y, 32, 18), Qt.AlignmentFlag.AlignRight, f'{hour:02}:00')
        for column, day in enumerate(self.data['days']):
            x = 36 + column * 46
            p.setPen(themed_color('#f0e1e9'))
            p.drawLine(x, offset + 10, x, offset + 1210)
            groups = {}
            for item in day['events']:
                if item['event_time']:
                    groups.setdefault(item['event_time'], []).append(item)
            for time, items in groups.items():
                hour, minute = map(int, time.split(':'))
                y = offset + 10 + (hour + minute / 60) * 50
                width = 42 / len(items)
                for index, item in enumerate(items):
                    box = QRectF(x + 3 + width * index, y + 2, width - 2, 31)
                    color = themed_color(COLORS[item['kind']])
                    p.setPen(color)
                    p.drawLine(box.topLeft(), box.topRight())
                    p.drawText(box.adjusted(2, 3, -2, 0), Qt.AlignmentFlag.AlignTop, p.fontMetrics().elidedText(item['title'], Qt.TextElideMode.ElideRight, int(box.width()-4)))
                    self.hits.append((box, day['date'], f"{time} · {item['title']}"))
        now = now_kst()
        key = now.date().isoformat()
        for column, day in enumerate(self.data['days']):
            if day['date'] == key:
                y = offset + 10 + (now.hour + now.minute / 60) * 50
                p.setPen(themed_color('#d64289'))
                p.drawLine(36 + column*46, int(y), 82 + column*46, int(y))

    def mousePressEvent(self, event):
        column = int((event.position().x()-36)//46)
        if self.data and 0 <= column < 7:
            self.selected.emit(QDate.fromString(self.data['days'][column]['date'], 'yyyy-MM-dd'))

    def mouseMoveEvent(self, event):
        for box, day, text in self.hits:
            if box.contains(event.position()):
                QToolTip.showText(event.globalPosition().toPoint(), f'{day}\n{text}', self)
                return
        QToolTip.hideText()


class WeeklyTimetable(QWidget):
    selected = Signal(QDate)
    def __init__(self):
        super().__init__()
        self.items = []
        self.day = QDate.currentDate()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.heading = QLabel()
        row.addWidget(self.heading, 1)
        for text, action in [('‹', lambda: self.selected.emit(self.day.addDays(-7))), ('오늘', lambda: self.selected.emit(QDate.fromString(now_kst().date().isoformat(), 'yyyy-MM-dd'))), ('›', lambda: self.selected.emit(self.day.addDays(7)))]:
            b = QPushButton(text)
            b.clicked.connect(action)
            row.addWidget(b)
        layout.addLayout(row)
        self.header_scroll = QScrollArea()
        self.header_scroll.setFixedHeight(54)
        self.header_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.header_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.header = QWidget()
        self.header.setFixedSize(358, 50)
        self.headers = QHBoxLayout(self.header)
        self.headers.setContentsMargins(36, 0, 0, 0)
        self.headers.setSpacing(0)
        self.header_scroll.setWidget(self.header)
        layout.addWidget(self.header_scroll)
        self.scroll = QScrollArea()
        self.canvas = WeekCanvas()
        self.canvas.selected.connect(self.selected)
        self.scroll.setWidget(self.canvas)
        self.scroll.horizontalScrollBar().valueChanged.connect(self.header_scroll.horizontalScrollBar().setValue)
        layout.addWidget(self.scroll, 1)
        self.scroll.verticalScrollBar().setValue(max(0, (now_kst().hour - 3)*50))
        self.setMinimumHeight(320)
        self.setMaximumHeight(350)

    def set_data(self, day, items):
        self.day, self.items = day, items
        data = week_data(items, day.toString('yyyy-MM-dd'))
        self.heading.setText(f"{data['start'][5:].replace('-', '.')} – {data['end'][5:].replace('-', '.')}")
        while self.headers.count():
            self.headers.takeAt(0).widget().deleteLater()
        for i, entry in enumerate(data['days']):
            text = f"{'일월화수목금토'[i]}\n{int(entry['date'][-2:])}"
            b = QPushButton(text)
            b.setFixedSize(46, 48)
            b.setStyleSheet(themed_style("QPushButton { padding: 3px 1px; border-radius: 10px; font-size: 11px; } QPushButton:checked { background: #fae0ed; color: #b65d88; }"))
            b.setToolTip(entry['date'])
            b.setCheckable(True)
            b.setChecked(entry['date'] == day.toString('yyyy-MM-dd'))
            b.clicked.connect(lambda checked=False, key=entry['date']: self.selected.emit(QDate.fromString(key, 'yyyy-MM-dd')))
            self.headers.addWidget(b)
        self.canvas.data = data
        count = max(sum(not item['event_time'] for item in entry['events']) for entry in data['days'])
        self.canvas.untimed_height = max(46, count * 23 + 8)
        self.canvas.setFixedHeight(1220 + self.canvas.untimed_height)
        self.canvas.update()
