"""Local appearance settings with a portable, sanitized copy of the chosen image."""
import base64
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QImageReader, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QColorDialog, QCheckBox
from appearance import DEFAULT_NAME, DEFAULT_COLOR


class AppearanceEditor(QWidget):
    def __init__(self, companion):
        super().__init__()
        self.companion = companion
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel('이름 · 테마 · 이미지')
        heading.setObjectName('section')
        layout.addWidget(heading)
        self.name = QLineEdit()
        self.name.setMaxLength(30)
        self.name.setPlaceholderText('챗봇 이름')
        self.name.setAccessibleName('챗봇 이름')
        layout.addWidget(self.name)
        row = QHBoxLayout()
        self.color = QLineEdit()
        self.color.setMaxLength(7)
        self.color.setAccessibleName('테마색 HEX')
        choose = QPushButton('색 고르기')
        choose.clicked.connect(self.choose_color)
        row.addWidget(self.color, 1)
        row.addWidget(choose)
        layout.addLayout(row)
        save = QPushButton('이름 · 테마 적용')
        save.setObjectName('primary')
        save.clicked.connect(self.save)
        layout.addWidget(save)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedHeight(80)
        layout.addWidget(self.preview)
        row = QHBoxLayout()
        for text, action in [('정지 이미지 선택', self.choose_image), ('기본 이미지', lambda: self.save(avatar=''))]:
            b = QPushButton(text)
            b.clicked.connect(action)
            row.addWidget(b)
        layout.addLayout(row)
        self.frame_previews = {}
        for frame, title in [('left', '왼손 내림'), ('right', '오른손 내림')]:
            row = QHBoxLayout()
            thumbnail = QLabel()
            thumbnail.setFixedSize(64, 48)
            self.frame_previews[frame] = thumbnail
            row.addWidget(thumbnail)
            button = QPushButton(title + ' 선택')
            button.clicked.connect(lambda checked=False, slot=frame: self.choose_image(frame=slot))
            row.addWidget(button)
            clear = QPushButton('해제')
            clear.clicked.connect(lambda checked=False, slot=frame: self.save(avatar='', avatar_frame=slot))
            row.addWidget(clear)
            layout.addLayout(row)
        reset = QPushButton('꾸미기 전체 기본값')
        reset.clicked.connect(self.reset)
        layout.addWidget(reset)
        self.keyboard = QCheckBox('키보드 입력에 펫 반응')
        self.keyboard.setChecked(companion.store.get('keyboard_reaction', '1') == '1')
        self.keyboard.toggled.connect(self.toggle_keyboard)
        layout.addWidget(self.keyboard)
        note = QLabel('정지 → 왼손 내림 → 오른손 내림 이미지를 등록하면 키 입력과 AI 답장 중에 움직여요. 같은 크기·위치의 투명 PNG를 권장해요. 키보드가 이미지에 포함되면 함께 늘어나요. 정지 이미지를 바꾸면 손 이미지는 초기화돼요. 입력한 글자는 읽거나 저장하지 않으며, 움직임 줄이기를 켜면 멈춰요.')
        note.setObjectName('muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        self.status.setObjectName('muted')
        layout.addWidget(self.status)

    def refresh(self, settings):
        self.name.setText(settings['name'])
        self.color.setText(settings['color'])
        self.preview.setPixmap(self.companion.pet.image.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        for slot, label in self.frame_previews.items():
            raw = self.companion.store.get('avatar_' + slot + '_png')
            pixmap = QPixmap()
            if raw:
                pixmap.loadFromData(base64.b64decode(raw))
            label.setPixmap(pixmap.scaled(64, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)) if not pixmap.isNull() else label.clear()

    def toggle_keyboard(self, enabled):
        self.companion.store.set('keyboard_reaction', '1' if enabled else '0')
        self.companion.pet.keyboard.set_enabled(enabled)
        self.companion.pet.typing_frame = 0
        self.companion.pet.update()

    def save(self, checked=False, avatar=None, avatar_frame='idle'):
        try:
            self.companion.save_appearance(self.name.text(), self.color.text(), avatar=avatar, avatar_frame=avatar_frame)
        except ValueError as error:
            self.status.setText(str(error))
            return False
        self.status.setText('적용했어요. 다음 실행에도 유지돼요.')
        return True

    def choose_color(self):
        selected = QColorDialog.getColor(QColor(self.color.text()), self, '테마색 선택')
        if selected.isValid():
            self.color.setText(selected.name())

    def choose_image(self, checked=False, frame='idle'):
        path, _ = QFileDialog.getOpenFileName(self, '챗봇 이미지 선택', '', '이미지 (*.png *.jpg *.jpeg *.webp)')
        if path:
            self.import_image(path, frame=frame)

    def import_image(self, path, frame='idle'):
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        if not size.isValid() or size.width()*size.height() > 40000000:
            self.status.setText('지원하지 않거나 너무 큰 이미지예요. 4천만 화소 이하의 이미지를 선택해주세요.')
            return False
        reader.setScaledSize(size.scaled(1024, 1024, Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            self.status.setText('이미지를 읽지 못했어요. PNG, JPG, WEBP 파일을 선택해주세요.')
            return False
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, 'PNG'):
            self.status.setText('이미지를 저장하지 못했어요.')
            return False
        return self.save(avatar=base64.b64encode(bytes(data)).decode('ascii'), avatar_frame=frame)

    def reset(self):
        self.name.setText(DEFAULT_NAME)
        self.color.setText(DEFAULT_COLOR)
        self.save(avatar='')
