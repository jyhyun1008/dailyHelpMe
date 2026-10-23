"""Exercise the real drawer with local data and fake inference; no login/network requests."""
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop/python"))

from PySide6.QtCore import QDate, QPoint, QSettings, Qt, QTime
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow
import app as pet_app
from drawer import Drawer
from store import KST, Store
from ui_widgets import DATA_ROLE


class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)
        cls.settings_directory = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls.settings_directory.name)

    @classmethod
    def tearDownClass(cls):
        cls.settings_directory.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name) / "test.sqlite3")
        QSettings("Cybermaid", "DOAPet").clear()
        self.controller = pet_app.Companion(self.store)
        self.panel = self.controller.panel
        self.controller.timer.stop()
        self.controller.pet.motion.stop()
        self.qt.processEvents()

    def tearDown(self):
        if self.controller.worker:
            self.controller.worker.wait(3000)
        self.controller.dispose()
        self.qt.processEvents()
        self.store.db.close()
        self.directory.cleanup()

    def wait_for_reply(self):
        deadline = time.monotonic() + 3
        while self.controller.busy and time.monotonic() < deadline:
            self.qt.processEvents()
            time.sleep(.01)
        self.qt.processEvents()
        self.assertFalse(self.controller.busy)

    def add(self, kind="schedule", title="휴식", **kwargs):
        op = dict(action="add", kind=kind, title=title, **kwargs)
        self.store.apply_reply({"reply": "기억했어요.", "operations": [op]})
        return next(item for item in self.store.items() if item["title"] == title)

    def test_created_item_card_opens_detail_and_progress_in_all_lists(self):
        from store import now_kst
        day = now_kst().date().isoformat()
        self.controller.receive({"reply":"새 일정을 만들었어요.","operations":[{"action":"add","kind":"schedule","title":"카드 작업","at":day+"T09:00:00+09:00"}]})
        parent = self.store.items()[0]["id"]
        for title in ("컴퓨터 켜기", "파일 열기"):
            self.store.change_subtask(parent,"add",title=title)
        self.store.change_subtask(parent,"toggle",subtask_id=self.store.subtasks(parent)[0]["id"])
        self.panel.refresh()
        self.panel.calendar.setSelectedDate(QDate.fromString(day,"yyyy-MM-dd"))
        self.panel.refresh_calendar()
        views = [self.panel.today, self.panel.tasks, self.panel.calendar_list]
        for view in views:
            self.assertIn("(1/2)", next(view.item(i).text() for i in range(view.count()) if view.item(i).data(Qt.ItemDataRole.UserRole)==parent))
        self.panel.show_page(1)
        self.panel.show()
        self.qt.processEvents()
        view = self.panel.messages
        row = view.item(view.count()-1)
        data = row.data(DATA_ROLE)
        self.assertEqual(data["created_items"][0]["id"],parent)
        area = view.visualItemRect(row).adjusted(5,0,-5,0)
        _,height,header,author = view.itemDelegate().layout_for(area.width(),data)
        QTest.mouseClick(view.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(area.left()+25,area.top()+header+author+height+40))
        self.assertEqual(self.panel.edit_id,parent)
        self.assertEqual(self.panel.tabs.currentIndex(),5)
        self.assertFalse(self.store.items()[0]["done"])

    def test_source_link_click_opens_only_explicit_https_link(self):
        from ui_widgets import MessageList
        from message_links import display_text, source_links
        message = {"id": "source", "role": "assistant", "content": "예보 [기상청](https://www.weather.go.kr/) [실행](javascript:alert) <script>bad</script>", "created_at": "2026-10-24T09:00:00+09:00"}
        self.assertEqual(source_links(message), [("기상청", "https://www.weather.go.kr/")])
        self.assertIn("<script>bad</script>", display_text(message))
        self.assertEqual(source_links(dict(message, role="user")), [])
        view = MessageList()
        view.resize(400, 500)
        view.set_messages([message])
        view.show()
        self.qt.processEvents()
        row = view.item(0)
        data = row.data(DATA_ROLE)
        area = view.visualItemRect(row).adjusted(5,0,-5,0)
        width,height,header,author = view.itemDelegate().layout_for(area.width(),data)
        point = QPoint(area.left()+15, area.top()+header+author+height+30)
        with patch("ui_widgets.QDesktopServices.openUrl") as opened:
            QTest.mouseClick(view.viewport(),Qt.MouseButton.LeftButton,pos=point)
            opened.assert_called_once()
            self.assertEqual(opened.call_args.args[0].toString(), "https://www.weather.go.kr/")
        view.close()
        self.assertIn("이(가)", self.panel.memory_heading.text())

    def test_week_and_diary_date_switch_export(self):
        self.add(kind="routine", title="반복 산책", days=[0, 2, 6], time="09:30")
        self.panel.calendar.setSelectedDate(QDate(2027, 1, 1))
        self.panel.set_calendar_mode(1)
        self.assertEqual(self.panel.weekly.canvas.data["start"], "2026-12-27")
        self.assertEqual(sum(e["title"]=="반복 산책" for d in self.panel.weekly.canvas.data["days"] for e in d["events"]), 3)
        self.panel.show_page(6)
        diary = self.panel.diary
        day = diary.current_day
        diary.title.setText("좋은 하루")
        diary.content.setPlainText("조금 걸었다 🌷")
        diary.date.setDate(diary.date.date().addDays(-1))
        self.assertEqual(self.store.diary_entry(day)["content"], "조금 걸었다 🌷")
        self.assertEqual(diary.content.toPlainText(), "")
        diary.content.setPlainText("어제 기록")
        self.panel.show_page(4)
        export = Path(self.directory.name) / "일기.md"
        with patch("drawer.QFileDialog.getSaveFileName", return_value=(str(export), "")):
            self.panel.export_diary("markdown")
        self.assertIn("어제 기록", export.read_text())
        self.assertIn("조금 걸었다 🌷", export.read_text())
        diary.delete()
        diary.delete()
        self.assertIsNone(self.store.diary_entry(diary.current_day))

    def test_diary_ai_draft_preview_apply_conflict_and_failure(self):
        diary = self.panel.diary
        self.store.message("user", "오늘 산책했어")
        operations = [{"action": "add", "kind": "bucket", "title": "반영되면 안 됨"}]
        with patch.object(pet_app, "request_reply", return_value={"reply": "오늘은 산책을 했다.", "operations": operations}) as request:
            diary.generate_draft()
            self.wait_for_reply()
            self.assertEqual(request.call_args.args[0]["task"], "diary_draft")
        self.assertIsNone(self.store.diary_entry(diary.current_day))
        self.assertEqual(self.store.items(), [])
        self.assertEqual(len(self.store.history()), 1)
        self.assertEqual(diary.draft_preview.toPlainText(), "오늘은 산책을 했다.")
        diary.apply_draft()
        self.assertEqual(self.store.diary_entry(diary.current_day)["content"], "오늘은 산책을 했다.")
        with patch.object(pet_app, "request_reply", return_value={"reply": "새 초안", "operations": []}):
            diary.generate_draft()
            self.wait_for_reply()
        diary.content.setPlainText("직접 쓴 내용")
        diary.apply_draft()
        self.assertIn("변경", diary.draft_status.text())
        self.assertEqual(self.store.diary_entry(diary.current_day)["content"], "직접 쓴 내용")
        with patch.object(pet_app, "request_reply", side_effect=RuntimeError("초안 연결 실패")):
            diary.generate_draft()
            self.wait_for_reply()
        self.assertIn("실패", diary.draft_status.text())
        self.assertTrue(diary.draft_button.isEnabled())

    def test_subtask_detail_manual_completion_and_persistence(self):
        parent = self.add(kind="bucket", title="작업 시작")
        self.panel.show_page(3)
        self.panel.edit_item(parent["id"])
        editor = self.panel.subtask_editor
        self.assertEqual(editor.parent_id, parent["id"])
        editor.input.setText("컴퓨터 켜기")
        editor.add_button.click()
        editor.input.setText("파일 열기")
        editor.input.returnPressed.emit()
        for child in self.store.subtasks(parent["id"]):
            editor.perform("toggle", child["id"])
        self.assertEqual(editor.heading.text(), "2차 일정 · 2/2")
        self.assertFalse(next(i for i in self.store.items() if i["id"]==parent["id"])["done"])
        self.panel.parent_complete.click()
        self.assertTrue(next(i for i in self.store.items() if i["id"]==parent["id"])["done"])
        self.panel.leave_editor()
        self.panel.edit_item(parent["id"])
        self.assertEqual(len(editor.snapshot), 2)
        self.assertEqual(editor.heading.text(), "2차 일정 · 2/2")

    def test_pet_bubble_visible_glyph_margins_are_balanced(self):
        bubble = self.controller.pet.bubble
        for text in ("Hello!", "안녕하세요!", "클릭해서 말을 걸어주세요"):
            self.controller.pet.say(text)
            self.qt.processEvents()
            image = bubble.grab().toImage()
            points = []
            for y in range(image.height()):
                for x in range(image.width()):
                    pixel = image.pixelColor(x, y)
                    if pixel.alpha() > 128 and pixel.red() < 150 and pixel.green() < 130 and pixel.blue() < 140:
                        points.append((x, y))
            left = min(x for x, y in points)
            right = image.width()-1-max(x for x, y in points)
            top = min(y for x, y in points)
            bottom = image.height()-1-max(y for x, y in points)
            self.assertLessEqual(abs(left-right), 2, (text, left, right))
            self.assertLessEqual(abs(top-bottom), 2, (text, top, bottom))

    def test_pet_bubble_sizes_and_scrolls_without_truncation(self):
        pet = self.controller.pet
        pet.say("안녕")
        short = pet.bubble.size()
        self.assertLess(short.width(), 300)
        self.assertLess(short.height(), 94)
        self.assertEqual(pet.bubble.geometry().bottom(), 101)
        long = "긴 이야기를 천천히 읽어보세요. " * 100
        pet.say(long)
        self.qt.processEvents()
        self.assertEqual(pet.bubble.text(), long)
        self.assertLessEqual(pet.bubble.width(), 300)
        self.assertEqual(pet.bubble.height(), 94)
        self.assertGreater(pet.bubble.verticalScrollBar().maximum(), 0)
        pet.bubble.verticalScrollBar().setValue(pet.bubble.verticalScrollBar().maximum())
        self.assertGreater(pet.bubble.verticalScrollBar().value(), 0)
        pet.say("다시 짧게")
        self.qt.processEvents()
        self.assertLess(pet.bubble.height(), 94)
        self.assertEqual(pet.bubble.verticalScrollBar().value(), 0)

    def test_appearance_name_color_portable_image_and_reset(self):
        from PySide6.QtGui import QImage, QColor
        editor = self.panel.appearance_editor
        editor.name.setText("루나")
        editor.color.setText("#3979ae")
        self.assertTrue(editor.save())
        self.assertEqual(self.panel.brand.text(), "루나")
        self.assertEqual(self.controller.pet.menu.actions()[1].text(), "루나과(와) 대화")
        self.assertIn("#3979ae", self.panel.styleSheet())
        self.assertEqual(self.store.context()["companion_name"], "루나")
        image = QImage(40, 40, QImage.Format.Format_ARGB32)
        image.fill(QColor("#3979ae"))
        path = Path(self.directory.name) / "custom.png"
        image.save(str(path))
        self.assertTrue(editor.import_image(str(path)))
        path.unlink()
        self.controller.apply_appearance()
        self.assertTrue(self.controller.pet.custom)
        self.assertFalse(self.controller.pet.image.isNull())
        self.assertTrue(self.store.get("avatar_png"))
        self.assertNotIn("avatar_png", self.store.context())
        self.assertFalse(editor.import_image(str(path)))
        editor.reset()
        self.assertEqual(self.panel.brand.text(), "봉고캣")
        self.assertEqual(self.store.get("theme_color"), "#d64289")
        self.assertFalse(self.store.get("avatar_png"))

    def test_default_bongocat_typing_idle_and_custom_image(self):
        pet = self.controller.pet
        self.assertEqual(self.panel.brand.text(), "봉고캣")
        self.assertEqual(self.store.context()["companion_name"], "봉고캣")
        self.assertTrue(pet.bongo)
        self.assertTrue(all(not frame.isNull() for frame in pet.bongo_frames))
        self.assertTrue(all(frame.hasAlphaChannel() for frame in pet.bongo_frames))
        pet.on_key_activity()
        self.assertEqual(pet.typing_frame, 1)
        pet.on_key_activity()
        self.assertEqual(pet.typing_frame, 2)
        pet.last_tap -= 1
        pet.animate()
        self.assertEqual(pet.typing_frame, 0)
        pet.settings.setValue("reduce_motion", True)
        pet.on_key_activity()
        self.assertEqual(pet.typing_frame, 0)
        pet.settings.setValue("reduce_motion", False)
        self.panel.appearance_editor.keyboard.setChecked(False)
        self.assertFalse(pet.keyboard.enabled)
        self.assertEqual(self.store.get("keyboard_reaction"), "0")
        self.panel.appearance_editor.keyboard.setChecked(True)
        self.assertTrue(pet.keyboard.enabled)
        self.assertEqual(self.store.get("keyboard_reaction"), "1")

    def test_single_click_opens_details_from_today_tasks_and_calendar(self):
        from store import now_kst
        now = now_kst()
        parent = self.add(title="클릭해서 열기", at=now.date().isoformat()+"T14:00:00+09:00")
        self.panel.refresh()
        for page, name in ((0, "today"), (3, "tasks"), (2, "calendar_list")):
            self.panel.show_page(page)
            self.qt.processEvents()
            view = getattr(self.panel, name)
            rect = view.card_rect(view.item(0))
            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(rect.left()+60, rect.top()+24))
            self.assertEqual(self.panel.tabs.currentIndex(), 5, name)
            self.assertEqual(self.panel.edit_id, parent["id"])
            self.assertEqual(self.panel.subtask_editor.parent_id, parent["id"])
        self.panel.show_page(0)
        self.qt.processEvents()
        view = self.panel.today
        rect = view.card_rect(view.item(0))
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(rect.left()+23, rect.top()+27))
        self.assertEqual(self.panel.tabs.currentIndex(), 0)
        self.assertTrue(next(item for item in self.store.items() if item["id"]==parent["id"])["done"])

    def test_calendar_and_day_items_share_one_scroll(self):
        from store import now_kst
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QWheelEvent
        day = now_kst().date().isoformat()
        for index in range(12):
            self.add(title=(f"일정 {index:02} " + ("긴 제목을 줄바꿈해서 확인해요 "*5 if index==11 else "")).strip(), at=day+f"T{index+7:02}:00:00+09:00")
        self.panel.refresh()
        self.panel.show_page(2)
        self.qt.processEvents()
        outer, view = self.panel.calendar_scroll, self.panel.calendar_list
        self.assertEqual(view.count(), 12)
        self.assertGreater(outer.verticalScrollBar().maximum(), 0)
        self.assertEqual(view.verticalScrollBar().maximum(), 0)
        last = view.item(11)
        self.assertLess(view.visualItemRect(last).bottom(), view.viewport().height())
        outer.verticalScrollBar().setValue(0)
        point = QPointF(100, 25)
        event = QWheelEvent(point, QPointF(view.viewport().mapToGlobal(point.toPoint())), QPoint(0, -80), QPoint(0, -120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.ScrollUpdate, False)
        self.qt.sendEvent(view.viewport(), event)
        self.qt.processEvents()
        self.assertGreater(outer.verticalScrollBar().value(), 0)
        outer.verticalScrollBar().setValue(outer.verticalScrollBar().maximum())
        self.qt.processEvents()
        rect = view.card_rect(last)
        target = QPoint(rect.left()+70, rect.top()+24)
        self.assertTrue(outer.viewport().rect().contains(view.viewport().mapTo(outer.viewport(), target)))
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
        self.assertEqual(self.panel.tabs.currentIndex(), 5)
        self.assertEqual(self.panel.edit_id, last.data(Qt.ItemDataRole.UserRole))

    def test_calendar_defaults_monthly_and_links_selected_diary(self):
        self.panel.set_calendar_mode(1)
        self.panel.show_page(3)
        self.panel.show_page(2)
        self.assertEqual(self.panel.calendar_views.currentIndex(), 0)
        target = QDate(2026, 10, 10)
        self.store.save_diary("2026-10-10", "지난 기록", "그날의 이야기")
        self.panel.calendar.setSelectedDate(target)
        self.assertEqual(self.panel.calendar_diary.text(), "일기 보기")
        old_day = self.panel.diary.current_day
        self.panel.diary.content.setPlainText("저장 중이던 오늘 일기")
        self.panel.calendar_diary.click()
        self.assertEqual(self.panel.tabs.currentIndex(), 6)
        self.assertEqual(self.panel.diary.current_day, "2026-10-10")
        self.assertEqual(self.panel.diary.content.toPlainText(), "그날의 이야기")
        self.assertEqual(self.store.diary_entry(old_day)["content"], "저장 중이던 오늘 일기")

    def test_detail_remains_accessible_while_ai_is_busy(self):
        from unittest.mock import PropertyMock
        parent = self.add(kind="bucket", title="답장 중에도 보기")
        self.panel.refresh()
        self.panel.show_page(3)
        self.qt.processEvents()
        with patch.object(pet_app.Companion, "busy", new_callable=PropertyMock, return_value=True):
            self.panel.set_busy(True)
            view = self.panel.tasks
            rect = view.card_rect(view.item(0))
            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(rect.left()+60, rect.top()+24))
            self.assertEqual(self.panel.tabs.currentIndex(), 5)
            self.assertFalse(self.panel.editor_save.isEnabled())
            self.assertEqual(self.panel.subtask_editor.parent_id, parent["id"])
        self.panel.set_busy(False)

    def test_drawer_is_the_only_application_ui(self):
        self.controller.open_chat()
        self.qt.processEvents()
        self.assertEqual(self.panel.tabs.currentIndex(), 1)
        self.assertTrue(self.panel.isVisible())
        self.assertFalse(any(isinstance(widget, QMainWindow) for widget in self.qt.topLevelWidgets()))
        self.assertIs(self.panel.input.window(), self.panel)
        self.assertIs(self.panel.profile.window(), self.panel)

    def test_send_receive_and_role_bubbles(self):
        answer = {"reply": "천천히 해봐요.", "operations": [
            {"action": "add", "kind": "schedule", "title": "휴식", "at": "2026-10-23T14:00:00+09:00"}
        ]}
        with patch.object(pet_app, "request_reply", return_value=answer) as request:
            self.panel.input.setPlainText("내일 오후 두시에 쉬라고 해줘")
            self.controller.send()
            self.wait_for_reply()
            self.assertIn("내일", request.call_args.args[0]["current_request"])
        self.assertEqual(self.panel.messages.count(), 2)
        self.assertEqual(self.panel.messages.item(0).data(DATA_ROLE)["role"], "user")
        self.assertEqual(self.panel.messages.item(1).data(DATA_ROLE)["role"], "assistant")
        self.assertTrue(self.panel.messages.item(0).data(DATA_ROLE)["date_label"])
        self.assertEqual(self.panel.messages.item(1).data(DATA_ROLE)["date_label"], "")
        self.assertEqual(self.controller.pet.bubble.text(), answer["reply"])
        self.assertTrue(self.panel.send_button.isEnabled())
        self.assertTrue(self.panel.retry_button.isHidden())
        self.panel.calendar.setSelectedDate(QDate(2026, 10, 23))
        self.assertEqual(self.panel.calendar_list.count(), 1)

    def test_failure_and_retry_keep_single_user_message(self):
        with patch.object(pet_app, "request_reply", side_effect=RuntimeError("연결 오류")):
            self.panel.input.setPlainText("안녕")
            self.controller.send()
            self.wait_for_reply()
        self.assertIn("연결 오류", self.panel.chat_status.text())
        self.assertFalse(self.panel.retry_button.isHidden())
        self.store.message("assistant", "뭐 하고 계세요?")
        with patch.object(pet_app, "request_reply", return_value={"reply": "안녕하세요!", "operations": []}):
            self.controller.retry()
            self.wait_for_reply()
        self.assertEqual(len([m for m in self.store.history() if m["role"] == "user"]), 1)
        self.assertEqual(self.store.history()[-1]["content"], "안녕하세요!")

    def test_composer_enter_sends_shift_enter_inserts_newline(self):
        self.controller.open_chat()
        self.panel.input.setPlainText("첫 줄")
        self.panel.input.moveCursor(self.panel.input.textCursor().MoveOperation.End)
        QTest.keyClick(self.panel.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        self.assertIn("\n", self.panel.input.toPlainText())
        with patch.object(pet_app, "request_reply", return_value={"reply": "네!", "operations": []}):
            QTest.keyClick(self.panel.input, Qt.Key.Key_Return)
            self.wait_for_reply()
        self.assertEqual(self.panel.messages.count(), 2)

    def test_overdue_work_on_today_keeps_original_date_and_completion(self):
        now = datetime(2026, 10, 24, 14, tzinfo=KST)
        old = self.add(title="어제 못한 일정", at="2026-10-23T15:00:00+09:00")
        deadline = self.add(kind="todo", title="지난 마감", at="2026-10-22T23:59:00+09:00")
        self.add(title="오늘 일정", at="2026-10-24T09:00:00+09:00")
        self.add(kind="routine", title="어제 루틴", days=[5], time="09:00")
        with patch("drawer.now_kst", return_value=now):
            self.panel.refresh()
            self.assertEqual(self.panel.today.count(), 3)
            rows = [self.panel.today.item(i).data(DATA_ROLE) for i in range(3)]
            self.assertEqual(rows[0]["timeline_header"], "이전 미완료")
            self.assertEqual(rows[0]["id"], deadline["id"])
            self.assertIn("원래 마감", self.panel.today.item(0).text())
            self.assertEqual(next(item for item in self.store.items() if item["id"]==old["id"])["at"], old["at"])
            self.store.toggle_completed(old["id"], now)
            self.panel.refresh()
            self.assertEqual(self.panel.today.count(), 2)
            self.store.toggle_completed(old["id"], now)
            self.panel.refresh()
            self.assertEqual(self.panel.today.count(), 3)
        self.panel.calendar.setSelectedDate(QDate(2026, 10, 23))
        self.assertEqual(self.panel.calendar_list.count(), 2)

    def test_calendar_today_filter_and_event_dots(self):
        now = datetime(2026, 10, 22, 14, 0, tzinfo=KST)
        self.add(title="오늘 약속", at="2026-10-22T15:00:00+09:00")
        self.add(title="내일 약속", at="2026-10-23T15:00:00+09:00")
        self.add(kind="todo", title="오늘 마감", at="2026-10-22T23:59:00+09:00")
        self.add(kind="routine", title="목요일 루틴", days=[4], time="09:00")
        self.add(kind="bucket", title="언젠가 여행")
        with patch("drawer.now_kst", return_value=now):
            self.panel.refresh()
        self.assertEqual(self.panel.today.count(), 3)
        self.assertEqual(self.panel.tasks.count(), 5)
        self.panel.calendar.setSelectedDate(QDate(2026, 10, 23))
        self.assertEqual(self.panel.calendar_list.count(), 1)
        self.assertIn("내일 약속", self.panel.calendar_list.item(0).text())
        self.assertIn("2026-10-22", self.panel.calendar.grid.marks)
        self.assertEqual(len(self.panel.calendar.grid.marks["2026-10-22"]), 3)
        self.panel.filter.setCurrentIndex(self.panel.filter.findData("bucket"))
        self.assertEqual(self.panel.tasks.count(), 1)

    def test_calendar_month_boundary_and_grid_selection(self):
        calendar = self.panel.calendar
        calendar.setSelectedDate(QDate(2026, 12, 31))
        calendar.move_month(1)
        self.assertEqual((calendar.yearShown(), calendar.monthShown()), (2027, 1))
        calendar.move_month(-1)
        self.assertEqual((calendar.yearShown(), calendar.monthShown()), (2026, 12))
        target = QDate(2026, 12, 15)
        index = calendar.grid.first_cell().daysTo(target)
        point = QPoint(int((index % 7 + .5) * calendar.grid.width() / 7), 26 + index // 7 * 36 + 14)
        self.panel.show_page(2)
        self.qt.processEvents()
        # Compute the point after the calendar receives its final layout width.
        point.setX(int((index % 7 + .5) * calendar.grid.width() / 7))
        QTest.mouseClick(calendar.grid, Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(calendar.selectedDate(), target)
        QTest.keyClick(calendar.grid, Qt.Key.Key_Right)
        self.assertEqual(calendar.selectedDate(), target.addDays(1))

    def test_inline_add_edit_delete_and_completion(self):
        self.panel.edit_item(kind="todo")
        self.assertEqual(self.panel.tabs.currentIndex(), 5)
        self.panel.edit_title.setText("작은 작업")
        self.panel.save_item()
        item = self.store.items()[0]
        self.assertEqual(item["title"], "작은 작업")
        self.controller.toggle_item(item["id"])
        self.assertEqual(self.store.items()[0]["done"], 1)
        self.assertEqual(self.panel.tasks.count(), 0)
        self.panel.show_done.setChecked(True)
        self.assertEqual(self.panel.tasks.count(), 1)
        self.controller.toggle_item(item["id"])
        self.assertEqual(self.store.items()[0]["done"], 0)
        self.panel.edit_item(item["id"])
        self.panel.edit_title.setText("고친 작업")
        self.panel.has_date.setChecked(True)
        self.panel.edit_date.setDate(QDate(2026, 11, 2))
        self.panel.all_day.setChecked(False)
        self.panel.edit_time.setTime(QTime(17, 30))
        self.panel.save_item()
        self.assertEqual(self.store.items()[0]["at"], "2026-11-02T17:30:00+09:00")
        self.panel.edit_item(item["id"])
        self.panel.delete_item()
        self.assertEqual(len(self.store.items()), 1)
        self.panel.delete_item()
        self.assertEqual(self.store.items(), [])

    def test_editor_validation_and_busy_guard(self):
        self.panel.edit_item(kind="routine")
        self.panel.edit_title.setText("운동")
        for day in self.panel.day_buttons:
            day.setChecked(False)
        self.panel.save_item()
        self.assertFalse(self.store.items())
        self.assertIn("요일", self.panel.editor_error.text())
        self.panel.set_busy(True)
        self.assertFalse(self.panel.editor_save.isEnabled())
        self.assertFalse(self.panel.tasks.editable)
        # Browsing the calendar remains possible while the reply is generated.
        self.panel.show_page(2)
        self.assertEqual(self.panel.tabs.currentIndex(), 2)

    def test_profile_confirmation_and_settings_persistence(self):
        self.panel.show_page(4)
        self.panel.profile.setPlainText("민트를 좋아해요")
        self.controller.save_profile()
        self.assertEqual(self.store.get("profile"), "민트를 좋아해요")
        self.store.message("assistant", "기억했어요")
        message = self.store.history()[0]
        self.controller.confirm_message(message["id"])
        self.assertEqual(self.store.history()[0]["confirmed"], 1)
        self.panel.transparency.setValue(45)
        self.assertAlmostEqual(self.panel.windowOpacity(), .55, places=2)
        recreated = Drawer(self.controller)
        self.assertEqual(recreated.transparency.value(), 45)
        self.assertEqual(recreated.tabs.currentIndex(), 4)
        recreated.deleteLater()
        self.panel.show()
        self.controller.toggle_panel()
        self.assertFalse(self.panel.isVisible())
        self.controller.panel_action.trigger()
        self.assertTrue(self.panel.isVisible())
        self.panel.shutting_down = True
        self.panel.hide()
        self.assertTrue(self.panel.settings.value("mini/visible", False, type=bool))

    def test_load_older_preserves_position(self):
        for index in range(125):
            self.store.message("user", f"대화 {index}")
        self.controller.open_chat()
        self.panel.refresh_messages()
        self.qt.processEvents()
        self.assertEqual(self.panel.messages.count(), 50)
        self.panel.load_older()
        self.assertEqual(self.panel.messages.count(), 100)
        self.panel.load_older()
        self.assertEqual(self.panel.messages.count(), 125)
        self.assertTrue(self.panel.more.isHidden())
        self.assertIn("대화 0", self.panel.messages.item(0).text())
        self.panel.messages.verticalScrollBar().setValue(0)
        self.panel.refresh()
        self.assertEqual(self.panel.messages.verticalScrollBar().value(), 0)


if __name__ == "__main__":
    unittest.main()
