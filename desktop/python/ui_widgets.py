"""Compact calendar, conversation bubbles and agenda rows painted for the drawer."""
from __future__ import annotations
from appearance import color as themed_color, current, foreground, style as themed_style

from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal, QUrl, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QScrollArea,
    QPushButton, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from store import now_kst
from typography import FONT_FAMILY
from calendar_data import event_time
from message_links import display_text, source_links
from chat_media import TOKEN
from media_rendering import rich_layout, draw_artwork

COLORS = {"schedule": "#c878a0", "todo": "#e0a16d", "routine": "#75b5a5", "bucket": "#b28dc6"}
DATA_ROLE = Qt.ItemDataRole.UserRole + 1
DAYS = "일월화수목금토"


def font(size=13, bold=False):
    result = QFont(FONT_FAMILY)
    result.setPixelSize(size)
    result.setWeight(QFont.Weight.Normal)  # The supplied face is weight 400; avoid synthetic bold.
    return result


def is_done(item, now=None):
    day = ((now or now_kst()) - timedelta(hours=5)).date().isoformat()
    return bool(item["done"] or item["kind"] == "routine" and item["completed_day"] == day)


def item_title(item):
    total = item.get("subtask_total", 0)
    return item["title"] + (f' ({item.get("subtask_done", 0)}/{total})' if total else "")


def item_detail(item):
    if item["kind"] == "routine":
        days = item["days"]
        label = "매일" if len(days) == 7 else "·".join(DAYS[day] for day in days)
        return f'{label}  ·  {item["time"]}'
    if item["at"]:
        at = item["at"]
        only_date = (item["kind"] == "todo" and at[11:16] == "23:59") or (item["kind"] == "schedule" and at[11:16] == "05:01")
        prefix = ("원래 마감 " if item["kind"] == "todo" else "원래 일정 ") if item.get("carryover") else ""
        return prefix + at[:10].replace("-", ".") + ("" if only_date else "  ·  " + at[11:16])
    return "언젠가 하고 싶은 일" if item["kind"] == "bucket" else "날짜 미정"


class MessageDelegate(QStyledItemDelegate):
    def rich(self, width, message):
        owner = self.parent()
        color = foreground() if message["role"] == "user" else "#604653"
        key = (width, message["content"], color)
        if key not in owner.rich_cache:
            if len(owner.rich_cache)>200: owner.rich_cache.clear()
            owner.rich_cache[key] = rich_layout(display_text(message), width, font(14), color, owner.media_assets)
        return owner.rich_cache[key]

    def layout_for(self, width, message):
        metrics = QFontMetrics(font(14))
        max_text_width = max(80, int(width * .78) - 26)
        text = display_text(message)
        bounds = metrics.boundingRect(QRect(0, 0, max_text_width, 100000), Qt.TextFlag.TextWordWrap, text)
        if message.get("sticker"):
            return 146, 146, 32 if message.get("date_label") else 0, 0
        if TOKEN.search(text):
            _, rich_width, rich_height, _ = self.rich(max_text_width,message)
            return int(rich_width)+26, int(rich_height)+20, 32 if message.get("date_label") else 0, 18 if message.get("show_author") else 0
        bubble_width = min(max_text_width + 26, max(46, bounds.width() + 26))
        header = 32 if message.get("date_label") else 0
        author = 18 if message.get("show_author") else 0
        return bubble_width, bounds.height() + 20, header, author

    def sizeHint(self, option, index):
        message = index.data(DATA_ROLE)
        if not message:
            return QSize(0, 0)
        width = self.parent().viewport().width() - 12
        _, height, header, author = self.layout_for(width, message)
        return QSize(width, height + header + author + 24 + len(source_links(message))*22 + len(message.get("created_items", []))*58)

    def paint(self, painter, option, index):
        message = index.data(DATA_ROLE)
        if not message:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = option.rect.adjusted(5, 0, -5, 0)
        width, height, header, author = self.layout_for(area.width(), message)
        outgoing = message["role"] == "user"
        y = area.y()
        if header:
            painter.setFont(font(11))
            painter.setPen(themed_color("#aa94a1"))
            painter.drawText(QRect(area.x(), y, area.width(), 26), Qt.AlignmentFlag.AlignCenter, message["date_label"])
            y += header
        x = area.right() - width if outgoing else area.left()
        if author:
            painter.setFont(font(11))
            painter.setPen(themed_color("#a08897"))
            painter.drawText(QRect(x + 3, y, width, 16), Qt.AlignmentFlag.AlignLeft, current()["name"])
            y += author
        bubble = QRectF(x, y, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(themed_color("#d64289" if outgoing else "#f8ecf2"))
        if not message.get("sticker"):
            painter.drawRoundedRect(bubble, 17, 17)
        painter.setFont(font(14))
        painter.setPen(themed_color(foreground() if outgoing else "#604653"))
        if message.get("sticker"):
            asset_id = message["sticker"]["id"]
            rect = bubble.adjusted(10,10,-10,-10)
            owner = self.parent()
            owner.media_hits.append((rect, (message["id"], "sticker"), message["sticker"]["name"]))
            draw_artwork(painter,rect,owner.media_pixmaps.get(asset_id,QPixmap()),owner.media_scales.get((message["id"],"sticker"),1.0))
        elif TOKEN.search(display_text(message)):
            doc, _, _, boxes = self.rich(max(80,int(area.width()*.78)-26),message)
            painter.save();painter.translate(x+13,y+10);doc.drawContents(painter);painter.restore()
            owner = self.parent()
            for local, asset_id, name, occurrence in boxes:
                rect = local.translated(x+13,y+10)
                key = (message["id"],occurrence)
                owner.media_hits.append((rect,key,name))
                draw_artwork(painter,rect,owner.media_pixmaps.get(asset_id,QPixmap()),owner.media_scales.get(key,1.0))
        else:
            painter.drawText(bubble.adjusted(13, 10, -13, -10), Qt.TextFlag.TextWordWrap, display_text(message))
        timestamp = message["created_at"][11:16]
        if message.get("confirmed"):
            timestamp += "  · 확인"
        if message.get("bookmarked"):
            timestamp += "  · ★"
        painter.setFont(font(10))
        painter.setPen(themed_color("#aa94a1"))
        painter.drawText(QRectF(x + 3, y + height + 3, width - 6, 16),
                         Qt.AlignmentFlag.AlignRight if outgoing else Qt.AlignmentFlag.AlignLeft, timestamp)
        painter.setFont(font(12))
        painter.setPen(themed_color("#b65d88"))
        for offset, (title, url) in enumerate(source_links(message)):
            caption = painter.fontMetrics().elidedText("↗ " + title, Qt.TextElideMode.ElideRight, max(30, width-6))
            painter.drawText(QRectF(x+3, y+height+23+offset*22, width-6, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, caption)
        card_y = y+height+24+len(source_links(message))*22
        for offset, item in enumerate(message.get("created_items", [])):
            card = QRectF(area.left(), card_y+offset*58, max(80, area.width()-24), 50)
            painter.setPen(QPen(themed_color("#ecd6e1"), 1))
            painter.setBrush(themed_color("#fff5fa"))
            painter.drawRoundedRect(card, 12, 12)
            painter.setPen(themed_color("#a5748d"))
            painter.setFont(font(11))
            painter.drawText(card.adjusted(12, 5, -12, -25), Qt.AlignmentFlag.AlignLeft, "일정이 생성됐어요 · 상세 보기 ›" if item["available"] else "삭제된 일정")
            painter.setPen(themed_color("#604653"))
            painter.setFont(font(13))
            painter.drawText(card.adjusted(12, 25, -12, -5), Qt.AlignmentFlag.AlignLeft, painter.fontMetrics().elidedText(item["title"], Qt.TextElideMode.ElideRight, int(card.width()-24)))
        painter.restore()


class MessageList(QListWidget):
    item_requested = Signal(str)
    def __init__(self):
        super().__init__()
        self.setItemDelegate(MessageDelegate(self))
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(3)
        self.setAccessibleName("대화 내역")
        self.snapshot = None
        self.has_shown = False
        self._link_press = None
        self.media_assets = {}
        self.media_pixmaps = {}
        self.rich_cache = {}
        self.media_hits = []
        self.media_scales = {}
        self.media_animations = {}
        self.hovered_media = None
        self.setMouseTracking(True)

    def set_media(self, store):
        assets = {asset["id"]:asset for asset in store.media_assets(include_archived=True)}
        if assets == self.media_assets:return
        for asset_id in assets:
            if asset_id not in self.media_pixmaps:
                image = QPixmap();image.loadFromData(store.media_image(asset_id))
                self.media_pixmaps[asset_id] = image
        self.media_assets = assets
        self.rich_cache.clear()
        self.doItemsLayout();self.viewport().update()

    def paintEvent(self,event):
        self.media_hits = []
        super().paintEvent(event)

    def hover_media(self,key):
        if key == self.hovered_media:return
        previous = self.hovered_media
        self.hovered_media = key
        for target,scale in [(previous,1.0),(key,1.08)]:
            if target is None:continue
            old = self.media_animations.pop(target,None)
            if old:old.stop();old.deleteLater()
            animation = QVariantAnimation(self)
            self.media_animations[target] = animation
            animation.setDuration(280)
            animation.setEasingCurve(QEasingCurve.Type.OutBack)
            animation.setStartValue(self.media_scales.get(target,1.0))
            animation.setEndValue(scale)
            animation.valueChanged.connect(lambda value,k=target:self.update_media_scale(k,value))
            animation.finished.connect(lambda k=target,a=animation:self.finish_media_animation(k,a))
            animation.start()

    def update_media_scale(self,key,value):
        self.media_scales[key] = value
        self.viewport().update()

    def finish_media_animation(self,key,animation):
        if self.media_animations.get(key) is animation:self.media_animations.pop(key,None)
        if key != self.hovered_media:self.media_scales.pop(key,None)
        animation.deleteLater()

    def mouseMoveEvent(self,event):
        hit = next(((key,name) for rect,key,name in self.media_hits if rect.contains(event.position())),None)
        self.hover_media(hit[0] if hit else None)
        self.viewport().setToolTip(hit[1] if hit else "")
        super().mouseMoveEvent(event)

    def leaveEvent(self,event):
        self.hover_media(None)
        super().leaveEvent(event)

    def scrollContentsBy(self,dx,dy):
        self.hover_media(None)
        super().scrollContentsBy(dx,dy)

    def mousePressEvent(self, event):
        self._link_press = event.position().toPoint() if event.button() == Qt.MouseButton.LeftButton else None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        point = event.position().toPoint()
        row = self.itemAt(point)
        target = None
        item_target = None
        if row and self._link_press is not None and event.button() == Qt.MouseButton.LeftButton and (point-self._link_press).manhattanLength() <= 6:
            message = row.data(DATA_ROLE)
            area = self.visualItemRect(row).adjusted(5, 0, -5, 0)
            width, height, header, author = self.itemDelegate().layout_for(area.width(), message)
            x = area.right()-width if message["role"] == "user" else area.left()
            for offset, (title, url) in enumerate(source_links(message)):
                rect = QRectF(x+3, area.top()+header+author+height+23+offset*22, width-6, 20)
                if rect.contains(event.position()):
                    target = url
                    break
            card_y = area.top()+header+author+height+24+len(source_links(message))*22
            for offset, item in enumerate(message.get("created_items", [])):
                rect = QRectF(area.left(), card_y+offset*58, max(80, area.width()-24), 50)
                if item["available"] and rect.contains(event.position()):
                    item_target = item["id"]
                    break
        self._link_press = None
        super().mouseReleaseEvent(event)
        if item_target:
            self.item_requested.emit(item_target)
        if target:
            QDesktopServices.openUrl(QUrl(target))

    def showEvent(self, event):
        super().showEvent(event)
        if not self.has_shown:
            self.has_shown = True
            QTimer.singleShot(0, self.scrollToBottom)

    def set_messages(self, messages, prepend=False):
        if messages == self.snapshot:
            return
        bar = self.verticalScrollBar()
        old, maximum = bar.value(), bar.maximum()
        at_bottom = old >= maximum - 12
        self.clear()
        previous = None
        for original in messages:
            message = dict(original)
            date = QDate.fromString(message["created_at"][:10], "yyyy-MM-dd")
            message["date_label"] = f'{date.month()}월 {date.day()}일 {DAYS[date.dayOfWeek() % 7]}요일' if not previous or previous["created_at"][:10] != original["created_at"][:10] else ""
            same_group = previous and previous["role"] == message["role"] and not message["date_label"] and abs((datetime.fromisoformat(message["created_at"]) - datetime.fromisoformat(previous["created_at"])).total_seconds()) < 300
            message["show_author"] = message["role"] == "assistant" and not same_group
            row = QListWidgetItem(message["content"])
            row.setData(Qt.ItemDataRole.UserRole, message["id"])
            row.setData(DATA_ROLE, message)
            if source_links(message):
                row.setToolTip("답변 아래 출처를 클릭해 브라우저에서 열기")
            self.addItem(row)
            previous = original
        self.snapshot = messages
        self.doItemsLayout()
        if prepend:
            bar.setValue(old + bar.maximum() - maximum)
        elif at_bottom:
            self.scrollToBottom()
        else:
            bar.setValue(old)

    def resizeEvent(self, event):
        bar = self.verticalScrollBar()
        following = bar.value() >= bar.maximum() - 12
        super().resizeEvent(event)
        self.doItemsLayout()
        if following:
            self.scrollToBottom()


class AgendaDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        item = index.data(DATA_ROLE)
        width = max(100, self.parent().viewport().width() - 98)
        height = QFontMetrics(font(14)).boundingRect(QRect(0, 0, width, 10000), Qt.TextFlag.TextWordWrap, item_title(item)).height()
        return QSize(0, max(69, height + 41))

    def paint(self, painter, option, index):
        item = index.data(DATA_ROLE)
        if not item:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(2, 2, -2, -2)
        done = is_done(item)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(themed_color("#fcf1f6"))
        painter.drawRoundedRect(QRectF(rect), 15, 15)
        circle = QRectF(rect.left() + 13, rect.top() + 18, 19, 19)
        color = themed_color(COLORS[item["kind"]])
        painter.setPen(QPen(color, 1.5))
        painter.setBrush(color if done else themed_color("#ffffff"))
        painter.drawEllipse(circle)
        if done:
            painter.setPen(QPen(themed_color("white"), 1.7))
            painter.drawLine(QPointF(circle.x() + 5, circle.y() + 10), QPointF(circle.x() + 8, circle.y() + 13))
            painter.drawLine(QPointF(circle.x() + 8, circle.y() + 13), QPointF(circle.x() + 14, circle.y() + 6))
        painter.setFont(font(18))
        painter.setPen(themed_color("#bca6b2"))
        painter.drawText(QRect(rect.right()-23, rect.top()+15, 18, 24), Qt.AlignmentFlag.AlignCenter, "›")
        text_rect = QRect(rect.left() + 44, rect.top() + 12, rect.width() - 76, rect.height() - 32)
        text_font = font(14)
        text_font.setStrikeOut(done)
        painter.setFont(text_font)
        painter.setPen(themed_color("#bca6b2" if done else "#654b59"))
        painter.drawText(text_rect, Qt.TextFlag.TextWordWrap, item_title(item))
        painter.setFont(font(11))
        painter.setPen(themed_color("#ac929f"))
        painter.drawText(QRect(text_rect.x(), rect.bottom() - 23, text_rect.width(), 18), Qt.AlignmentFlag.AlignLeft, item_detail(item))
        painter.restore()


class AgendaList(QListWidget):
    toggle_requested = Signal(str)
    edit_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setItemDelegate(AgendaDelegate(self))
        self.setSpacing(3)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self._press = None
        self.full_height = False
        self.snapshot = None
        self.editable = True

    def set_items(self, items):
        snapshot = [(item, is_done(item)) for item in items]
        if self.snapshot == snapshot:
            return
        old = self.verticalScrollBar().value()
        self.clear()
        for item in items:
            row = QListWidgetItem(item_title(item) + "\n" + item_detail(item))
            row.setData(Qt.ItemDataRole.UserRole, item["id"])
            row.setData(DATA_ROLE, item)
            row.setToolTip("원: 완료/취소 · 제목 또는 카드 클릭: 상세/2차 일정")
            self.addItem(row)
        self.snapshot = snapshot
        self.doItemsLayout()
        self.verticalScrollBar().setValue(old)
        self.fit_contents()

    def set_full_height(self):
        self.full_height = True
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.fit_contents()

    def fit_contents(self):
        if not self.full_height:
            return
        height = sum(self.sizeHintForRow(i) + 2*self.spacing() for i in range(self.count())) + 2*self.frameWidth()
        if self.height() != height:
            self.setFixedHeight(height)
        self.verticalScrollBar().setValue(0)

    def wheelEvent(self, event):
        if self.full_height:
            parent = self.parentWidget()
            while parent is not None and not isinstance(parent, QScrollArea):
                parent = parent.parentWidget()
            if parent is not None:
                QApplication.sendEvent(parent.viewport(), event)
            else:
                event.ignore()
        else:
            super().wheelEvent(event)

    def card_rect(self, row):
        return self.visualItemRect(row)

    def mousePressEvent(self, event):
        row = self.itemAt(event.position().toPoint())
        self._press = (row.data(Qt.ItemDataRole.UserRole), event.position().toPoint()) if row and event.button() == Qt.MouseButton.LeftButton else None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        point = event.position().toPoint()
        row = self.itemAt(point)
        action = None
        if row and event.button() == Qt.MouseButton.LeftButton and self._press:
            item_id, origin = self._press
            rect = self.card_rect(row)
            if item_id == row.data(Qt.ItemDataRole.UserRole) and (point-origin).manhattanLength() <= 6 and rect.contains(point):
                toggle = QRect(rect.left()+10, rect.top()+12, 28, 32)
                if not toggle.contains(point) or self.editable:
                    action = (self.toggle_requested if toggle.contains(point) else self.edit_requested, item_id)
        self._press = None
        # A completion may rebuild the model; finish the Qt mouse event first.
        super().mouseReleaseEvent(event)
        if action:
            action[0].emit(action[1])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.doItemsLayout()
        self.fit_contents()


class CalendarGrid(QWidget):
    selected = Signal(QDate)

    def __init__(self):
        super().__init__()
        self.month = QDate.currentDate()
        self.selection = self.month
        self.marks = {}
        self.setFixedHeight(250)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("월간 달력 · 방향키로 날짜 이동")

    def first_cell(self):
        first = QDate(self.month.year(), self.month.month(), 1)
        return first.addDays(-(first.dayOfWeek() % 7))

    def cell_date(self, point):
        row = int((point.y() - 26) / 36)
        column = int(point.x() / (self.width() / 7))
        if point.y() >= 26 and 0 <= row < 6 and 0 <= column < 7:
            return self.first_cell().addDays(row * 7 + column)
        return QDate()

    def mouseReleaseEvent(self, event):
        date = self.cell_date(event.position())
        if date.isValid() and event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(date)

    def keyPressEvent(self, event):
        delta = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Up: -7, Qt.Key.Key_Down: 7}.get(event.key())
        if delta is not None:
            self.selected.emit(self.selection.addDays(delta))
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        column_width = self.width() / 7
        painter.setFont(font(11))
        for col, name in enumerate(DAYS):
            painter.setPen(themed_color("#bf8e8e" if col == 0 else "#aa919f"))
            painter.drawText(QRectF(col * column_width, 0, column_width, 20), Qt.AlignmentFlag.AlignCenter, name)
        today = now_kst().date().isoformat()
        for index in range(42):
            date = self.first_cell().addDays(index)
            col, row = index % 7, index // 7
            center = QPointF((col + .5) * column_width, 26 + row * 36 + 14)
            selected = date == self.selection
            is_today = date.toString("yyyy-MM-dd") == today
            if selected or is_today:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(themed_color("#d64289" if selected else "#fbe7f1"))
                painter.drawEllipse(center, 14, 14)
            painter.setFont(font(13, selected or is_today))
            painter.setPen(themed_color(foreground() if selected else "#cfbfc8" if date.month() != self.month.month() else "#bf8e8e" if col == 0 else "#654b59"))
            painter.drawText(QRectF(center.x() - 16, center.y() - 14, 32, 28), Qt.AlignmentFlag.AlignCenter, str(date.day()))
            dots = self.marks.get(date.toString("yyyy-MM-dd"), [])[:3]
            for dot, color in enumerate(dots):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(themed_color(color))
                painter.drawEllipse(QPointF(center.x() + (dot - (len(dots) - 1) / 2) * 6, center.y() + 18), 1.7, 1.7)


class MobileCalendar(QWidget):
    selectionChanged = Signal()
    currentPageChanged = Signal(int, int)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        row = QHBoxLayout()
        self.month_label = QLabel()
        self.month_label.setObjectName("monthTitle")
        row.addWidget(self.month_label)
        row.addStretch()
        self.today_button = QPushButton("오늘")
        self.today_button.setObjectName("quietButton")
        self.today_button.clicked.connect(self.go_today)
        row.addWidget(self.today_button)
        for name, delta in [("‹", -1), ("›", 1)]:
            button = QPushButton(name)
            button.setObjectName("monthArrow")
            button.setFixedSize(29, 29)
            button.setAccessibleName("이전 달" if delta < 0 else "다음 달")
            button.clicked.connect(lambda checked=False, step=delta: self.move_month(step))
            row.addWidget(button)
        layout.addLayout(row)
        self.grid = CalendarGrid()
        layout.addWidget(self.grid)
        self.grid.selected.connect(self.setSelectedDate)
        self.go_today()

    def go_today(self):
        now = now_kst()
        self.setSelectedDate(QDate(now.year, now.month, now.day))

    def selectedDate(self):
        return self.grid.selection

    def setSelectedDate(self, date):
        if not date.isValid():
            return
        changed = self.grid.selection != date
        page_changed = (self.grid.month.year(), self.grid.month.month()) != (date.year(), date.month())
        self.grid.selection = date
        self.grid.month = QDate(date.year(), date.month(), 1)
        self.update_header()
        if page_changed:
            self.currentPageChanged.emit(date.year(), date.month())
        if changed:
            self.selectionChanged.emit()
        self.grid.update()

    def move_month(self, step):
        self.grid.month = self.grid.month.addMonths(step)
        self.update_header()
        self.currentPageChanged.emit(self.grid.month.year(), self.grid.month.month())
        self.grid.update()

    def update_header(self):
        self.month_label.setText(f'{self.grid.month.year()}년 {self.grid.month.month()}월')

    def yearShown(self):
        return self.grid.month.year()

    def monthShown(self):
        return self.grid.month.month()

    def set_marks(self, marks):
        self.grid.marks = marks
        self.grid.update()


def schedule_time(item):
    return None if item.get("carryover") else event_time(item)


def timeline_items(items):
    return sorted(items, key=lambda item: (0 if item.get("carryover") else 1 if schedule_time(item) is None else 2, item["at"] if item.get("carryover") else schedule_time(item) or "", item_title(item)))


class TimelineDelegate(AgendaDelegate):
    def sizeHint(self, option, index):
        item = index.data(DATA_ROLE)
        width = max(100, self.parent().viewport().width() - (168 if schedule_time(item) else 98))
        height = QFontMetrics(font(14)).boundingRect(QRect(0, 0, width, 10000), Qt.TextFlag.TextWordWrap, item_title(item)).height()
        return QSize(0, max(69, height + 41) + (28 if item.get("timeline_header") else 0))

    def paint(self, painter, option, index):
        from PySide6.QtWidgets import QStyleOptionViewItem
        item = index.data(DATA_ROLE)
        header = item.get("timeline_header")
        timed = schedule_time(item)
        painter.save()
        if header:
            painter.setFont(font(11))
            painter.setPen(themed_color("#ac929f"))
            painter.drawText(option.rect.adjusted(4, 2, -4, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, header)
        top = option.rect.top() + (28 if header else 0)
        if timed:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(themed_color("#ecd6e1"), 1))
            painter.drawLine(QPointF(option.rect.x() + 60, top), QPointF(option.rect.x() + 60, option.rect.bottom()))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(themed_color(COLORS[item["kind"]]))
            painter.drawEllipse(QPointF(option.rect.x() + 60, top + 26), 3, 3)
            painter.setPen(themed_color("#a5748d"))
            painter.setFont(font(12))
            painter.drawText(QRect(option.rect.x(), top + 16, 49, 22), Qt.AlignmentFlag.AlignRight, timed)
        painter.restore()
        card = QStyleOptionViewItem(option)
        card.rect = QRect(option.rect.x() + (74 if timed else 0), top, option.rect.width() - (74 if timed else 0), option.rect.bottom() - top + 1)
        super().paint(painter, card, index)


class TimelineList(AgendaList):
    def __init__(self):
        super().__init__()
        self.setItemDelegate(TimelineDelegate(self))
        self.setAccessibleName("오늘의 일정 타임라인")

    def set_items(self, items):
        prepared = []
        previous = None
        for item in timeline_items(items):
            item = dict(item)
            group = "이전 미완료" if item.get("carryover") else "시간 미정" if schedule_time(item) is None else "타임라인"
            item["timeline_header"] = group if group != previous else ""
            prepared.append(item)
            previous = group
        super().set_items(prepared)

    def card_rect(self, row):
        rect = self.visualItemRect(row)
        data = row.data(DATA_ROLE)
        return rect.adjusted(74 if schedule_time(data) else 0, 28 if data.get("timeline_header") else 0, 0, 0)
