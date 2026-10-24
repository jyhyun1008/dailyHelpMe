"""The single compact application window: chat, calendar, tasks and preferences."""
from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import QDate, QPoint, QSettings, Qt, QTime, Signal, QSaveFile, QIODevice, QUrl
from PySide6.QtGui import QColor, QImage, QTextDocument, QTextImageFormat
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QButtonGroup, QCheckBox, QComboBox, QDateEdit, QFrame,
    QFileDialog, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSlider, QStackedWidget, QTextBrowser, QTextEdit, QTimeEdit,
    QVBoxLayout, QWidget,
)

from calendar_data import today_items
from branding import APP_NAME, APP_NAME_EN, APP_VERSION, ROOT
from appearance import style as themed_style
from appearance_editor import AppearanceEditor
from subtask_widgets import SubtaskEditor
from diary_widgets import DiaryWidget
from weekly_widgets import WeeklyTimetable
from store import KINDS, now_kst
from ui_widgets import AgendaList, COLORS, DATA_ROLE, DAYS, MessageList, MobileCalendar, TimelineList, is_done

STYLE = """
QWidget { font-family: 'ThinMulmaru'; font-size: 13px; color: #634b58; }
QFrame#shell { background: #fffafd; border: 1px solid #efdfe7; border-radius: 26px; }
QLabel, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QLabel#brand { color: #573d4b; font-size: 17px; font-weight: normal; }
QLabel#muted { color: #a18b97; font-size: 11px; }
QLabel#heading, QLabel#monthTitle { color: #513644; font-size: 22px; font-weight: normal; }
QLabel#section { color: #8c6c7e; font-size: 13px; font-weight: normal; }
QPushButton { background: #f8edf3; color: #9b7087; border: none; border-radius: 12px; padding: 8px 12px; }
QPushButton:hover { background: #f3dfe9; }
QPushButton:disabled { color: #c5b2bd; background: #f8f1f5; }
QPushButton#primary { background: #b65d88; color: white; }
QPushButton#primary:hover { background: #a64d77; }
QPushButton#primary:disabled { background: #dfafc7; }
QPushButton#quietButton, QPushButton#monthArrow { background: transparent; padding: 5px; }
QPushButton#monthArrow { font-size: 25px; color: #ab7b94; }
QPushButton#navigation { background: transparent; color: #b29ba8; padding: 10px 8px; border-radius: 12px; }
QPushButton#navigation:checked { background: #fae8f1; color: #b65d88; font-weight: normal; }
QPushButton#danger { background: #faf0f0; color: #bb7474; }
QListWidget { background: transparent; border: none; outline: none; padding: 0; }
QScrollBar:vertical { width: 4px; background: transparent; }
QScrollBar::handle:vertical { background: #ead2de; border-radius: 2px; min-height: 26px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 4px; background: transparent; }
QScrollBar::handle:horizontal { background: #ead2de; border-radius: 2px; min-width: 26px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QLineEdit, QTextEdit, QTextBrowser, QComboBox, QDateEdit, QTimeEdit { background: #fbf0f6; border: 1px solid transparent; border-radius: 12px; padding: 9px; selection-background-color: #f3d4e4; }
QLineEdit:focus, QTextEdit:focus { border: 1px solid #e5b3cd; }
QComboBox::drop-down { border: none; width: 20px; }
QDateEdit, QTimeEdit { min-height: 20px; }
QSlider::groove:horizontal { background: #f1e0e9; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal { background: #d796b8; width: 12px; margin: -4px 0; border-radius: 6px; }
QCheckBox { spacing: 7px; color: #9e8292; }
"""


def button(text, callback=None, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    if callback:
        widget.clicked.connect(callback)
    return widget


def label(text, name="muted"):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(True)
    return widget


class Composer(QTextEdit):
    submitted = Signal()

    def __init__(self):
        super().__init__()
        self.setAcceptRichText(False)
        self.setPlaceholderText("메시지 보내기")
        self.setFixedHeight(46)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName("챗봇에게 보낼 메시지")
        self.emoji_movies = {}
        self.textChanged.connect(self.fit_height)

    def insert_emoji(self, asset_id, png):
        image = QImage.fromData(png)
        url = QUrl('customemoji/' + asset_id)
        self.document().addResource(QTextDocument.ResourceType.ImageResource,url,image)
        if asset_id not in self.emoji_movies:
            from chat_media import artwork_movie
            movie = artwork_movie(png, self, lambda frame: self.update_emoji_frame(url, frame))
            if movie: self.emoji_movies[asset_id] = movie
        format = QTextImageFormat()
        format.setName(url.toString());format.setWidth(26);format.setHeight(26)
        self.textCursor().insertImage(format)

    def update_emoji_frame(self, url, frame):
        self.document().addResource(QTextDocument.ResourceType.ImageResource, url, frame.toImage())
        self.document().markContentsDirty(0, self.document().characterCount())
        self.viewport().update()

    def message_text(self):
        from chat_media import emoji_token
        blocks = []
        block = self.document().begin()
        while block.isValid():
            pieces = []
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid():
                    if fragment.charFormat().isImageFormat():
                        name = fragment.charFormat().toImageFormat().name()
                        if name.startswith('customemoji/'):
                            pieces.append(emoji_token(name.split('/')[-1]))
                    else:pieces.append(fragment.text())
                iterator += 1
            blocks.append(''.join(pieces));block=block.next()
        return '\n'.join(blocks)

    def fit_height(self):
        self.document().setTextWidth(max(80, self.viewport().width()))
        height = int(self.document().size().height()) + 24
        self.setFixedHeight(max(46, min(100, height)))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if height > 100 else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submitted.emit()
        else:
            super().keyPressEvent(event)


class Header(QWidget):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel, self.offset = panel, None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.offset = event.globalPosition().toPoint() - self.panel.pos()

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.panel.move(event.globalPosition().toPoint() - self.offset)

    def mouseReleaseEvent(self, event):
        if self.offset is not None:
            self.panel.keep_on_screen()
            self.panel.settings.setValue("mini/position", self.panel.pos())
            self.offset = None


class Drawer(QWidget):
    visibility_changed = Signal(bool)

    def __init__(self, companion):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.companion, self.store = companion, companion.store
        self.settings = companion.pet.settings
        saved_tab = self.settings.value("mini/tab", 0, type=int)
        if saved_tab not in (0, 1, 2, 3, 4, 6):
            saved_tab = 0
        self.setWindowTitle(APP_NAME)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setFixedSize(420, 680)
        self.history_limit = 50
        self.shutting_down = False
        self.edit_id = None
        self.confirm_delete = False
        self.previous_page = 3
        self.setStyleSheet(STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        shell = QFrame()
        shell.setObjectName("shell")
        shadow = QGraphicsDropShadowEffect(shell)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(110, 65, 88, 25))
        shell.setGraphicsEffect(shadow)
        outer.addWidget(shell)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)
        header = Header(self)
        row = QHBoxLayout(header)
        row.setContentsMargins(5, 0, 0, 0)
        brand = label(APP_NAME, "brand")
        self.brand = brand
        brand.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(brand)
        row.addStretch()
        settings = button("설정", lambda: self.show_page(4))
        settings.setObjectName("quietButton")
        row.addWidget(settings)
        close = button("×", self.hide)
        close.setFixedSize(28, 28)
        close.setToolTip("서랍 숨기기 · 펫 클릭으로 다시 열기")
        row.addWidget(close)
        layout.addWidget(header)
        self.tabs = QStackedWidget()
        self.tabs.currentChanged.connect(self.page_changed)
        layout.addWidget(self.tabs, 1)
        self.build_today()
        self.build_chat()
        self.build_calendar()
        self.build_tasks()
        self.build_settings()
        self.build_editor()
        self.diary = DiaryWidget(self.store, self.companion)
        self.tabs.addWidget(self.diary)
        self.nav = QButtonGroup(self)
        navigation = QHBoxLayout()
        navigation.setSpacing(5)
        for index, text in ((0, "오늘"), (1, "대화"), (2, "달력"), (3, "할 일"), (6, "일기")):
            entry = button(text, lambda checked=False, i=index: self.show_page(i))
            entry.setObjectName("navigation")
            entry.setCheckable(True)
            self.nav.addButton(entry, index)
            navigation.addWidget(entry, 1)
        layout.addLayout(navigation)
        footer = QHBoxLayout()
        self.transparency_label = label("")
        footer.addWidget(self.transparency_label)
        self.transparency = QSlider(Qt.Orientation.Horizontal)
        self.transparency.setRange(0, 65)
        self.transparency.setValue(max(0, min(65, self.settings.value("mini/transparency", 8, type=int))))
        self.transparency.valueChanged.connect(self.set_transparency)
        footer.addWidget(self.transparency, 1)
        layout.addLayout(footer)
        self.set_transparency(self.transparency.value())
        saved = self.settings.value("mini/position")
        self.move(saved if isinstance(saved, QPoint) else companion.pet.pos() - QPoint(self.width() - 40, 170))
        self.keep_on_screen()
        self.show_page(saved_tab)
        self.refresh()

    def page(self, scroll=False):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(10)
        if scroll:
            wrapper = QScrollArea()
            wrapper.setWidgetResizable(True)
            wrapper.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            wrapper.setWidget(content)
            self.tabs.addWidget(wrapper)
        else:
            self.tabs.addWidget(content)
        return layout

    def agenda(self):
        view = AgendaList()
        view.toggle_requested.connect(self.companion.toggle_item)
        view.edit_requested.connect(self.edit_item)
        return view

    def build_today(self):
        page = self.page()
        self.today_title = label("", "muted")
        page.addWidget(self.today_title)
        row = QHBoxLayout()
        row.addWidget(label("오늘의 일정", "heading"))
        row.addStretch()
        self.today_add = button("＋", lambda: self.edit_item())
        self.today_add.setFixedSize(32, 32)
        self.today_add.setAccessibleName("일정 추가")
        row.addWidget(self.today_add)
        page.addLayout(row)
        self.today_count = label("")
        page.addWidget(self.today_count)
        self.today_empty = label("등록된 일정이 없어요.\n가볍게 하루를 시작해볼까요?")
        page.addWidget(self.today_empty)
        self.today = TimelineList()
        self.today.toggle_requested.connect(self.companion.toggle_item)
        self.today.edit_requested.connect(self.edit_item)
        page.addWidget(self.today, 1)

    def build_chat(self):
        page = self.page()
        row = QHBoxLayout()
        row.addWidget(label("대화", "heading"))
        row.addStretch()
        self.more = button("이전 대화 더 불러오기", self.load_older)
        self.more.setObjectName("quietButton")
        row.addWidget(self.more)
        page.addLayout(row)
        self.messages_empty = label("오늘은 어떤 하루였어요?\n여기서 바로 이야기 나눠요.")
        page.addWidget(self.messages_empty)
        self.messages = MessageList()
        self.messages.item_requested.connect(self.edit_item)
        self.messages.itemDoubleClicked.connect(lambda item: self.companion.confirm_message(item.data(Qt.ItemDataRole.UserRole)))
        self.messages.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.messages.customContextMenuRequested.connect(self.message_menu)
        page.addWidget(self.messages, 1)
        self.chat_status = label("")
        self.chat_status.hide()
        page.addWidget(self.chat_status)
        self.retry_button = button("다시 보내기", self.companion.retry)
        self.retry_button.hide()
        page.addWidget(self.retry_button)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = Composer()
        self.input.submitted.connect(self.companion.send)
        row.addWidget(self.input, 1)
        self.media_button = button("☺", self.open_media_picker)
        self.media_button.setAccessibleName("커스텀 이모지 · 스티커")
        self.media_button.setToolTip("이모지 · 스티커 등록 / 보내기")
        self.media_button.setFixedSize(36,36)
        row.addWidget(self.media_button,0,Qt.AlignmentFlag.AlignBottom)
        self.send_button = button("↑", self.companion.send, True)
        self.send_button.setFixedSize(36, 36)
        self.send_button.setAccessibleName("메시지 전송")
        row.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignBottom)
        page.addLayout(row)

    def message_menu(self, point):
        row = self.messages.itemAt(point)
        if not row:
            return
        from menus import RoundedMenu
        message = row.data(DATA_ROLE)
        menu = RoundedMenu()
        bookmark = menu.addAction("북마크 해제" if message.get("bookmarked") else "북마크하기")
        bookmark.triggered.connect(lambda: self.companion.toggle_bookmark(message["id"]))
        menu.exec(self.messages.viewport().mapToGlobal(point))

    def open_media_picker(self):
        from media_picker import MediaPicker
        if getattr(self, 'media_picker', None) is not None:
            self.media_picker.show()
            self.media_picker.raise_()
            self.media_picker.activateWindow()
            return
        self.media_picker = MediaPicker(self.companion,self)
        self.media_picker.destroyed.connect(lambda: setattr(self, 'media_picker', None))
        self.media_picker.show()

    def build_calendar(self):
        page = self.page(scroll=True)
        self.calendar_scroll = self.tabs.widget(2)
        self.calendar_scroll.setAccessibleName("달력과 선택한 날짜 일정 · 하나의 스크롤")
        page.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.calendar = MobileCalendar()
        self.calendar.selectionChanged.connect(self.refresh_calendar)
        self.calendar.currentPageChanged.connect(lambda *_: self.mark_calendar())
        modes = QHBoxLayout()
        self.calendar_modes = QButtonGroup(self)
        for index, title in enumerate(("월간", "주간 시간표")):
            b = button(title, lambda checked=False, i=index: self.set_calendar_mode(i))
            b.setCheckable(True)
            b.setObjectName("navigation")
            self.calendar_modes.addButton(b, index)
            modes.addWidget(b)
        page.addLayout(modes)
        self.calendar_views = QStackedWidget()
        self.calendar_views.addWidget(self.calendar)
        self.weekly = WeeklyTimetable()
        self.weekly.selected.connect(self.calendar.setSelectedDate)
        self.calendar_views.addWidget(self.weekly)
        page.addWidget(self.calendar_views)
        self.set_calendar_mode(0)
        row = QHBoxLayout()
        self.calendar_title = label("", "section")
        row.addWidget(self.calendar_title)
        row.addStretch()
        self.calendar_diary = button("일기 쓰기", self.open_calendar_diary)
        row.addWidget(self.calendar_diary)
        self.calendar_add = button("＋", lambda: self.edit_item())
        self.calendar_add.setFixedSize(29, 29)
        self.calendar_add.setAccessibleName("선택한 날짜에 일정 추가")
        row.addWidget(self.calendar_add)
        page.addLayout(row)
        self.calendar_empty = label("등록된 일정이 없어요.")
        page.addWidget(self.calendar_empty)
        self.calendar_list = self.agenda()
        self.calendar_list.set_full_height()
        page.addWidget(self.calendar_list)

    def open_calendar_diary(self):
        self.diary.open_entry(self.calendar.selectedDate().toString("yyyy-MM-dd"))
        self.show_page(6)

    def set_calendar_mode(self, index):
        index = 1 if index == 1 else 0
        self.calendar_views.setCurrentIndex(index)
        self.calendar_modes.button(index).setChecked(True)
        self.calendar_views.setFixedHeight(self.calendar.sizeHint().height() if index == 0 else 350)

    def build_tasks(self):
        page = self.page()
        row = QHBoxLayout()
        row.addWidget(label("할 일", "heading"))
        row.addStretch()
        self.task_add = button("＋ 추가", lambda: self.edit_item(kind="todo"))
        row.addWidget(self.task_add)
        page.addLayout(row)
        self.filter = QComboBox()
        self.filter.addItem("모든 실행목록", None)
        for kind, title in KINDS.items():
            self.filter.addItem(title, kind)
        self.filter.currentIndexChanged.connect(self.refresh_tasks)
        page.addWidget(self.filter)
        self.show_done = QCheckBox("완료한 일 포함")
        self.show_done.toggled.connect(self.refresh_tasks)
        page.addWidget(self.show_done)
        self.tasks_empty = label("떠오르는 일을 적어두세요.\n하나씩 가볍게 해봐요.")
        page.addWidget(self.tasks_empty)
        self.tasks = self.agenda()
        page.addWidget(self.tasks, 1)
        page.addWidget(label("원을 눌러 완료 · 제목을 눌러 상세/2차 일정"))

    def build_settings(self):
        page = self.page(scroll=True)
        page.addWidget(label("설정", "heading"))
        self.appearance_editor = AppearanceEditor(self.companion)
        page.addWidget(self.appearance_editor)
        self.memory_heading = label("봉고캣이(가) 기억하는 나", "section")
        page.addWidget(self.memory_heading)
        self.profile = QTextEdit()
        self.profile.setAcceptRichText(False)
        self.profile.setPlaceholderText("취향, 부르는 이름, 기억해둘 이야기")
        self.profile.setFixedHeight(110)
        page.addWidget(self.profile)
        self.profile_save = button("기억 저장", self.companion.save_profile)
        page.addWidget(self.profile_save)
        page.addWidget(label(APP_NAME + " · " + APP_NAME_EN + "  " + APP_VERSION, "section"))
        page.addWidget(button("앱 정보 · 개인정보 · 라이선스", self.show_app_information))
        page.addWidget(label("ChatGPT 연결", "section"))
        self.connection = label("로그인한 ChatGPT 계정의 Codex로 대화해요.")
        page.addWidget(self.connection)
        self.login_button = button("ChatGPT 로그인", self.companion.login)
        page.addWidget(self.login_button)
        self.web_search = QCheckBox("최신 정보가 필요하면 웹 검색 사용")
        self.web_search.setChecked(self.store.get("web_search_enabled", "1") == "1")
        self.web_search.toggled.connect(lambda enabled: self.store.set("web_search_enabled", "1" if enabled else "0"))
        page.addWidget(self.web_search)
        page.addWidget(label("날씨·뉴스처럼 최신 정보가 필요한 질문은 검색해 출처와 함께 답해요. 확인하지 못한 정보는 추측하지 않아요."))
        self.login_output = QTextBrowser()
        self.login_output.setOpenExternalLinks(True)
        self.login_output.setFixedHeight(90)
        self.login_output.hide()
        page.addWidget(self.login_output)
        page.addWidget(label("화면", "section"))
        motion = QCheckBox("펫 애니메이션 줄이기")
        motion.setChecked(self.settings.value("reduce_motion", False, type=bool))
        motion.toggled.connect(lambda value: self.settings.setValue("reduce_motion", value))
        page.addWidget(motion)
        page.addWidget(label("대화와 기억은 이 맥에 저장돼요. 답장을 요청할 때 최근 대화와 기억이 OpenAI로 전달됩니다. 구독 사용량 한도가 적용돼요."))
        page.addWidget(label("아이폰 · 아이패드 연결", "section"))
        self.mobile_enabled = QCheckBox("모바일 접속 허용")
        self.mobile_enabled.setChecked(self.store.get("mobile_enabled") == "1")
        self.mobile_enabled.toggled.connect(self.companion.configure_mobile)
        page.addWidget(self.mobile_enabled)
        self.mobile_status = label("")
        page.addWidget(self.mobile_status)
        page.addWidget(label("연결 코드", "section"))
        self.mobile_code = QLineEdit(self.companion.mobile.pairing_code)
        self.mobile_code.setReadOnly(True)
        page.addWidget(self.mobile_code)
        row = QHBoxLayout()
        row.addWidget(button("코드 복사", lambda: QApplication.clipboard().setText(self.mobile_code.text())))
        row.addWidget(button("연결 초기화", self.companion.reset_mobile_pairing))
        page.addLayout(row)
        page.addWidget(label("Tailscale HTTPS 주소를 Safari에서 열고 이 코드를 입력하세요. 공유 → 홈 화면에 추가 후, 홈 화면 앱에서 알림을 켜주세요. 맥은 켜져 있어야 해요."))
        self.mobile_command = QLineEdit("tailscale serve --bg --https=8765 http://127.0.0.1:8765")
        self.mobile_command.setReadOnly(True)
        self.mobile_command.setAccessibleName("Tailscale HTTPS 연결 명령")
        page.addWidget(self.mobile_command)
        page.addWidget(label("일기 내보내기", "section"))
        page.addWidget(label("날짜별 일기를 파일로 보관해요. 최근 일기는 AI가 대화에 참고하고, 선택한 날짜의 대화로 초안을 쓸 수 있어요."))
        page.addWidget(button("일기 JSON 내보내기", lambda: self.export_diary("json")))
        page.addWidget(button("일기 Markdown 내보내기", lambda: self.export_diary("markdown")))
        self.settings_status = label("")
        page.addWidget(self.settings_status)
        page.addStretch()

    def show_app_information(self):
        from PySide6.QtWidgets import QDialog, QTabWidget
        dialog = QDialog(self)
        dialog.setWindowTitle(APP_NAME + " · " + APP_VERSION)
        dialog.setStyleSheet(self.styleSheet())
        dialog.resize(400,520)
        layout = QVBoxLayout(dialog)
        tabs = QTabWidget()
        for title,relative in [("설치","docs/INSTALL.md"),("개인정보","docs/PRIVACY.md"),("라이선스","THIRD_PARTY_NOTICES.md"),("MIT","LICENSE")]:
            view = QTextBrowser()
            view.setOpenExternalLinks(True)
            path = ROOT / relative
            view.setMarkdown(path.read_text(encoding="utf-8") if path.is_file() else "문서는 GitHub 저장소에서 확인할 수 있어요.\nhttps://github.com/jyhyun1008/dailyHelpMe")
            tabs.addTab(view,title)
        layout.addWidget(tabs)
        layout.addWidget(button("닫기",dialog.accept))
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.app_information = dialog
        dialog.open()

    def apply_appearance(self, settings):
        self.setStyleSheet(themed_style(STYLE))
        self.brand.setText(settings["name"])
        self.setWindowTitle(APP_NAME + " · " + settings["name"])
        self.memory_heading.setText(settings["name"] + "이(가) 기억하는 나")
        self.input.setAccessibleName(settings["name"] + "에게 보낼 메시지")
        self.appearance_editor.refresh(settings)
        self.diary.apply_theme()
        self.refresh_calendar()
        self.messages.viewport().update()
        self.calendar.grid.update()
        self.update()

    def export_diary(self, format):
        if not self.diary.flush():
            self.show_page(6)
            return
        extension = "json" if format == "json" else "md"
        path, _ = QFileDialog.getSaveFileName(self, "일기 내보내기", f"날도와줘-일기-{now_kst().date().isoformat()}.{extension}", f"일기 (*.{extension})")
        if not path:
            return
        output = QSaveFile(path)
        data = self.store.export_diary(format).encode("utf-8")
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            self.settings_status.setText("파일을 열 수 없어요. 저장 위치를 확인해주세요.")
            return
        if output.write(data) != len(data) or not output.commit():
            self.settings_status.setText("내보내기에 실패했어요. 저장 위치를 확인해주세요.")
            return
        self.settings_status.setText("일기를 내보냈어요.")

    def build_editor(self):
        page = self.page(scroll=True)
        row = QHBoxLayout()
        row.addWidget(button("‹ 돌아가기", self.leave_editor))
        row.addStretch()
        page.addLayout(row)
        self.editor_heading = label("일정 추가", "heading")
        page.addWidget(self.editor_heading)
        self.edit_title = QLineEdit()
        self.edit_title.setPlaceholderText("무슨 일을 할까요?")
        page.addWidget(self.edit_title)
        self.parent_complete = button("1차 일정 완료", self.complete_parent)
        page.addWidget(self.parent_complete)
        self.subtask_editor = SubtaskEditor(self.store)
        self.subtask_editor.changed.connect(self.refresh)
        page.addWidget(self.subtask_editor)
        self.new_subtask_note = label("1차 일정을 저장한 뒤 다시 열면 2차 일정을 나눌 수 있어요.")
        page.addWidget(self.new_subtask_note)
        page.addWidget(label("1차 일정 정보", "section"))
        self.edit_kind = QComboBox()
        for key, title in KINDS.items():
            self.edit_kind.addItem(title, key)
        self.edit_kind.currentIndexChanged.connect(self.update_editor_fields)
        page.addWidget(self.edit_kind)
        self.has_date = QCheckBox("마감일 지정")
        self.has_date.toggled.connect(self.update_editor_fields)
        page.addWidget(self.has_date)
        self.edit_date = QDateEdit()
        self.edit_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.edit_date.setDisplayFormat("yyyy.MM.dd")
        self.edit_date.setAccessibleName("날짜")
        page.addWidget(self.edit_date)
        self.all_day = QCheckBox("시간 지정 안 함")
        self.all_day.toggled.connect(self.update_editor_fields)
        page.addWidget(self.all_day)
        self.edit_time = QTimeEdit()
        self.edit_time.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.edit_time.setDisplayFormat("HH:mm")
        self.edit_time.setAccessibleName("시각")
        page.addWidget(self.edit_time)
        self.days_group = QWidget()
        row = QHBoxLayout(self.days_group)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        self.day_buttons = []
        for name in DAYS:
            day = button(name)
            day.setCheckable(True)
            day.setObjectName("navigation")
            row.addWidget(day)
            self.day_buttons.append(day)
        page.addWidget(self.days_group)
        self.editor_error = label("")
        page.addWidget(self.editor_error)
        self.editor_save = button("저장", self.save_item, True)
        page.addWidget(self.editor_save)
        self.editor_delete = button("삭제", self.delete_item)
        self.editor_delete.setObjectName("danger")
        page.addWidget(self.editor_delete)
        page.addStretch()

    def update_editor_fields(self):
        # Signals can fire while the editor is being built.
        if not hasattr(self, "days_group"):
            return
        kind = self.edit_kind.currentData()
        self.has_date.setVisible(kind == "todo")
        dated = kind == "schedule" or kind == "todo" and self.has_date.isChecked()
        self.edit_date.setVisible(dated)
        self.all_day.setVisible(dated)
        self.edit_time.setVisible(kind == "routine" or dated and not self.all_day.isChecked())
        self.days_group.setVisible(kind == "routine")

    def edit_item(self, item_id=None, kind="schedule"):
        if self.companion.busy and item_id is None:
            return
        self.previous_page = self.tabs.currentIndex() if self.tabs.currentIndex() < 5 else 3
        item = next((item for item in self.store.items() if item["id"] == item_id), None)
        self.edit_id = item_id if item else None
        kind = item["kind"] if item else kind
        self.editor_heading.setText("1차 일정 상세" if item else "새로운 1차 일정")
        self.subtask_editor.set_parent(self.edit_id)
        self.new_subtask_note.setVisible(not item)
        self.parent_complete.setVisible(bool(item))
        if item:
            self.parent_complete.setText("1차 일정 완료 취소" if is_done(item) else "1차 일정 완료")
        self.edit_title.setText(item["title"] if item else "")
        self.edit_kind.setCurrentIndex(self.edit_kind.findData(kind))
        self.has_date.setChecked(bool(item and item["at"]))
        date = QDate.fromString(item["at"][:10], "yyyy-MM-dd") if item and item["at"] else self.calendar.selectedDate() if self.previous_page == 2 else QDate.fromString(now_kst().date().isoformat(), "yyyy-MM-dd")
        self.edit_date.setDate(date)
        time = item["time"] if item and kind == "routine" else item["at"][11:16] if item and item["at"] else "09:00"
        self.edit_time.setTime(QTime.fromString(time, "HH:mm"))
        self.all_day.setChecked(not item or time == ("23:59" if kind == "todo" else "05:01"))
        for index, day in enumerate(self.day_buttons):
            day.setChecked(index in item["days"] if item else True)
        self.editor_error.clear()
        self.confirm_delete = False
        self.editor_delete.setText("삭제")
        self.editor_delete.setVisible(bool(item))
        self.update_editor_fields()
        self.tabs.setCurrentIndex(5)
        self.edit_title.setFocus()

    def complete_parent(self):
        if not self.edit_id or self.companion.busy:
            return
        self.store.toggle_completed(self.edit_id)
        item = next(item for item in self.store.items() if item["id"] == self.edit_id)
        self.parent_complete.setText("1차 일정 완료 취소" if is_done(item) else "1차 일정 완료")
        self.refresh()

    def save_item(self):
        if self.companion.busy:
            return
        kind = self.edit_kind.currentData()
        at = None
        if kind == "schedule" or kind == "todo" and self.has_date.isChecked():
            time = ("23:59" if kind == "todo" else "05:01") if self.all_day.isChecked() else self.edit_time.time().toString("HH:mm")
            at = self.edit_date.date().toString("yyyy-MM-dd") + "T" + time + ":00+09:00"
        operation = {"action": "update" if self.edit_id else "add", "kind": kind, "id": self.edit_id,
                     "title": self.edit_title.text(), "at": at,
                     "days": [i for i, day in enumerate(self.day_buttons) if day.isChecked()] if kind == "routine" else None,
                     "time": self.edit_time.time().toString("HH:mm") if kind == "routine" else None}
        original = next((item for item in self.store.items() if item["id"] == self.edit_id), None)
        if original and original["kind"] != kind:
            self.editor_error.setText("기존 항목의 종류는 바꿀 수 없어요. 새 항목으로 추가해주세요.")
            return
        try:
            self.store.apply_reply({"reply": "기억해뒀어요.", "operations": [operation]})
        except (ValueError, TypeError) as error:
            self.editor_error.setText(str(error))
            return
        self.refresh()
        self.leave_editor()

    def delete_item(self):
        if self.companion.busy or not self.edit_id:
            return
        if not self.confirm_delete:
            self.confirm_delete = True
            self.editor_delete.setText("한 번 더 누르면 삭제돼요")
            return
        self.store.delete(self.edit_id)
        self.refresh()
        self.leave_editor()

    def leave_editor(self):
        self.show_page(self.previous_page)

    def show_page(self, index):
        if index == 2:
            if self.tabs.currentIndex() not in (2, 5):
                self.set_calendar_mode(0)
        self.tabs.setCurrentIndex(index)
        self.page_changed(index)
        if index == 2:
            self.refresh_calendar()

    def page_changed(self, index):
        if hasattr(self, "diary") and index != 6:
            self.diary.flush()
        if index in (0, 1, 2, 3, 4, 6):
            self.settings.setValue("mini/tab", index)
        if hasattr(self, "nav"):
            self.nav.setExclusive(False)
            for entry in self.nav.buttons():
                entry.setChecked(self.nav.id(entry) == index)
            self.nav.setExclusive(True)
        if index == 1 and hasattr(self, "input"):
            self.input.setFocus()

    def keep_on_screen(self):
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        rect = screen.availableGeometry()
        self.move(max(rect.left(), min(self.x(), rect.right() - self.width() + 1)),
                  max(rect.top(), min(self.y(), rect.bottom() - self.height() + 1)))

    def set_transparency(self, value):
        self.setWindowOpacity(1 - value / 100)
        self.transparency_label.setText(f"투명도 {value}%")
        self.settings.setValue("mini/transparency", value)

    def showEvent(self, event):
        super().showEvent(event)
        self.keep_on_screen()
        self.refresh()
        self.settings.setValue("mini/visible", True)
        self.visibility_changed.emit(True)

    def hideEvent(self, event):
        if hasattr(self, "diary"):
            self.diary.flush()
        super().hideEvent(event)
        if not self.shutting_down:
            self.settings.setValue("mini/visible", False)
        self.visibility_changed.emit(False)

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.leave_editor() if self.tabs.currentIndex() == 5 else self.hide()
        else:
            super().keyPressEvent(event)

    def for_date(self, day, items=None):
        date = day.toString("yyyy-MM-dd")
        weekday = day.dayOfWeek() % 7
        return sorted((item for item in (self.store.items() if items is None else items)
                       if item["kind"] == "routine" and weekday in item["days"] or item["at"] and item["at"][:10] == date),
                      key=lambda item: item["time"] or (item["at"][11:16] if item["at"] else ""))

    @staticmethod
    def fill_items(view, empty, items):
        view.set_items(items)
        empty.setVisible(not items)

    def load_older(self):
        self.history_limit += 50
        self.refresh_messages(prepend=True)

    def refresh_messages(self, prepend=False):
        self.messages.set_media(self.store)
        messages = self.store.history(self.history_limit + 1)
        self.more.setVisible(len(messages) > self.history_limit)
        self.messages.set_messages(messages[-self.history_limit:], prepend=prepend)
        self.messages_empty.setVisible(not messages)

    def refresh_calendar(self):
        day = self.calendar.selectedDate()
        items = self.for_date(day)
        self.weekly.set_data(day, self.store.items())
        entry = self.store.diary_entry(day.toString("yyyy-MM-dd"))
        self.calendar_diary.setText("일기 보기" if entry else "일기 쓰기")
        self.calendar_diary.setToolTip(day.toString("yyyy.MM.dd") + " 일기 열기")
        self.calendar_title.setText(f'{day.month()}월 {day.day()}일 {DAYS[day.dayOfWeek() % 7]}요일  ·  {len(items)}개')
        self.fill_items(self.calendar_list, self.calendar_empty, items)

    def mark_calendar(self):
        first = QDate(self.calendar.yearShown(), self.calendar.monthShown(), 1)
        date = first.addDays(-(first.dayOfWeek() % 7))
        marks = {}
        items = self.store.items()
        for index in range(42):
            day = date.addDays(index)
            colors = list(dict.fromkeys(COLORS[item["kind"]] for item in self.for_date(day, items) if not item["done"]))
            if colors:
                marks[day.toString("yyyy-MM-dd")] = colors
        self.calendar.set_marks(marks)

    def refresh_tasks(self):
        if not hasattr(self, "tasks"):
            return
        items = [item for item in self.store.items() if (not self.filter.currentData() or self.filter.currentData() == item["kind"]) and (self.show_done.isChecked() or not is_done(item))]
        self.fill_items(self.tasks, self.tasks_empty, items)

    def refresh(self):
        if self.edit_id and self.tabs.currentIndex() == 5:
            current = next((item for item in self.store.items() if item["id"] == self.edit_id), None)
            if current:
                self.parent_complete.setText("1차 일정 완료 취소" if is_done(current) else "1차 일정 완료")
                self.subtask_editor.refresh()
            else:
                self.leave_editor()
        self.diary.load()
        self.diary.refresh_bookmarks()
        self.diary.refresh_list()
        now = now_kst()
        day = QDate(now.year, now.month, now.day)
        self.today_title.setText(f'{now.month}월 {now.day}일 {DAYS[day.dayOfWeek() % 7]}요일')
        items = today_items(self.store.items(), day.toString("yyyy-MM-dd"))
        remaining = sum(not is_done(item, now) for item in items)
        self.today_count.setText(f"남은 일정 {remaining}개" if items else "조금 여유로운 하루")
        self.fill_items(self.today, self.today_empty, items)
        self.refresh_messages()
        self.refresh_calendar()
        self.refresh_tasks()
        self.mark_calendar()
        if not self.profile.document().isModified():
            self.profile.setPlainText(self.store.get("profile"))
            self.profile.document().setModified(False)

    def set_busy(self, busy):
        self.diary.draft_button.setEnabled(not busy)
        self.parent_complete.setEnabled(not busy)
        self.send_button.setEnabled(not busy)
        self.input.setEnabled(not busy)
        for control in (self.today_add, self.calendar_add, self.task_add, self.editor_save, self.editor_delete, self.profile_save, self.login_button):
            control.setEnabled(not busy)
        for view in (self.today, self.tasks, self.calendar_list):
            view.editable = not busy
        self.retry_button.setEnabled(not busy)

    def set_status(self, text, error=False):
        self.chat_status.setText(text)
        self.chat_status.setVisible(bool(text))
        self.retry_button.setVisible(error)
