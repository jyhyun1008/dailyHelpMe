from __future__ import annotations

import math
import time
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QLockFile, QPoint, QRect, QSettings, Qt, QThread, QTimer, Signal, QProcess
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap, QRegion
from PySide6.QtWidgets import QApplication, QLabel, QSystemTrayIcon, QWidget

from engine import codex_binary, request_reply
from native_windows import configure_pet_window
from store import Store
from drawer import Drawer
from appearance import read_appearance, validate, style as themed_style, current
from bongo_pet import load_frames, draw_bongo, preview as bongo_preview
from keyboard_activity import KeyboardActivity
from pet_bubble import PetBubble
from menus import RoundedMenu
from mobile_server import MobileService
from typography import initialize_typography
from branding import APP_NAME, APP_ICON

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
DEFAULT_DATA = Path.home() / "Library/Application Support/DOA Pet"
DATA = Path(os.environ.get("DOA_DATA_DIR", DEFAULT_DATA)).expanduser()


class ReplyWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, context):
        super().__init__()
        self.context = context

    def run(self):
        try:
            self.succeeded.emit(request_reply(self.context))
        except Exception as error:
            self.failed.emit(str(error))


class Pet(QWidget):
    clicked = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.resize(320, 280)
        self.avatar = QRect(80, 110, 160, 160)
        custom = os.environ.get("DOA_PET_IMAGE")
        self.custom = bool(custom)
        self.bongo_frames = load_frames()
        self.bongo = not self.custom
        self.typing_frame = 0
        self.custom_frames = []
        self.reply_typing = False
        self.frame_changed_at = float("-inf")
        self.last_tap = float("-inf")
        self.image = QPixmap(custom) if custom else bongo_preview(self.bongo_frames)
        self.phase, self.offset = 0.0, 0
        self.press, self.dragged = None, False
        self.bubble = PetBubble(self)
        self.settings = QSettings("Cybermaid", "DOAPet")
        saved = self.settings.value("position")
        if isinstance(saved, QPoint) and any(screen.availableGeometry().contains(saved + QPoint(160, 180)) for screen in QApplication.screens()):
            self.move(saved)
        else:
            self.reset_position()
        self.motion = QTimer(self)
        self.motion.timeout.connect(self.animate)
        self.motion.start(33)
        self.hide_bubble = QTimer(self)
        self.hide_bubble.setSingleShot(True)
        self.hide_bubble.timeout.connect(self.clear_bubble)
        self.keyboard = KeyboardActivity()
        self.keyboard.tapped.connect(self.on_key_activity)
        self.update_mask()
        self.setToolTip("클릭해서 작은 서랍 · 드래그해서 이동 · 우클릭 메뉴")

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.ensure_front)

    def ensure_front(self):
        if self.isVisible():
            configure_pet_window(self)

    def reset_position(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 20, screen.bottom() - self.height() - 20)

    def update_mask(self):
        # Restrict input to the visible pet and bubble; empty surroundings pass through.
        region = QRect(20, 97, 280, 170) if self.bongo else self.avatar
        shape = QRegion(region, QRegion.RegionType.Rectangle)
        if self.bubble.isVisible() or not self.isVisible():
            shape |= QRegion(self.bubble.geometry())
        self.setMask(shape)

    def say(self, text):
        self.bubble.setText(text)
        self.bubble.show()
        self.hide_bubble.start(25000)
        self.update_mask()

    def clear_bubble(self):
        self.bubble.hide()
        self.update_mask()

    def on_key_activity(self):
        if (self.bongo or self.custom_frames) and not self.settings.value("reduce_motion", False, type=bool):
            self.last_tap = time.monotonic()
            if not self.reply_typing:
                self.advance_typing_frame(self.last_tap)

    def advance_typing_frame(self, now):
        self.typing_frame = 2 if self.typing_frame == 1 else 1
        self.frame_changed_at = now
        self.update()

    def set_reply_typing(self, active):
        self.reply_typing = active
        if active and (self.bongo or self.custom_frames) and not self.settings.value("reduce_motion", False, type=bool):
            self.advance_typing_frame(time.monotonic())
        elif not active:
            self.typing_frame = 0
            self.update()

    def animate(self):
        self.keyboard.poll()
        now = time.monotonic()
        reduced = self.settings.value("reduce_motion", False, type=bool)
        if self.reply_typing and (self.bongo or self.custom_frames) and not reduced and now - self.frame_changed_at >= .24:
            self.advance_typing_frame(now)
        if self.typing_frame and (reduced or not self.reply_typing and now - self.last_tap > .18):
            self.typing_frame = 0
            self.update()
        if self.isVisible() and not self.settings.value("reduce_motion", False, type=bool):
            self.phase += 0.065
            self.offset = round(math.sin(self.phase) * 4)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        elapsed = time.monotonic() - self.frame_changed_at
        squash = 0.0
        if not self.settings.value("reduce_motion", False, type=bool) and elapsed < .4:
            squash = .12 * math.exp(-10 * elapsed) * math.cos(27 * elapsed)
        if self.bongo:
            draw_bongo(painter, QRect(35, 112, 250, 150), self.bongo_frames, self.typing_frame, squash)
            return
        rect = self.avatar.adjusted(5, 6 + self.offset, -5, -6 + self.offset)
        if self.image.isNull():
            painter.setBrush(QColor("#fadce8"))
            painter.drawEllipse(rect)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, current()["name"])
        else:
            image = self.custom_frames[self.typing_frame] if self.custom_frames else self.image
            if self.custom_frames:
                painter.translate(rect.center().x(), rect.bottom())
                painter.scale(1 + squash, 1 - squash)
                painter.translate(-rect.center().x(), -rect.bottom())
            scaled = image.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x = rect.x() + (rect.width() - scaled.width()) // 2
            y = rect.y() + (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press = event.globalPosition().toPoint() - self.pos()
            self.dragged = False

    def mouseMoveEvent(self, event):
        if self.press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            target = event.globalPosition().toPoint() - self.press
            if (target - self.pos()).manhattanLength() > 3:
                self.dragged = True
            self.move(target)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.press is not None:
            if not self.dragged:
                self.clicked.emit()
            self.settings.setValue("position", self.pos())
            self.press = None

    def contextMenuEvent(self, event):
        self.menu.exec(event.globalPos())


class Companion(QObject):
    """Own the pet, drawer and background requests; there is no second application window."""
    def __init__(self, store):
        super().__init__()
        initialize_typography()
        self.store = store
        self.worker = None
        self.diary_draft = None
        self.diary_draft_status = ""
        self.retry_available = False
        self.login_process = None
        self.mobile_reply_error = ""
        QApplication.instance().setProperty("doa_appearance", read_appearance(store))
        self.pet = Pet()
        self.mobile = MobileService(self)
        self.panel = Drawer(self)
        self.configure_mobile(self.store.get("mobile_enabled") == "1")
        self.pet.clicked.connect(self.toggle_panel)
        self.make_menu()
        self.apply_appearance()
        QApplication.instance().applicationStateChanged.connect(self.application_state_changed)
        self.pet.show()
        self.panel.setVisible(self.pet.settings.value("mini/visible", True, type=bool))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(15000)

    @property
    def busy(self):
        return bool(self.worker and self.worker.isRunning())

    def apply_appearance(self):
        import base64
        settings = read_appearance(self.store)
        QApplication.instance().setProperty("doa_appearance", settings)
        self.pet.bubble.apply_theme()
        raw = self.store.get("avatar_png")
        pixmap = QPixmap()
        if raw:
            pixmap.loadFromData(base64.b64decode(raw))
        custom = os.environ.get("DOA_PET_IMAGE")
        self.pet.custom = bool(raw or custom)
        self.pet.bongo = not self.pet.custom
        self.pet.typing_frame = 0
        self.pet.image = pixmap if raw and not pixmap.isNull() else QPixmap(custom) if custom else bongo_preview(self.pet.bongo_frames)
        self.pet.custom_frames = []
        if raw and not pixmap.isNull():
            frames = [pixmap]
            has_motion = False
            for key in ("avatar_left_png", "avatar_right_png"):
                frame = QPixmap()
                encoded = self.store.get(key)
                if encoded:
                    frame.loadFromData(base64.b64decode(encoded))
                has_motion |= not frame.isNull()
                frames.append(frame if not frame.isNull() else pixmap)
            if has_motion:
                self.pet.custom_frames = frames
        self.pet.keyboard.set_enabled(self.store.get("keyboard_reaction", "1") == "1")
        self.pet.update_mask()
        self.pet.update()
        self.panel.apply_appearance(settings)
        self.tray.setToolTip(APP_NAME + " · " + settings["name"])
        self.tray.setIcon(QIcon(str(APP_ICON)))
        self.pet.menu.setStyleSheet(themed_style(self.pet.menu.base_style))
        self.pet.menu.actions()[1].setText(settings["name"] + "과(와) 대화")
        self.pet.menu.update()

    def save_appearance(self, name, color, avatar=None, avatar_frame="idle"):
        name, color = validate(name, color)
        keys = {"idle": "avatar_png", "left": "avatar_left_png", "right": "avatar_right_png"}
        if avatar_frame not in keys:
            raise ValueError("이미지 상태를 확인해주세요.")
        if avatar is not None and avatar_frame != "idle" and not self.store.get("avatar_png"):
            raise ValueError("정지 이미지를 먼저 등록해주세요.")
        with self.store.db:
            self.store._set("companion_name", name)
            self.store._set("theme_color", color)
            if avatar is not None:
                self.store._set(keys[avatar_frame], avatar)
                if avatar_frame == "idle":
                    self.store._set("avatar_left_png", "")
                    self.store._set("avatar_right_png", "")
        self.apply_appearance()

    def application_state_changed(self, state):
        self.pet.ensure_front()

    def make_menu(self):
        menu = RoundedMenu()
        self.panel_action = QAction("서랍 보이기", self)
        self.panel_action.setCheckable(True)
        self.panel_action.triggered.connect(lambda checked: self.panel.setVisible(checked))
        self.panel.visibility_changed.connect(self.panel_action.setChecked)
        menu.addAction(self.panel_action)
        for text, callback in [(current()["name"] + "과(와) 대화", self.open_chat), ("설정", lambda: self.open_page(4)),
                               ("펫 보이기 / 숨기기", self.toggle_pet), ("펫 위치 초기화", self.pet.reset_position), ("종료", self.quit)]:
            action = QAction(text, self)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.pet.menu = menu
        self.tray = QSystemTrayIcon(QIcon(str(APP_ICON)), self)
        self.tray.setToolTip(APP_NAME + " · " + current()["name"])
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.messageClicked.connect(self.open_chat)
        self.tray.show()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_panel()

    def open_page(self, index):
        self.panel.show_page(index)
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def open_chat(self):
        self.open_page(1)

    def toggle_panel(self):
        self.panel.setVisible(not self.panel.isVisible())
        if self.panel.isVisible():
            self.panel.raise_()

    def toggle_pet(self):
        self.pet.setVisible(not self.pet.isVisible())

    def quit(self):
        if not self.panel.diary.flush():
            self.panel.show_page(6)
            self.panel.show()
            return
        if self.busy:
            self.panel.set_status("답장을 받은 뒤 종료해주세요.")
            self.open_chat()
            return
        if self.login_process and self.login_process.state() != QProcess.ProcessState.NotRunning:
            self.login_process.kill()
            self.login_process.waitForFinished(3000)
        self.panel.shutting_down = True
        self.pet.keyboard.close()
        self.mobile.close()
        self.pet.settings.sync()
        self.store.db.close()
        QApplication.quit()

    def login(self):
        if self.busy or self.login_process and self.login_process.state() != QProcess.ProcessState.NotRunning:
            return
        try:
            binary = codex_binary()
        except RuntimeError as error:
            self.panel.connection.setText(str(error))
            return
        self.panel.login_output.setPlainText("브라우저에서 ChatGPT 로그인을 완료해주세요.")
        self.panel.login_output.show()
        self.login_process = QProcess(self)
        self.login_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.login_process.readyReadStandardOutput.connect(self.read_login)
        self.login_process.finished.connect(self.login_finished)
        self.login_process.errorOccurred.connect(lambda _: self.panel.connection.setText("로그인을 시작하지 못했어요. 터미널에서 codex login을 실행해주세요."))
        self.login_process.start(binary, ["login"])

    def read_login(self):
        text = bytes(self.login_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.panel.login_output.setPlainText(self.panel.login_output.toPlainText() + text)

    def login_finished(self, code, status):
        self.panel.connection.setText("로그인 완료! 대화해보세요." if code == 0 else "로그인을 완료하지 못했어요. 다시 시도해주세요.")
        if code == 0:
            self.panel.login_output.clear()
            self.panel.login_output.hide()

    def send(self):
        text = self.panel.input.message_text().strip()
        if not text or self.busy:
            return
        self.panel.input.clear()
        self.send_text(text)

    def send_text(self, text):
        if self.busy:
            return False
        self.retry_available = True
        self.mobile_reply_error = ""
        self.store.message("user", text.strip())
        self.panel.refresh_messages()
        self.start_reply()
        return True

    def send_sticker(self, asset_id):
        self.store.send_sticker(asset_id)
        self.panel.refresh_messages()
        return True

    def retry(self):
        if self.retry_available and not self.busy:
            self.start_reply()

    def start_reply(self):
        self.mobile_reply_error = ""
        self.panel.set_status(current()["name"] + "이(가) 답장을 생각하고 있어요…")
        self.pet.say("답장을 생각하고 있어요…")
        self.panel.set_busy(True)
        context = self.store.context()
        context["current_request"] = next((m["content"] for m in reversed(context["history"]) if m["role"] == "user"), "")
        self.worker = ReplyWorker(context)
        self.worker.succeeded.connect(self.receive)
        self.worker.failed.connect(self.failure)
        self.worker.finished.connect(self.finished)
        self.pet.set_reply_typing(True)
        self.worker.start()

    def generate_diary_draft(self, day):
        if self.busy:
            raise ValueError("AI 작업이 끝난 뒤 초안을 요청해주세요.")
        if not self.panel.diary.flush():
            raise ValueError("작성 중인 일기를 먼저 저장해주세요.")
        context = self.store.diary_draft_context(day)
        self.diary_draft = None
        self.diary_draft_status = "대화를 바탕으로 일기 초안을 쓰고 있어요…"
        original = self.store.diary_entry(day)
        self.panel.set_busy(True)
        self.panel.diary.refresh_draft()
        self.worker = ReplyWorker(context)
        self.worker.succeeded.connect(lambda result: self.receive_diary_draft(day, original, result))
        self.worker.failed.connect(self.diary_draft_failure)
        self.worker.finished.connect(self.finished)
        self.pet.set_reply_typing(True)
        self.worker.start()

    def receive_diary_draft(self, day, original, result):
        content = result.get("reply") if isinstance(result, dict) else None
        if not isinstance(content, str) or not content.strip() or len(content) > 30000:
            self.diary_draft_failure("초안 형식을 읽지 못했어요. 다시 요청해주세요.")
            return
        self.diary_draft = {"date": day, "content": content.strip(), "original": original}
        self.diary_draft_status = "초안을 확인하고 적용해주세요."
        self.panel.diary.refresh_draft()

    def diary_draft_failure(self, message):
        self.diary_draft_status = message
        self.panel.diary.refresh_draft()

    def apply_diary_draft(self):
        draft = self.diary_draft
        if not draft:
            raise ValueError("적용할 초안이 없어요.")
        if not self.panel.diary.flush():
            raise ValueError("작성 중인 일기를 먼저 저장해주세요.")
        current = self.store.diary_entry(draft["date"])
        if current != draft["original"]:
            raise ValueError("초안을 요청한 뒤 일기가 변경됐어요. 초안을 복사해서 원하는 부분에 붙여넣거나 다시 요청해주세요.")
        self.store.save_diary(draft["date"], current["title"] if current else "", draft["content"])
        self.diary_draft = None
        self.diary_draft_status = "초안을 일기에 적용했어요."
        self.panel.diary.load()
        self.panel.diary.refresh_draft()

    def dismiss_diary_draft(self):
        self.diary_draft = None
        self.diary_draft_status = ""
        self.panel.diary.refresh_draft()

    def receive(self, result):
        try:
            text = self.store.apply_reply(result, link_created=True)
        except (ValueError, TypeError) as error:
            self.failure(str(error))
            return
        self.retry_available = False
        self.pet.say(text)
        self.mobile.notify([text])
        self.panel.set_status("")
        self.panel.refresh()

    def failure(self, message):
        self.mobile_reply_error = message
        self.panel.set_status(message, error=True)
        self.pet.say("연결을 확인해주세요. 서랍에 자세히 적어뒀어요.")

    def finished(self):
        self.pet.set_reply_typing(False)
        self.panel.set_busy(False)
        self.panel.retry_button.setVisible(self.retry_available)
        if self.panel.tabs.currentIndex() == 1:
            self.panel.input.setFocus()

    def tick(self):
        texts = self.store.reminders()
        if texts:
            self.mobile.notify(texts)
            self.pet.say(texts[-1])
            if not self.panel.isVisible():
                self.tray.showMessage(current()["name"], "\n".join(texts), QSystemTrayIcon.MessageIcon.Information, 10000)
        self.panel.refresh()

    def confirm_message(self, message_id):
        self.store.confirm(message_id)
        self.panel.refresh_messages()

    def toggle_bookmark(self, message_id):
        self.store.toggle_bookmark(message_id)
        self.panel.refresh_messages()
        self.panel.diary.refresh_bookmarks()

    def toggle_item(self, item_id):
        if not self.busy:
            self.store.toggle_completed(item_id)
            self.panel.refresh()

    def save_profile(self):
        if self.busy:
            return
        self.store.set("profile", self.panel.profile.toPlainText())
        self.panel.profile.document().setModified(False)
        self.panel.settings_status.setText("기억을 저장했어요.")

    def configure_mobile(self, enabled):
        success = self.mobile.enable(enabled)
        self.panel.mobile_enabled.blockSignals(True)
        self.panel.mobile_enabled.setChecked(bool(enabled and success))
        self.panel.mobile_enabled.blockSignals(False)
        self.panel.mobile_status.setText(self.mobile.last_error or ("맥의 모바일 서버가 켜졌어요 · 127.0.0.1:8765" if enabled else "모바일 서버가 꺼져 있어요."))

    def reset_mobile_pairing(self):
        import secrets
        with self.store.db:
            self.store._set("mobile_pairing", secrets.token_hex(8))
            self.store.db.execute("DELETE FROM mobile_sessions")
            self.store.db.execute("DELETE FROM mobile_push")
        self.panel.mobile_code.setText(self.mobile.pairing_code)
        self.panel.mobile_status.setText("연결 코드를 바꿨어요. 각 기기에서 다시 연결하고 알림을 켜주세요.")

    def dispose(self):
        """Release top-level widgets without changing the saved visible preference."""
        self.timer.stop()
        self.mobile.close()
        self.panel.shutting_down = True
        self.panel.hide()
        self.pet.keyboard.close()
        self.pet.motion.stop()
        self.pet.hide()
        self.tray.hide()
        self.panel.deleteLater()
        self.pet.deleteLater()
        self.deleteLater()


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    DATA.chmod(0o700)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(QIcon(str(APP_ICON)))
    app.setQuitOnLastWindowClosed(False)
    lock = QLockFile(str(DATA / "app.lock"))
    if not lock.tryLock(100):
        return 0
    companion = Companion(Store(DATA / "doa.sqlite3"))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
