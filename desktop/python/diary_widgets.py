"""Date-based diary with debounced local saves; with conversation-based AI drafts."""
from sqlite3 import Error as SQLiteError
from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import QAbstractSpinBox, QDateEdit, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget
from store import now_kst
from ui_widgets import MobileCalendar


class DiaryWidget(QWidget):
    def __init__(self, store, companion=None):
        super().__init__()
        self.store = store
        self.companion = companion
        self.current_day = now_kst().date().isoformat()
        self.dirty = False
        self.loading = False
        self.delete_confirmed = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(12)
        title = QLabel("일기")
        title.setObjectName("heading")
        layout.addWidget(title)
        row = QHBoxLayout()
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
        self.content = QTextEdit()
        self.content.setAcceptRichText(False)
        self.content.setPlaceholderText("오늘 하루는 어땠나요?\n마음에 남은 일을 자유롭게 적어두세요.")
        self.content.setAccessibleName("일기 본문")
        layout.addWidget(self.content, 1)
        self.draft_button = QPushButton("대화로 AI 초안 쓰기")
        self.draft_button.clicked.connect(self.generate_draft)
        layout.addWidget(self.draft_button)
        self.draft_status = QLabel("")
        self.draft_status.setWordWrap(True)
        self.draft_status.setObjectName("muted")
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
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.save_button = QPushButton("저장")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.flush)
        self.delete_button = QPushButton("이 날짜 일기 삭제")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self.delete)
        row.addWidget(self.save_button)
        row.addWidget(self.delete_button)
        layout.addLayout(row)
        note = QLabel("일기도 AI가 참고해요. 초안은 확인 후 적용하며, 설정에서 일기를 내보낼 수 있어요.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(700)
        self.timer.timeout.connect(self.flush)
        self.title.textChanged.connect(self.changed)
        self.content.textChanged.connect(self.changed)
        self.date.dateChanged.connect(self.change_date)
        self.load()

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
            self.date.setDate(QDate.fromString(day, "yyyy-MM-dd"))
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
        self.delete_button.setText("이 날짜 일기 삭제")
        self.dirty = True
        self.status.setText("저장 중…")
        self.timer.start()

    def flush(self):
        self.timer.stop()
        if not self.dirty:
            return True
        try:
            self.store.save_diary(self.current_day, self.title.text(), self.content.toPlainText())
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
        # A mobile edit can refresh the current entry without resetting cursor on every tick.
        if self.title.text() != title:
            self.title.setText(title)
        if self.content.toPlainText() != content:
            self.content.setPlainText(content)
        self.loading = False
        self.delete_confirmed = False
        self.delete_button.setText("이 날짜 일기 삭제")
        self.delete_button.setEnabled(entry is not None)

    def delete(self):
        if not self.delete_confirmed:
            self.delete_confirmed = True
            self.delete_button.setText("한 번 더 누르면 삭제돼요")
            return
        self.timer.stop()
        self.store.delete_diary(self.current_day)
        self.dirty = False
        self.load()
        self.status.setText("삭제했어요.")
