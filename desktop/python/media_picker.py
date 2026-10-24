"""Registration and reusable emoji/sticker palette for the native drawer."""
from pathlib import Path
from PySide6.QtCore import QEasingCurve, QSize, QVariantAnimation, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QWidget, QScrollArea, QPushButton, QLabel, QLineEdit, QComboBox, QFileDialog, QSizePolicy
from chat_media import normalize_image, artwork_movie
from appearance import style


class ArtworkButton(QPushButton):
    def __init__(self, asset, png, callback):
        super().__init__()
        image = QPixmap();image.loadFromData(png)
        self.setIcon(QIcon(image))
        self.movie = artwork_movie(png, self, lambda frame: self.setIcon(QIcon(frame)))
        self.base_size = 34 if asset['kind']=='emoji' else 54
        self.setIconSize(QSize(self.base_size,self.base_size))
        self.setFixedSize(72,72)
        self.setToolTip(asset['name'])
        self.setAccessibleName(asset['name'])
        self.clicked.connect(callback)
        self.bounce = QVariantAnimation(self)
        self.bounce.setDuration(260)
        self.bounce.setEasingCurve(QEasingCurve.Type.OutBack)
        self.bounce.valueChanged.connect(lambda value:self.setIconSize(QSize(int(value),int(value))))

    def animate(self, hover):
        self.bounce.stop()
        self.bounce.setStartValue(self.iconSize().width())
        self.bounce.setEndValue(self.base_size*(1.08 if hover else 1))
        self.bounce.start()

    def enterEvent(self,event):
        self.animate(True)
        super().enterEvent(event)

    def leaveEvent(self,event):
        self.animate(False)
        super().leaveEvent(event)


class MediaPicker(QDialog):
    def __init__(self, companion, parent):
        super().__init__(parent)
        self.companion = companion
        self.store = companion.store
        self.setWindowTitle('이모지 · 스티커')
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setStyleSheet(style(parent.styleSheet()+"""
QDialog { background: #fffafd; }
QTabWidget::pane { border: 0; background: #fffafd; }
QTabBar::tab { background: #f8ecf2; border: 0; border-radius: 10px; padding: 9px 18px; margin: 2px; }
QTabBar::tab:selected { background: #d64289; color: white; }
QScrollArea { border: 0; background: #fffafd; }
QScrollArea > QWidget > QWidget { background: #fffafd; }
"""))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(390,460)
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs,1)
        row = QHBoxLayout()
        self.kind = QComboBox()
        self.kind.addItem('이모지','emoji');self.kind.addItem('스티커','sticker')
        self.name = QLineEdit();self.name.setMaxLength(40);self.name.setPlaceholderText('이미지 이름')
        row.addWidget(self.kind);row.addWidget(self.name,1)
        layout.addLayout(row)
        register = QPushButton('이미지 선택해서 등록')
        register.clicked.connect(self.choose)
        layout.addWidget(register)
        self.status = QLabel('이모지는 글 사이에 삽입 · 스티커는 AI 답장 없이 바로 전송')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parentWidget()
        anchor = parent.frameGeometry()
        bounds = parent.screen().availableGeometry()
        frame = self.frameGeometry()
        gap = 12
        right = anchor.right() + gap
        left = anchor.left() - frame.width() - gap
        x = right if right + frame.width() <= bounds.right() + 1 else left
        x = max(bounds.left(), min(x, bounds.right() - frame.width() + 1))
        y = max(bounds.top(), min(anchor.top(), bounds.bottom() - frame.height() + 1))
        self.move(self.pos() + type(self.pos())(x - frame.x(), y - frame.y()))
        self.raise_()
        self.activateWindow()

    def rename(self, key, field):
        try:
            self.store.rename_media(key, field.text())
        except ValueError as error:
            self.status.setText(str(error))
            current = next((asset for asset in self.store.media_assets() if asset['id'] == key), None)
            if current: field.setText(current['name'])
            return
        field.setText(field.text().strip())
        self.status.setText('이름을 저장했어요.')

    def refresh(self):
        selected = self.tabs.currentIndex()
        while self.tabs.count():
            widget=self.tabs.widget(0);self.tabs.removeTab(0);widget.deleteLater()
        assets = self.store.media_assets()
        for kind,title in [('emoji','이모지'),('sticker','스티커')]:
            scroll=QScrollArea();scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            body=QWidget();grid=QGridLayout(body);grid.setAlignment(Qt.AlignmentFlag.AlignTop)
            entries=[a for a in assets if a['kind']==kind]
            for col in range(3):grid.setColumnStretch(col,1)
            if not entries:
                grid.addWidget(QLabel('아래에서 나만의 이미지를 등록해보세요.'),0,0,1,3)
            for index,asset in enumerate(entries):
                tile=QWidget();tile.setMinimumWidth(0);tile.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);column=QVBoxLayout(tile);column.setContentsMargins(2,2,2,2)
                image=ArtworkButton(asset,self.store.media_image(asset['id']),lambda checked=False,a=asset:self.select(a))
                column.addWidget(image,0,Qt.AlignmentFlag.AlignCenter)
                name=QLineEdit(asset['name']);name.setMaxLength(40)
                name.setMinimumWidth(0);name.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
                name.setAlignment(Qt.AlignmentFlag.AlignCenter);name.setAccessibleName('이름 수정')
                name.setToolTip('이름을 수정하고 Enter를 누르면 저장해요.')
                name.editingFinished.connect(lambda key=asset['id'],field=name:self.rename(key,field))
                column.addWidget(name)
                remove=QPushButton('삭제');remove.setAccessibleName(asset['name']+' 선택 목록에서 삭제')
                remove.clicked.connect(lambda checked=False,key=asset['id']:self.remove(key))
                column.addWidget(remove)
                grid.addWidget(tile,index//3,index%3)
            scroll.setWidget(body);self.tabs.addTab(scroll,title)
        self.tabs.setCurrentIndex(max(0,selected))

    def remove(self,key):
        self.store.archive_media(key)
        self.refresh()
        self.status.setText('선택 목록에서 삭제했어요. 지난 대화의 이미지는 유지돼요.')

    def select(self,asset):
        if asset['kind']=='emoji':
            if self.companion.busy:
                self.status.setText('답장을 받은 뒤 이모지를 넣어주세요.');return
            self.companion.panel.input.insert_emoji(asset['id'],self.store.media_image(asset['id']))
            self.companion.panel.input.setFocus()
        else:
            self.companion.send_sticker(asset['id'])
        self.accept()

    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,'이모지 · 스티커 이미지','','이미지 (*.png *.jpg *.jpeg *.webp *.gif)')
        if not path:return
        try:
            if Path(path).stat().st_size>4*1024*1024:raise ValueError('이미지는 4MB 이하로 선택해주세요.')
            self.store.add_media(self.kind.currentData(),self.name.text().strip() or Path(path).stem[:40],normalize_image(Path(path).read_bytes()))
        except (ValueError,OSError) as error:
            self.status.setText(str(error));return
        self.refresh();self.name.clear()
        self.tabs.setCurrentIndex(0 if self.kind.currentData()=='emoji' else 1)
        self.status.setText('등록했어요. 이미지를 눌러 사용해보세요.')
