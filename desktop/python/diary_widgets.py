"""Diary list with tag filter, and a date-based editor with debounced local saves and AI drafts."""
from sqlite3 import Error as SQLiteError
from PySide6.QtCore import QDate, Qt, QTimer, Signal
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QDateEdit, QHBoxLayout, QLabel, QLineEdit, QFrame, QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget
from appearance import current, style as themed_style
from store import MOODS, WEATHERS, now_kst
from PySide6.QtGui import QFontMetrics
from ui_widgets import MobileCalendar, font

BOOKMARK_STYLE = ("QWidget#bookmarks { background: #fbf0f6; border-radius: 12px; } "
                  "QFrame#bookmark { background: #fffafd; border-radius: 10px; }")
ENTRY_STYLE = ("QFrame#entry { background: #fbf0f6; border-radius: 14px; } QFrame#entry:hover { background: #f6e1ec; } "
               "QLabel#entryTitle { font-size: 14px; color: #573d4b; } QLabel#entryTags { color: #b65d88; font-size: 11px; }")
DAYS = "일월화수목금토"


class AutoHideLabel(QLabel):
    """A muted status line that takes no space while empty."""
    def __init__(self):
        super().__init__("")
        self.setWordWrap(True)
        self.setObjectName("muted")
        self.hide()

    def setText(self, text):
        super().setText(text)
        self.setVisible(bool(text))

    def clear(self):
        self.setText("")


class EntryCard(QFrame):
    clicked = Signal(str)

    def __init__(self, entry):
        super().__init__()
        self.day = entry["date"]
        self.setObjectName("entry")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(self.day + " 일기 열기")
        column = QVBoxLayout(self)
        column.setContentsMargins(14, 10, 14, 12)
        column.setSpacing(4)
        day = QDate.fromString(self.day, "yyyy-MM-dd")
        icons = " ".join(value.split(" ", 1)[0] for value in (entry["weather"], entry["mood"]) if value)
        meta = QLabel(f'{self.day.replace("-", ".")} {DAYS[day.dayOfWeek() % 7]}' + ("   " + icons if icons else ""))
        meta.setObjectName("muted")
        column.addWidget(meta)
        title = QLabel(entry["title"] or "제목 없음")
        title.setObjectName("entryTitle")
        column.addWidget(title)
        preview = " ".join(entry["content"].split())
        if preview:
            text = QLabel(preview[:90] + ("…" if len(preview) > 90 else ""))
            text.setWordWrap(True)
            column.addWidget(text)
        if entry["tags"]:
            tags = QLabel(" ".join("#" + tag for tag in entry["tags"]))
            tags.setObjectName("entryTags")
            tags.setWordWrap(True)
            column.addWidget(tags)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.day)
        super().mouseReleaseEvent(event)


class DiaryWidget(QWidget):
    def __init__(self, store, companion=None):
        super().__init__()
        self.store = store
        self.companion = companion
        self.current_day = now_kst().date().isoformat()
        self.dirty = False
        self.loading = False
        self.delete_confirmed = False
        self.bookmark_snapshot = None
        self.entries_snapshot = None
        self.view = "list"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(12)
        row = QHBoxLayout()
        title = QLabel("일기")
        title.setObjectName("heading")
        row.addWidget(title)
        row.addStretch()
        self.new_button = QPushButton("＋")
        self.new_button.setFixedSize(32, 32)
        self.new_button.setAccessibleName("새 일기")
        self.new_button.setToolTip("날짜를 골라 새 일기 쓰기")
        self.new_button.clicked.connect(self.new_entry)
        row.addWidget(self.new_button)
        layout.addLayout(row)
        self.bookmark_toggle = QPushButton("")
        self.bookmark_toggle.setCheckable(True)
        self.bookmark_toggle.setToolTip("대화 말풍선을 우클릭해 북마크할 수 있어요. 다시 누르면 일기로 돌아가요.")
        self.bookmark_toggle.toggled.connect(self.refresh_bookmarks)
        layout.addWidget(self.bookmark_toggle)
        self.bookmark_list = QScrollArea()
        self.bookmark_list.setWidgetResizable(True)
        self.bookmark_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.bookmark_list.setAccessibleName("북마크한 말풍선")
        self.bookmark_cards = QWidget()
        self.bookmark_cards.setObjectName("bookmarks")
        QVBoxLayout(self.bookmark_cards).setContentsMargins(6, 6, 6, 6)
        self.bookmark_list.setWidget(self.bookmark_cards)
        self.bookmark_list.hide()
        layout.addWidget(self.bookmark_list, 1)
        # Bookmarks, the diary list and the editor each take the whole tab; the drawer is too short for two.
        self.browser = QWidget()
        layout.addWidget(self.browser, 1)
        column = QVBoxLayout(self.browser)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        self.tag_filter = QComboBox()
        self.tag_filter.setAccessibleName("태그별 보기")
        self.tag_filter.currentIndexChanged.connect(lambda: self.refresh_list())
        column.addWidget(self.tag_filter)
        self.entries = QScrollArea()
        self.entries.setWidgetResizable(True)
        self.entries.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.entries.setAccessibleName("일기 목록")
        self.entry_cards = QWidget()
        cards = QVBoxLayout(self.entry_cards)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(8)
        self.entries.setWidget(self.entry_cards)
        column.addWidget(self.entries, 1)
        self.editor = QScrollArea()
        self.editor.setWidgetResizable(True)
        self.editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.editor, 1)
        form = QWidget()
        self.editor.setWidget(form)
        layout = QVBoxLayout(form)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        back = QPushButton("‹ 목록")
        back.setObjectName("quietButton")
        back.setAccessibleName("일기 목록으로")
        back.clicked.connect(self.show_list)
        row = QHBoxLayout()
        row.addWidget(back)
        previous, following = QPushButton("‹"), QPushButton("›")
        previous.setAccessibleName("이전 날짜")
        following.setAccessibleName("다음 날짜")
        self.date = QDateEdit(QDate.fromString(self.current_day, "yyyy-MM-dd"))
        self.date.setParent(self)
        self.date.setMinimumHeight(40)
        self.date.lineEdit().setStyleSheet("padding: 0; border: none; background: transparent;")
        self.date.setDisplayFormat("yyyy.MM.dd")
        self.date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        previous.clicked.connect(lambda: self.date.setDate(self.date.date().addDays(-1)))
        following.clicked.connect(lambda: self.date.setDate(self.date.date().addDays(1)))
        row.addWidget(previous)
        self.date.hide()
        self.date_display = QPushButton(self.current_day.replace("-", "."))
        self.date_display.clicked.connect(self.pick_date)
        row.addWidget(self.date_display, 1)
        row.addWidget(following)
        layout.addLayout(row)
        self.title = QLineEdit()
        self.title.setMaxLength(200)
        self.title.setPlaceholderText("오늘의 제목")
        self.title.setAccessibleName("일기 제목")
        layout.addWidget(self.title)
        row = QHBoxLayout()
        self.weather, self.mood = QComboBox(), QComboBox()
        for combo, placeholder, options in ((self.weather, "날씨", WEATHERS), (self.mood, "기분", MOODS)):
            combo.setAccessibleName(placeholder)
            combo.addItem(placeholder, "")
            for option in options:
                combo.addItem(option, option)
            row.addWidget(combo, 1)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("태그: 산책, 카페")
        self.tags.setToolTip("태그는 쉼표로 구분해요")
        self.tags.setAccessibleName("일기 태그")
        row.addWidget(self.tags, 1)
        layout.addLayout(row)
        self.content = QTextEdit()
        self.content.setAcceptRichText(False)
        self.content.setPlaceholderText("오늘 하루는 어땠나요?\n마음에 남은 일을 자유롭게 적어두세요.")
        self.content.setAccessibleName("일기 본문")
        self.content.setMinimumHeight(10 * QFontMetrics(font(13)).lineSpacing() + 30)  # At least ten lines.
        layout.addWidget(self.content, 1)
        self.draft_status = AutoHideLabel()
        layout.addWidget(self.draft_status)
        self.draft_preview = QTextEdit()
        self.draft_preview.setReadOnly(True)
        self.draft_preview.setFixedHeight(110)
        self.draft_preview.hide()
        layout.addWidget(self.draft_preview)
        self.draft_actions = QWidget()
        actions = QHBoxLayout(self.draft_actions)
        actions.setContentsMargins(0, 0, 0, 0)
        apply = QPushButton("이 초안 적용")
        apply.clicked.connect(self.apply_draft)
        dismiss = QPushButton("초안 닫기")
        dismiss.clicked.connect(lambda: self.companion.dismiss_diary_draft())
        actions.addWidget(apply)
        actions.addWidget(dismiss)
        self.draft_actions.hide()
        layout.addWidget(self.draft_actions)
        self.status = AutoHideLabel()
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.draft_button = QPushButton("AI 초안")
        self.draft_button.setToolTip("이 날짜의 대화로 일기 초안 쓰기 (적용 전 미리보기)")
        self.draft_button.clicked.connect(self.generate_draft)
        row.addWidget(self.draft_button)
        self.save_button = QPushButton("저장")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.flush)
        self.delete_button = QPushButton("삭제")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self.delete)
        row.addWidget(self.save_button)
        row.addWidget(self.delete_button)
        layout.addLayout(row)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(700)
        self.timer.timeout.connect(self.flush)
        self.title.textChanged.connect(self.changed)
        self.content.textChanged.connect(self.changed)
        self.tags.textChanged.connect(self.changed)
        self.weather.currentIndexChanged.connect(self.changed)
        self.mood.currentIndexChanged.connect(self.changed)
        self.date.dateChanged.connect(self.change_date)
        self.apply_theme()
        self.load()
        self.refresh_bookmarks()
        self.refresh_list()

    def apply_theme(self):
        # The drawer is built before the saved theme loads, so the theme is re-applied here.
        self.bookmark_cards.setStyleSheet(themed_style(BOOKMARK_STYLE))
        self.entry_cards.setStyleSheet(themed_style(ENTRY_STYLE))

    def update_view(self):
        reading = self.bookmark_toggle.isChecked()
        self.bookmark_list.setVisible(reading)
        self.bookmark_toggle.setVisible(reading or self.view == "list")
        self.browser.setVisible(not reading and self.view == "list")
        self.editor.setVisible(not reading and self.view == "editor")

    def show_list(self):
        if not self.flush():
            return
        self.view = "list"
        self.bookmark_toggle.setChecked(False)
        self.update_view()
        self.refresh_list()

    def open_entry(self, day):
        if not self.flush():
            return False
        self.view = "editor"
        self.bookmark_toggle.setChecked(False)
        self.update_view()
        self.date.setDate(QDate.fromString(day, "yyyy-MM-dd"))
        self.load()
        return True

    def new_entry(self):
        if self.open_entry(now_kst().date().isoformat()):
            QTimer.singleShot(0, self.pick_date)

    def refresh_list(self):
        tags = self.store.diary_tag_counts()
        selected = self.tag_filter.currentData() or ""
        if [self.tag_filter.itemData(i) for i in range(1, self.tag_filter.count())] != [tag for tag, _ in tags]:
            self.tag_filter.blockSignals(True)
            self.tag_filter.clear()
            self.tag_filter.addItem("모든 태그", "")
            for tag, count in tags:
                self.tag_filter.addItem(f"#{tag}  ({count})", tag)
            self.tag_filter.setCurrentIndex(max(0, self.tag_filter.findData(selected)))
            self.tag_filter.blockSignals(False)
        self.tag_filter.setVisible(bool(tags))
        entries = self.store.diary_entries(self.tag_filter.currentData() or None)
        if entries == self.entries_snapshot:
            return
        self.entries_snapshot = entries
        cards = self.entry_cards.layout()
        while cards.count():
            item = cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not entries:
            empty = QLabel("아직 쓴 일기가 없어요.\n＋를 눌러 날짜를 고르고 써보세요.")
            empty.setObjectName("muted")
            cards.addWidget(empty)
        for entry in entries:
            card = EntryCard(entry)
            card.clicked.connect(self.open_entry)
            cards.addWidget(card)
        cards.addStretch()

    def refresh_bookmarks(self):
        bookmarks = self.store.bookmarks()
        expanded = self.bookmark_toggle.isChecked()
        self.bookmark_toggle.setText(f"★ 북마크 {len(bookmarks)}개 " + ("▴" if expanded else "▾"))
        self.update_view()
        snapshot = (bookmarks, current()["name"])
        if not expanded or snapshot == self.bookmark_snapshot:
            return
        self.bookmark_snapshot = snapshot
        cards = self.bookmark_cards.layout()
        while cards.count():
            cards.takeAt(0).widget().deleteLater()
        if not bookmarks:
            empty = QLabel("아직 북마크가 없어요.\n대화에서 말풍선을 우클릭해 북마크해보세요.")
            empty.setObjectName("muted")
            cards.addWidget(empty)
        for bookmark in bookmarks:
            card = QFrame()
            card.setObjectName("bookmark")
            column = QVBoxLayout(card)
            column.setContentsMargins(10, 6, 6, 8)
            column.setSpacing(2)
            head = QHBoxLayout()
            author = "나" if bookmark["role"] == "user" else current()["name"]
            meta = QLabel(f'{author} · {bookmark["created_at"][:16].replace("-", ".").replace("T", " ")}')
            meta.setObjectName("muted")
            head.addWidget(meta, 1)
            remove = QPushButton("해제")
            remove.setObjectName("quietButton")
            remove.setAccessibleName("북마크 해제")
            remove.clicked.connect(lambda checked=False, message_id=bookmark["id"]: self.companion.toggle_bookmark(message_id))
            head.addWidget(remove)
            column.addLayout(head)
            text = QLabel(bookmark["content"])
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            column.addWidget(text)
            cards.addWidget(card)
        cards.addStretch()

    def generate_draft(self):
        try:
            self.companion.generate_diary_draft(self.current_day)
        except ValueError as error:
            self.draft_status.setText(str(error))

    def refresh_draft(self):
        if not self.companion:
            return
        draft = self.companion.diary_draft
        self.draft_status.setText((draft["date"] + " · " if draft else "") + self.companion.diary_draft_status)
        self.draft_preview.setVisible(draft is not None)
        self.draft_actions.setVisible(draft is not None)
        self.draft_preview.setPlainText(draft["content"] if draft else "")

    def apply_draft(self):
        try:
            day = self.companion.diary_draft["date"] if self.companion.diary_draft else self.current_day
            self.companion.apply_diary_draft()
            self.open_entry(day)
        except ValueError as error:
            self.draft_status.setText(str(error))

    def pick_date(self):
        self.date_popup = QWidget(self, Qt.WindowType.Popup)
        self.date_popup.setStyleSheet("background: #fffafd; color: #634b58; border-radius: 14px;")
        layout = QVBoxLayout(self.date_popup)
        calendar = MobileCalendar()
        calendar.setSelectedDate(self.date.date())
        def choose():
            self.date.setDate(calendar.selectedDate())
            self.date_popup.hide()
        calendar.selectionChanged.connect(choose)
        layout.addWidget(calendar)
        self.date_popup.resize(350, 330)
        self.date_popup.move(self.date_display.mapToGlobal(self.date_display.rect().bottomLeft()))
        self.date_popup.show()

    def changed(self):
        if self.loading:
            return
        self.delete_confirmed = False
        self.delete_button.setText("삭제")
        self.dirty = True
        self.status.setText("저장 중…")
        self.timer.start()

    def flush(self):
        self.timer.stop()
        if not self.dirty:
            return True
        try:
            self.store.save_diary(self.current_day, self.title.text(), self.content.toPlainText(),
                                  weather=self.weather.currentData(), mood=self.mood.currentData(), tags=self.tags.text())
        except (ValueError, OSError, SQLiteError) as error:
            self.status.setText(str(error))
            return False
        self.dirty = False
        self.status.setText("저장했어요.")
        self.delete_button.setEnabled(True)
        return True

    def change_date(self, date):
        if not self.flush():
            self.date.blockSignals(True)
            self.date.setDate(QDate.fromString(self.current_day, "yyyy-MM-dd"))
            self.date.blockSignals(False)
            return
        self.current_day = date.toString("yyyy-MM-dd")
        self.date_display.setText(self.current_day.replace("-", "."))
        self.status.clear()
        self.load()

    def load(self):
        if self.dirty:
            return
        entry = self.store.diary_entry(self.current_day)
        self.loading = True
        title, content = (entry["title"], entry["content"]) if entry else ("", "")
        for combo, value in ((self.weather, entry["weather"] if entry else ""), (self.mood, entry["mood"] if entry else "")):
            if combo.findData(value) < 0:
                combo.addItem(value, value)
            combo.setCurrentIndex(combo.findData(value))
        tags = ", ".join(entry["tags"]) if entry else ""
        # Keep a trailing comma while typing; only replace when the saved tags differ.
        if [tag.strip() for tag in self.tags.text().split(",") if tag.strip()] != (entry["tags"] if entry else []):
            self.tags.setText(tags)
        # A mobile edit can refresh the current entry without resetting cursor on every tick.
        if self.title.text() != title:
            self.title.setText(title)
        if self.content.toPlainText() != content:
            self.content.setPlainText(content)
        self.loading = False
        self.delete_confirmed = False
        self.delete_button.setText("삭제")
        self.delete_button.setEnabled(entry is not None)

    def delete(self):
        if not self.delete_confirmed:
            self.delete_confirmed = True
            self.delete_button.setText("한 번 더!")
            return
        self.timer.stop()
        self.store.delete_diary(self.current_day)
        self.dirty = False
        self.load()
        self.status.setText("삭제했어요.")
        self.show_list()
