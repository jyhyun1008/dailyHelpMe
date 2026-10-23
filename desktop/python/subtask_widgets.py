"""Manual steps within an existing first-level item; no AI operations."""
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox


class SubtaskEditor(QWidget):
    changed = Signal()

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.parent_id = None
        self.snapshot = None
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)
        self.heading = QLabel('2차 일정')
        self.heading.setObjectName('section')
        self.layout.addWidget(self.heading)
        self.note = QLabel('작은 단계로 나눠보세요. 변경은 바로 저장돼요. 모두 체크해도 1차 일정은 직접 완료해야 해요.')
        self.note.setWordWrap(True)
        self.note.setObjectName('muted')
        self.layout.addWidget(self.note)
        self.rows = QVBoxLayout()
        self.layout.addLayout(self.rows)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText('예: 작업을 위해 컴퓨터 켜기')
        self.input.setMaxLength(500)
        self.input.returnPressed.connect(self.add)
        self.add_button = QPushButton('＋')
        self.add_button.setAccessibleName('2차 일정 추가')
        self.add_button.clicked.connect(self.add)
        row.addWidget(self.input, 1)
        row.addWidget(self.add_button)
        self.layout.addLayout(row)
        self.status = QLabel('')
        self.status.setObjectName('muted')
        self.status.setWordWrap(True)
        self.layout.addWidget(self.status)

    def set_parent(self, parent_id):
        if self.parent_id != parent_id:
            self.input.clear()
            self.status.clear()
            self.snapshot = None
        self.parent_id = parent_id
        self.setVisible(bool(parent_id))
        if parent_id:
            self.refresh()

    def perform(self, action, id=None, title=None, direction=None):
        try:
            self.store.change_subtask(self.parent_id, action, subtask_id=id, title=title, direction=direction)
        except ValueError as error:
            self.status.setText(str(error))
            return False
        self.status.clear()
        if action == 'update':
            # A focus-out title save must not destroy a checkbox being clicked.
            self.snapshot = self.store.subtasks(self.parent_id)
        else:
            self.refresh()
        self.changed.emit()
        return True

    def add(self):
        if self.perform('add', title=self.input.text()):
            self.input.clear()
            self.input.setFocus()

    def refresh(self):
        if not self.parent_id:
            return
        items = self.store.subtasks(self.parent_id)
        if items == self.snapshot:
            return
        self.snapshot = items
        self.heading.setText(f'2차 일정 · {sum(item["done"] for item in items)}/{len(items)}')
        while self.rows.count():
            self.rows.takeAt(0).widget().deleteLater()
        for item in items:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(5)
            check = QCheckBox()
            check.setChecked(bool(item['done']))
            check.setAccessibleName(item['title'] + ' 완료')
            check.clicked.connect(lambda checked=False, key=item['id']: self.perform('toggle', key))
            title = QLineEdit(item['title'])
            title.setMaxLength(500)
            title.setAccessibleName('2차 일정 제목')
            # Commit on Return or focus change; sibling controls keep the row alive until then.
            title.editingFinished.connect(lambda field=title, key=item['id'], original=item['title']: self.perform('update', key, field.text()) if field.text() != original else None)
            layout.addWidget(check)
            layout.addWidget(title, 1)
            for text, action, direction in [('↑', 'move', -1), ('↓', 'move', 1), ('×', 'delete', None)]:
                b = QPushButton(text)
                b.setFixedWidth(25)
                b.setStyleSheet('padding: 6px 2px;')
                b.setAccessibleName({'↑':'위로 이동', '↓':'아래로 이동', '×':'2차 일정 삭제'}[text])
                b.clicked.connect(lambda checked=False, key=item['id'], a=action, d=direction: self.perform(a, key, direction=d))
                layout.addWidget(b)
            self.rows.addWidget(row)
