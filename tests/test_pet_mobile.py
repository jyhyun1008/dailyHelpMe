"""Exercise HTTP auth, Qt-thread dispatch, shared data and real push encryption offline."""
import base64
import http.client
import json
import os
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop/python"))
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
import app as pet_app
from mobile_server import MobileService, valid_endpoint
from ui_widgets import schedule_time, timeline_items
from store import Store


class MobileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)
        cls.settings_dir = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls.settings_dir.name)

    @classmethod
    def tearDownClass(cls):
        cls.settings_dir.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name) / "test.sqlite3")
        self.controller = pet_app.Companion(self.store)
        self.controller.timer.stop()
        self.controller.pet.motion.stop()
        self.mobile = self.controller.mobile
        self.mobile.port = 0
        self.assertTrue(self.mobile.enable(True))
        self.port = self.mobile.server.server_address[1]
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.cookie = ""

    def tearDown(self):
        if self.controller.worker:
            self.controller.worker.wait(3000)
        self.controller.dispose()
        self.executor.shutdown()
        self.qt.processEvents()
        self.store.db.close()
        self.directory.cleanup()

    def wait(self, future):
        deadline = time.monotonic() + 4
        while not future.done() and time.monotonic() < deadline:
            self.qt.processEvents()
            time.sleep(.005)
        return future.result(timeout=1)

    def request(self, path, data=None, origin=True, cookie=None):
        def run():
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
            headers = {"Cookie": self.cookie if cookie is None else cookie}
            if data is not None:
                headers["Content-Type"] = "application/json"
                if origin:
                    headers["Origin"] = f"http://127.0.0.1:{self.port}"
            connection.request("POST" if data is not None else "GET", path,
                               body=json.dumps(data) if data is not None else None, headers=headers)
            response = connection.getresponse()
            body = response.read()
            result = response.status, dict(response.getheaders()), body
            connection.close()
            return result
        return self.wait(self.executor.submit(run))

    def pair(self):
        status, headers, body = self.request("/api/pair", {"code": self.mobile.pairing_code})
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("Secure", headers["Set-Cookie"])
        self.cookie = headers["Set-Cookie"].split(";")[0]

    def test_message_pages_are_bounded_and_reach_history_beyond_1000(self):
        self.pair()
        with self.store.db:
            self.store.db.execute("DELETE FROM messages")
            self.store.db.executemany(
                "INSERT INTO messages(role,content,created_at) VALUES ('user',?,?)",
                [(str(index), "2026-10-24T12:00:00+09:00") for index in range(1050)])
        page = json.loads(self.request("/api/state?limit=1000")[2])
        self.assertEqual(len(page["messages"]), 50)
        self.assertTrue(page["hasMoreMessages"])
        seen = [m["id"] for m in page["messages"]]
        # A new reply between page requests must not shift the older page.
        self.store.message("assistant", "새 답장")
        while page["hasMoreMessages"]:
            page = json.loads(self.request("/api/state?before=" + str(seen[0]))[2])
            ids = [m["id"] for m in page["messages"]]
            self.assertEqual(len(ids), 50)
            self.assertLess(ids[-1], seen[0])
            seen = ids + seen
        self.assertEqual(len(seen), 1050)
        self.assertEqual(len(set(seen)), 1050)
        empty = json.loads(self.request("/api/state?before=" + str(seen[0]))[2])
        self.assertEqual(empty["messages"], [])
        self.assertFalse(empty["hasMoreMessages"])

    def test_mobile_chat_marks_message_source(self):
        self.pair()
        with patch.object(self.controller, "send_text", return_value=True) as send:
            self.assertEqual(self.request("/api/chat", {"text": "안녕"})[0], 202)
            send.assert_called_once_with("안녕", source="mobile")

    def test_custom_media_auth_upload_archive_and_sticker_without_ai(self):
        from test_pet_media import sample_png
        image = base64.b64encode(sample_png()).decode()
        payload = {"kind":"sticker","name":"인사","image":image}
        self.assertEqual(self.request("/api/media/add",payload)[0],401)
        self.pair()
        self.assertEqual(self.request("/api/media/add",dict(payload,image="broken"))[0],400)
        status,_,body = self.request("/api/media/add",payload)
        self.assertEqual(status,200)
        key = json.loads(body)["id"]
        self.assertEqual(self.request("/api/media/image/"+key,cookie="")[0],401)
        status,headers,raw = self.request("/api/media/image/"+key)
        self.assertEqual(status,200);self.assertEqual(headers["Content-Type"],"image/png")
        self.assertTrue(raw.startswith(b"\x89PNG"))
        with patch.object(self.controller,"start_reply") as start:
            self.assertEqual(self.request("/api/sticker",{"id":key})[0],200)
            start.assert_not_called()
        state=json.loads(self.request("/api/state")[2])
        self.assertEqual(state["messages"][-1]["sticker"]["id"],key)
        self.assertEqual(state["media"][0]["name"],"인사")
        self.assertNotIn("png",state["media"][0])
        self.assertEqual(self.request("/api/media/delete",{"id":key})[0],200)
        self.assertEqual(self.request("/api/sticker",{"id":key})[0],400)
        self.assertEqual(self.request("/api/media/image/"+key)[0],200)

    def test_web_search_settings_authenticated_shared_and_validated(self):
        self.assertEqual(self.request("/api/search/settings", {"enabled": False})[0], 401)
        self.pair()
        self.assertEqual(self.request("/api/search/settings", {"enabled": "false"})[0], 400)
        self.assertEqual(self.request("/api/search/settings", {"enabled": False})[0], 200)
        self.assertFalse(self.controller.panel.web_search.isChecked())
        self.assertFalse(self.store.context()["web_search_enabled"])
        self.assertFalse(json.loads(self.request("/api/state")[2])["webSearchEnabled"])
        self.controller.panel.web_search.setChecked(True)
        self.assertTrue(json.loads(self.request("/api/state")[2])["webSearchEnabled"])

    def test_diary_authenticated_save_export_delete_and_week(self):
        self.assertEqual(self.request("/api/diary/export")[0], 401)
        self.pair()
        diary = {"date": "2026-10-24", "title": "토요일", "content": "산책 🌷"}
        self.assertEqual(self.request("/api/diary", diary)[0], 200)
        self.assertEqual(self.store.diary_entry(diary["date"])["content"], diary["content"])
        self.assertEqual(json.loads(self.request("/api/diary?date=2026-10-24")[2])["entry"]["title"], "토요일")
        status, headers, body = self.request("/api/diary/export?format=markdown")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/markdown"))
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertIn("산책 🌷", body.decode())
        self.assertNotIn("산책 🌷", self.request("/api/state")[2].decode())
        self.assertEqual(json.loads(self.request("/api/week?date=2027-01-01")[2])["start"], "2026-12-27")
        self.assertEqual(self.request("/api/diary", dict(diary, date="invalid"))[0], 400)
        self.assertEqual(self.request("/api/diary/delete", {"date": diary["date"]})[0], 200)
        self.assertIsNone(self.store.diary_entry(diary["date"]))

    def test_mobile_bookmarks_and_diary_tags(self):
        self.pair()
        self.store.message("user", "오늘 산책했어")
        message_id = self.store.history()[-1]["id"]
        self.assertEqual(self.request("/api/bookmark", {"id": message_id})[0], 200)
        state = json.loads(self.request("/api/state")[2])
        self.assertTrue(state["messages"][-1]["bookmarked"])
        self.assertEqual(state["bookmarks"][0]["content"], "오늘 산책했어")
        self.assertEqual(self.controller.panel.diary.bookmark_toggle.text(), "★ 북마크 1개 ▾")
        self.assertEqual(self.request("/api/bookmark", {"id": "1"})[0], 400)
        diary = {"date": "2026-10-24", "title": "", "content": "", "weather": "☀️ 맑음", "mood": "😊 좋음", "tags": "산책, #카페, 산책"}
        self.assertEqual(self.request("/api/diary", diary)[0], 200)
        payload = json.loads(self.request("/api/diary?date=2026-10-24")[2])
        self.assertEqual(payload["entry"]["tags"], ["산책", "카페"])
        self.assertIn("😊 좋음", payload["moods"])
        listing = json.loads(self.request("/api/diary/list?tag=" + __import__("urllib.parse").parse.quote("카페"))[2])
        self.assertEqual([e["date"] for e in listing["entries"]], ["2026-10-24"])
        self.assertEqual(listing["tags"], [["산책", 1], ["카페", 1]])
        self.assertEqual(json.loads(self.request("/api/diary/list?tag=none")[2])["entries"], [])
        self.assertEqual(self.request("/api/bookmark", {"id": message_id})[0], 200)
        self.assertEqual(json.loads(self.request("/api/state")[2])["bookmarks"], [])

    def test_mobile_diary_draft_preview_and_apply(self):
        self.assertEqual(self.request("/api/diary/draft", {"date": "2026-10-24"})[0], 401)
        self.pair()
        from store import now_kst
        day = now_kst().date().isoformat()
        self.store.message("user", "산책했어")
        with patch.object(pet_app, "request_reply", return_value={"reply": "천천히 산책한 하루였다.", "operations": []}):
            self.assertEqual(self.request("/api/diary/draft", {"date": day})[0], 202)
            deadline = time.monotonic()+3
            while self.controller.busy and time.monotonic()<deadline:
                self.qt.processEvents()
                time.sleep(.01)
            self.qt.processEvents()
        payload = json.loads(self.request("/api/state")[2])
        self.assertEqual(payload["diaryDraft"]["content"], "천천히 산책한 하루였다.")
        self.assertNotIn("original", payload["diaryDraft"])
        self.assertIsNone(self.store.diary_entry(day))
        self.assertEqual(self.request("/api/diary/draft/apply", {})[0], 200)
        self.assertEqual(self.store.diary_entry(day)["content"], "천천히 산책한 하루였다.")

    def test_mobile_today_carries_over_without_rewriting_deadline(self):
        self.pair()
        original = "2000-01-01T23:59:00+09:00"
        self.store.apply_reply({"reply": "네", "operations": [{"action": "add", "kind": "todo", "title": "미완료", "at": original}]})
        item = self.store.items()[0]
        state = json.loads(self.request("/api/state")[2])
        self.assertTrue(state["todayItems"][0]["carryover"])
        self.assertEqual(state["todayItems"][0]["at"], original)
        self.assertEqual(self.request("/api/toggle", {"id": item["id"]})[0], 200)
        self.assertEqual(json.loads(self.request("/api/state")[2])["todayItems"], [])
        self.assertEqual(self.store.items()[0]["at"], original)

    def test_mobile_subtasks_do_not_complete_parent_or_enter_ai_context(self):
        self.assertEqual(self.request("/api/subtasks?parent=missing")[0], 401)
        self.pair()
        self.store.apply_reply({"reply":"saved", "operations":[{"action":"add", "kind":"bucket", "title":"Start"}]})
        parent = self.store.items()[0]["id"]
        status, _, body = self.request("/api/subtask", {"parent":parent,"action":"add","title":"Turn on computer"})
        self.assertEqual(status, 200)
        child = json.loads(body)["subtasks"][0]
        self.assertEqual(self.request("/api/subtask", {"parent":parent,"action":"toggle","id":child["id"]})[0], 200)
        self.assertTrue(json.loads(self.request("/api/subtasks?parent="+parent)[2])["subtasks"][0]["done"])
        self.assertFalse(self.store.items()[0]["done"])
        self.assertNotIn("Turn on computer", json.dumps(self.store.context()))
        self.assertEqual(self.request("/api/toggle", {"id":parent})[0], 200)
        self.assertTrue(self.store.items()[0]["done"])
        self.assertEqual(self.request("/api/subtask", {"parent":parent,"action":"add","title":" "})[0], 400)
        self.assertEqual(self.request("/api/delete", {"id":parent})[0], 200)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM subtasks").fetchone()[0], 0)

    def test_mobile_appearance_auth_name_theme_and_avatar(self):
        self.assertEqual(self.request("/api/avatar")[0], 401)
        self.assertEqual(self.request("/api/theme.css")[0], 401)
        self.pair()
        self.assertEqual(self.request("/api/appearance", {"name":"Luna", "color":"#3979ae"})[0], 200)
        payload = json.loads(self.request("/api/state")[2])
        self.assertEqual(payload["appearance"]["name"], "Luna")
        self.assertEqual(self.controller.panel.brand.text(), "Luna")
        status, headers, body = self.request("/api/theme.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers["Content-Type"])
        self.assertIn("#3979ae", body.decode())
        status, headers, body = self.request("/api/avatar")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertTrue(body.startswith(b"\x89PNG"))
        self.assertEqual(self.request("/api/appearance", {"name":"", "color":"red"})[0], 400)
        self.assertEqual(self.store.get("companion_name"), "Luna")

    def test_http_pair_origin_auth_and_shared_state(self):
        self.assertEqual(self.request("/api/state")[0], 401)
        self.assertEqual(self.request("/api/pair", {"code": self.mobile.pairing_code}, origin=False)[0], 403)
        self.assertEqual(self.request("/api/pair", {"code": "wrong"})[0], 401)
        self.pair()
        self.store.message("user", "맥에서 쓴 메시지")
        status, _, body = self.request("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["messages"][0]["content"], "맥에서 쓴 메시지")
        self.assertNotIn("mobile_pairing", body.decode())
        self.assertNotIn("mobile_vapid", body.decode())
        self.assertEqual(self.request("/api/profile", {"profile": "모바일에서 기억 수정"})[0], 200)
        self.assertEqual(self.store.get("profile"), "모바일에서 기억 수정")
        self.assertEqual(self.request("/api/logout", {})[0], 200)
        self.assertEqual(self.request("/api/state")[0], 401)

    def test_mobile_chat_uses_existing_engine_and_pet(self):
        self.pair()
        with patch.object(pet_app, "request_reply", return_value={"reply": "모바일에서도 안녕하세요!", "operations": []}):
            self.assertEqual(self.request("/api/chat", {"text": "폰에서 보낸 말"})[0], 202)
            deadline = time.monotonic() + 3
            while self.controller.busy and time.monotonic() < deadline:
                self.qt.processEvents()
                time.sleep(.01)
            self.qt.processEvents()
        self.assertEqual(self.store.history()[0]["content"], "폰에서 보낸 말")
        self.assertEqual(self.store.history()[-1]["content"], "모바일에서도 안녕하세요!")
        self.assertEqual(self.controller.pet.bubble.text(), "모바일에서도 안녕하세요!")

    def test_item_mutation_and_explicit_reset_revoke_devices(self):
        self.pair()
        operation = {"action": "add", "kind": "schedule", "title": "폰에서 일정", "at": "2026-10-23T14:00:00+09:00"}
        self.assertEqual(self.request("/api/item", {"operation": operation})[0], 200)
        item = self.store.items()[0]
        self.assertEqual(self.request("/api/toggle", {"id": item["id"]})[0], 200)
        self.assertEqual(self.store.items()[0]["done"], 1)
        self.assertEqual(self.request("/api/delete", {"id": item["id"]})[0], 200)
        self.assertEqual(self.store.items(), [])
        old_code = self.mobile.pairing_code
        self.controller.reset_mobile_pairing()
        self.assertNotEqual(old_code, self.mobile.pairing_code)
        self.assertEqual(self.request("/api/state")[0], 401)

    def test_static_assets_manifest_and_worker(self):
        for path in ("/", "/app.js", "/style.css", "/sw.js", "/font.woff2", "/font-mulmaru.woff2", "/manifest.webmanifest", "/manifest-en.webmanifest", "/icon.png", "/icon-512.png", "/icon-maskable-512.png", "/apple-touch-icon.png", "/favicon.png"):
            status, headers, body = self.request(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body)
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        manifest = json.loads(self.request("/manifest.webmanifest")[2])
        self.assertEqual(manifest["name"], "날도와줘")
        self.assertEqual(json.loads(self.request("/manifest-en.webmanifest")[2])["name"], "DailyHelpMe!!")
        self.assertEqual(manifest["id"], "/")  # Keep the identity of already-installed PWAs.
        from PySide6.QtGui import QImage
        for icon in manifest["icons"]:
            image = QImage.fromData(self.request(icon["src"])[2])
            self.assertEqual(f"{image.width()}x{image.height()}", icon["sizes"])
            self.assertEqual(image.pixelColor(0,0).alpha(),255)
        apple = QImage.fromData(self.request("/apple-touch-icon.png")[2])
        self.assertEqual((apple.width(),apple.height()),(180,180))
        self.assertEqual(self.request("/../store.py")[0], 404)

    def test_animated_media_http_preserves_bytes_and_mime_type(self):
        self.pair()
        for extension in ('webp', 'gif'):
            raw = (Path(__file__).parent / 'fixtures' / ('animated.' + extension)).read_bytes()
            status, _, body = self.request('/api/media/add', {'kind': 'emoji', 'name': extension, 'image': base64.b64encode(raw).decode()})
            self.assertEqual(status, 200)
            asset = self.store.media_assets()[-1]
            status, headers, body = self.request('/api/media/image/' + asset['id'])
            self.assertEqual(status, 200)
            self.assertEqual(body, raw)
            self.assertEqual(dict(headers)['Content-Type'], 'image/' + extension)

    def test_push_endpoint_validation_and_stable_key(self):
        self.pair()
        first = self.mobile.vapid_key()
        self.assertEqual(first, self.mobile.vapid_key())
        from py_vapid import Vapid
        self.assertTrue(Vapid.from_string(self.store.get("mobile_vapid")))
        self.assertFalse(valid_endpoint("http://127.0.0.1:9000/private"))
        self.assertFalse(valid_endpoint("https://web.push.apple.com.evil.example/x"))
        self.assertTrue(valid_endpoint("https://web.push.apple.com/QxTEST"))
        self.assertEqual(self.request("/api/push/test", {})[0], 400)
        self.assertEqual(self.request("/api/push/subscribe", {"subscription": {"endpoint": "https://localhost/private"}})[0], 400)

    def test_real_push_encryption_with_mock_transport_and_expired_cleanup(self):
        self.pair()
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        key = ec.generate_private_key(ec.SECP256R1())
        point = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        def encoded(value):
            return base64.urlsafe_b64encode(value).decode().rstrip("=")
        subscription = {"endpoint": "https://web.push.apple.com/TEST", "keys": {"p256dh": encoded(point), "auth": encoded(os.urandom(16))}}
        self.assertEqual(self.request("/api/push/subscribe", {"subscription": subscription})[0], 200)
        self.assertTrue(json.loads(self.request("/api/state")[2])["pushSubscribed"])
        class Response:
            status_code = 410
            headers = {}
            reason = "Gone"
            text = "Expired"
            content = b"Expired"
        with patch("requests.post", return_value=Response()) as post:
            self.mobile.notify(["진짜 암호화되는 테스트"])
            deadline = time.monotonic() + 3
            while self.mobile.push_pending and time.monotonic() < deadline:
                self.qt.processEvents()
                time.sleep(.01)
            self.qt.processEvents()
        self.assertTrue(post.called)
        self.assertIsInstance(post.call_args.kwargs["data"], bytes)
        authorization = post.call_args.kwargs["headers"]["Authorization"]
        token = authorization.split("t=", 1)[1].split(",", 1)[0]
        claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        self.assertEqual(claims["sub"], "https://github.com/jyhyun1008/dailyHelpMe")
        self.assertNotIn("진짜 암호화되는 테스트".encode(), post.call_args.kwargs["data"])
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM mobile_push").fetchone()[0], 0)

    def test_pair_rate_limit(self):
        for index in range(10):
            self.assertEqual(self.request("/api/pair", {"code": "wrong"})[0], 401)
        self.assertEqual(self.request("/api/pair", {"code": self.mobile.pairing_code})[0], 429)


class TimelineTests(unittest.TestCase):
    def test_untimed_first_and_timed_chronology(self):
        def item(kind, title, at=None, time=None):
            return dict(kind=kind, title=title, at=at, time=time)
        items = [item("schedule", "오후", "2026-10-23T14:00:00+09:00"),
                 item("todo", "시간 없는 마감", "2026-10-23T23:59:00+09:00"),
                 item("routine", "아침 루틴", time="09:00"),
                 item("schedule", "시간 없는 일정", "2026-10-23T05:01:00+09:00")]
        result = timeline_items(items)
        self.assertEqual([schedule_time(value) for value in result], [None, None, "09:00", "14:00"])
        self.assertEqual(result[-1]["title"], "오후")


if __name__ == "__main__":
    unittest.main()
