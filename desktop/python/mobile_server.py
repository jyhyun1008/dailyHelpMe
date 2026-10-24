"""Loopback-only companion server, exposed privately by Tailscale Serve."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, Signal
from store import now_kst

import sys
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
COOKIE = "doa_mobile"


def encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def valid_endpoint(endpoint):
    if not isinstance(endpoint, str):
        return False
    url = urlsplit(endpoint)
    host = url.hostname or ""
    return url.scheme == "https" and url.port in (None, 443) and not url.username and not url.password and (
        host in ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com") or host.endswith(".push.apple.com"))


@dataclass
class Call:
    method: str
    path: str
    data: dict
    cookie: str
    done: threading.Event = field(default_factory=threading.Event)
    result: tuple = (503, {"error": "앱에 연결하지 못했어요."}, {})
    cancelled: bool = False


class HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(rpc, asset_root=ROOT):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Pairing codes, cookies and conversations must not go into HTTP logs.

        def respond(self, status, data, headers=None, content_type="application/json; charset=utf-8"):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            headers = dict(headers or {})
            self.send_header("Content-Type", headers.pop("Content-Type", content_type))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            files = {"/": (asset_root / "mobile/index.html", "text/html; charset=utf-8"),
                     "/app.js": (asset_root / "mobile/app.js", "text/javascript; charset=utf-8"),
                     "/subtasks.js": (asset_root / "mobile/subtasks.js", "text/javascript; charset=utf-8"),
                     "/appearance.js": (asset_root / "mobile/appearance.js", "text/javascript; charset=utf-8"),
                     "/media.js": (asset_root / "mobile/media.js", "text/javascript; charset=utf-8"),
                     "/style.css": (asset_root / "mobile/style.css", "text/css; charset=utf-8"),
                     "/sw.js": (asset_root / "mobile/sw.js", "text/javascript; charset=utf-8"),
                     "/manifest.webmanifest": (asset_root / "mobile/manifest.webmanifest", "application/manifest+json"),
                     "/manifest-en.webmanifest": (asset_root / "mobile/manifest-en.webmanifest", "application/manifest+json"),
                     "/font.woff2": ((asset_root / "desktop/python/assets/fonts/ThinMulmaru.woff2" if hasattr(sys, "_MEIPASS") else asset_root / "assets/fonts/ThinMulmaru.woff2"), "font/woff2"),
                     "/icon.png": (asset_root / "mobile/icon.png", "image/png"),
                     "/icon-512.png": (asset_root / "mobile/icon-512.png", "image/png"),
                     "/icon-maskable-512.png": (asset_root / "mobile/icon-maskable-512.png", "image/png"),
                     "/apple-touch-icon.png": (asset_root / "mobile/apple-touch-icon.png", "image/png"),
                     "/favicon.png": (asset_root / "mobile/favicon.png", "image/png")}
            if path in files:
                file, kind = files[path]
                if not file.is_file():
                    self.respond(404, {"error": "not found"})
                    return
                self.respond(200, file.read_bytes(), content_type=kind)
            elif path.startswith("/api/"):
                status, payload, headers = rpc("GET", self.path, {}, self.headers.get("Cookie", ""))
                self.respond(status, payload, headers)
            else:
                self.respond(404, {"error": "not found"})

        def do_POST(self):
            # Only JSON, same-origin mutations. No CORS and no form-encoded requests.
            origin = self.headers.get("Origin", "")
            if not origin or urlsplit(origin).netloc != self.headers.get("Host") or urlsplit(origin).scheme not in ("http", "https"):
                self.respond(403, {"error": "잘못된 요청 출처예요."})
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.respond(415, {"error": "JSON 요청이 필요해요."})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= (6*1024*1024 if urlsplit(self.path).path == "/api/media/add" else 131072):
                    raise ValueError()
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError()
            except (ValueError, TypeError):
                self.respond(400, {"error": "잘못된 요청이에요."})
                return
            status, payload, headers = rpc("POST", self.path, data, self.headers.get("Cookie", ""))
            self.respond(status, payload, headers)
    return Handler


class MobileService(QObject):
    request_received = Signal(object)
    push_result = Signal(object)

    def __init__(self, companion, port=8765):
        super().__init__(companion)
        self.companion, self.store, self.port = companion, companion.store, port
        self.server = None
        self.thread = None
        self.closed = False
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="doa-push")
        self.attempts = []
        self.push_pending = False
        self.notifications = []
        self.last_error = ""
        self.request_received.connect(self.handle_call)
        self.push_result.connect(self.handle_push_result)
        self.store.db.executescript("""
            CREATE TABLE IF NOT EXISTS mobile_sessions (token TEXT PRIMARY KEY, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS mobile_push (endpoint TEXT PRIMARY KEY, session TEXT NOT NULL, subscription TEXT NOT NULL);
        """)
        if not self.store.get("mobile_pairing"):
            self.store.set("mobile_pairing", secrets.token_hex(8))

    @property
    def pairing_code(self):
        return self.store.get("mobile_pairing")

    def enable(self, enabled):
        if enabled and not self.server:
            try:
                self.server = HTTPServer(("127.0.0.1", self.port), make_handler(self.rpc))
                self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
                self.thread.start()
            except OSError:
                self.server = None
                self.last_error = f"모바일 포트 {self.port}를 열지 못했어요. 다른 앱이 사용 중인지 확인해주세요."
                return False
        elif not enabled and self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        self.store.set("mobile_enabled", "1" if enabled else "0")
        self.last_error = ""
        return True

    def close(self):
        self.closed = True
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        self.executor.shutdown(wait=False, cancel_futures=True)

    def rpc(self, method, path, data, cookie):
        call = Call(method, path, data, cookie)
        self.request_received.emit(call)
        if not call.done.wait(10):
            call.cancelled = True
            return 503, {"error": "맥 앱의 응답을 기다리는 중이에요."}, {}
        return call.result

    def handle_call(self, call):
        if call.cancelled:
            return
        try:
            call.result = self.dispatch(call.method, call.path, call.data, call.cookie)
        except (ValueError, TypeError, KeyError):
            call.result = 400, {"error": "입력 내용을 확인해주세요."}, {}
        except Exception:
            call.result = 500, {"error": "요청을 처리하지 못했어요."}, {}
        finally:
            call.done.set()

    def session(self, cookie):
        parsed = SimpleCookie()
        try:
            parsed.load(cookie)
            token = parsed[COOKIE].value
        except (KeyError, ValueError, CookieError):
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        row = self.store.db.execute("SELECT token FROM mobile_sessions WHERE token=? AND expires>?", (digest, time.time())).fetchone()
        return digest if row else None

    def dispatch(self, method, path, data, cookie):
        url = urlsplit(path)
        path = url.path
        if method == "POST" and path == "/api/pair":
            self.attempts = [stamp for stamp in self.attempts if stamp > time.time() - 60]
            if len(self.attempts) >= 10:
                return 429, {"error": "잠시 뒤 다시 연결해주세요."}, {}
            self.attempts.append(time.time())
            code = data.get("code")
            if not isinstance(code, str) or not hmac.compare_digest(code.strip(), self.pairing_code):
                return 401, {"error": "연결 코드가 맞지 않아요."}, {}
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).hexdigest()
            with self.store.db:
                self.store.db.execute("DELETE FROM mobile_sessions WHERE expires<=?", (time.time(),))
                self.store.db.execute("INSERT INTO mobile_sessions VALUES (?,?)", (digest, time.time() + 30 * 86400))
            return 200, {"ok": True}, {"Set-Cookie": f"{COOKIE}={token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=2592000"}
        session = self.session(cookie)
        if not session:
            return 401, {"error": "맥 앱에 표시된 연결 코드를 입력해주세요."}, {}
        if method == "GET" and path.startswith("/api/media/image/"):
            try:
                image = self.store.media_image(path.rsplit("/",1)[-1])
            except ValueError:
                return 404, {"error":"이미지를 찾을 수 없어요."}, {}
            return 200, image, {"Content-Type":"image/png"}
        if method == "POST" and path == "/api/media/add":
            from chat_media import normalize_image
            try:
                raw = base64.b64decode(data.get("image", ""),validate=True)
            except (ValueError,TypeError):
                raise ValueError("이미지를 읽지 못했어요.")
            asset_id = self.store.add_media(data.get("kind"),data.get("name"),normalize_image(raw))
            self.companion.panel.refresh_messages()
            return 200, {"id":asset_id}, {}
        if method == "POST" and path == "/api/media/delete":
            asset_id = data.get("id")
            if not isinstance(asset_id,str):raise ValueError("이미지를 선택해주세요.")
            self.store.archive_media(asset_id)
            return 200, {"ok":True}, {}
        if method == "POST" and path == "/api/sticker":
            asset_id = data.get("id")
            if not isinstance(asset_id,str):raise ValueError("스티커를 선택해주세요.")
            self.companion.send_sticker(asset_id)
            return 200, {"ok":True}, {}
        if method == "GET" and path == "/api/theme.css":
            from appearance import style
            css = style((ROOT / "mobile/style.css").read_text(encoding="utf-8"), self.store.get("theme_color", "#d64289"))
            return 200, css.encode(), {"Content-Type": "text/css; charset=utf-8"}
        if method == "GET" and path == "/api/avatar":
            raw = self.store.get("avatar_png")
            if raw:
                image = base64.b64decode(raw)
            else:
                from PySide6.QtCore import QByteArray, QBuffer, QIODevice
                data = QByteArray()
                buffer = QBuffer(data)
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                self.companion.pet.image.save(buffer, "PNG")
                image = bytes(data)
            return 200, image, {"Content-Type": "image/png"}
        if method == "POST" and path == "/api/search/settings":
            enabled = data.get("enabled")
            if type(enabled) is not bool:
                raise ValueError("검색 사용 여부를 확인해주세요.")
            self.store.set("web_search_enabled", "1" if enabled else "0")
            self.companion.panel.web_search.setChecked(enabled)
            return 200, {"ok": True}, {}
        if method == "POST" and path == "/api/appearance":
            self.companion.save_appearance(data.get("name"), data.get("color"))
            return 200, {"ok": True}, {}
        if method == "GET" and path == "/api/subtasks":
            from urllib.parse import parse_qs
            parent_id = parse_qs(url.query).get("parent", [None])[0]
            return 200, {"subtasks": self.store.subtasks(parent_id)}, {}
        if method == "POST" and path == "/api/subtask":
            items = self.store.change_subtask(data.get("parent"), data.get("action"), subtask_id=data.get("id"), title=data.get("title"), direction=data.get("direction"))
            self.companion.panel.refresh()
            return 200, {"subtasks": items}, {}
        if method == "POST" and path == "/api/diary/draft":
            if self.companion.busy:
                return 409, {"error": "AI 작업이 끝난 뒤 요청해주세요."}, {}
            self.companion.generate_diary_draft(data.get("date"))
            return 202, {"ok": True}, {}
        if method == "POST" and path == "/api/diary/draft/apply":
            self.companion.apply_diary_draft()
            return 200, {"ok": True}, {}
        if method == "POST" and path == "/api/diary/draft/dismiss":
            self.companion.dismiss_diary_draft()
            return 200, {"ok": True}, {}
        if path in ("/api/diary", "/api/diary/list", "/api/diary/delete", "/api/diary/export", "/api/week"):
            from urllib.parse import parse_qs
            query = parse_qs(url.query)
            if method == "GET" and path == "/api/diary/export":
                format = query.get("format", ["json"])[0]
                body = self.store.export_diary(format).encode("utf-8")
                extension = "json" if format == "json" else "md"
                return 200, body, {"Content-Type": "application/json; charset=utf-8" if format == "json" else "text/markdown; charset=utf-8", "Content-Disposition": f'attachment; filename="DailyHelpMe-diary.{extension}"'}
            if method == "GET" and path == "/api/week":
                from calendar_data import week_data
                return 200, week_data(self.store.items(), query.get("date", [now_kst().date().isoformat()])[0]), {}
            if method == "GET" and path == "/api/diary/list":
                entries = [{key: entry[key] for key in ("date", "title", "weather", "mood", "tags")} | {"preview": " ".join(entry["content"].split())[:90]}
                           for entry in self.store.diary_entries(query.get("tag", [None])[0])]
                return 200, {"entries": entries, "tags": self.store.diary_tag_counts()}, {}
            if method == "GET" and path == "/api/diary":
                from store import MOODS, WEATHERS
                return 200, {"entry": self.store.diary_entry(query.get("date", [now_kst().date().isoformat()])[0]), "weathers": WEATHERS, "moods": MOODS}, {}
            if method == "POST" and path == "/api/diary":
                entry = self.store.save_diary(data.get("date"), data.get("title"), data.get("content"), weather=data.get("weather"), mood=data.get("mood"), tags=data.get("tags"))
                return 200, {"entry": entry}, {}
            if method == "POST" and path == "/api/diary/delete":
                self.store.delete_diary(data.get("date"))
                return 200, {"ok": True}, {}
        if method == "GET" and path == "/api/state":
            from calendar_data import today_items
            from urllib.parse import parse_qs
            limit = min(1000, max(50, int(parse_qs(url.query).get("limit", [100])[0])))
            from appearance import read_appearance
            return 200, {"media": self.store.media_assets(include_archived=True), "webSearchEnabled": self.store.get("web_search_enabled", "1") == "1", "appearance": read_appearance(self.store), "now": now_kst().isoformat(), "messages": self.store.history(limit), "bookmarks": self.store.bookmarks(),
                         "items": self.store.items(), "todayItems": today_items(self.store.items(), now_kst().date().isoformat()), "profile": self.store.get("profile"),
                         "diaryDraft": ({k: self.companion.diary_draft[k] for k in ("date", "content")} if self.companion.diary_draft else None),
                         "diaryDraftStatus": self.companion.diary_draft_status, "busy": self.companion.busy, "error": self.companion.mobile_reply_error, "pushError": self.last_error}, {}
        if method == "POST" and path == "/api/chat":
            text = data.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 8000:
                raise ValueError()
            if self.companion.busy:
                return 409, {"error": "답장을 먼저 기다려주세요."}, {}
            self.companion.send_text(text)
            return 202, {"ok": True}, {}
        if method == "POST" and path == "/api/retry":
            if self.companion.busy or not self.companion.retry_available:
                return 409, {"error": "다시 보낼 메시지가 없어요."}, {}
            self.companion.retry()
            return 202, {"ok": True}, {}
        if method == "POST" and path == "/api/logout":
            with self.store.db:
                self.store.db.execute("DELETE FROM mobile_sessions WHERE token=?", (session,))
                self.store.db.execute("DELETE FROM mobile_push WHERE session=?", (session,))
            return 200, {"ok": True}, {"Set-Cookie": f"{COOKIE}=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0"}
        if method == "POST" and path == "/api/confirm":
            self.store.confirm(int(data["id"]))
        elif method == "POST" and path == "/api/bookmark":
            self.companion.toggle_bookmark(data.get("id"))
        elif method == "POST" and path == "/api/push/subscribe":
            subscription = data.get("subscription")
            if not isinstance(subscription, dict) or not valid_endpoint(subscription.get("endpoint")):
                raise ValueError()
            keys = subscription.get("keys", {})
            if not isinstance(keys.get("p256dh"), str) or not isinstance(keys.get("auth"), str):
                raise ValueError()
            if len(base64.urlsafe_b64decode(keys["p256dh"] + "==")) != 65 or len(base64.urlsafe_b64decode(keys["auth"] + "==")) != 16:
                raise ValueError()
            with self.store.db:
                self.store.db.execute("INSERT OR REPLACE INTO mobile_push VALUES (?,?,?)", (subscription["endpoint"], session, json.dumps(subscription)))
        elif method == "GET" and path == "/api/push/key":
            return 200, {"publicKey": self.vapid_key()}, {}
        elif method == "POST" and path == "/api/push/test":
            if not self.store.db.execute("SELECT 1 FROM mobile_push WHERE session=?", (session,)).fetchone():
                return 400, {"error": "먼저 이 기기에서 알림을 켜주세요."}, {}
            if self.push_pending:
                return 409, {"error": "알림을 보내는 중이에요."}, {}
            self.notify(["모바일 알림 테스트예요."], session=session)
        elif method == "POST" and path in ("/api/item", "/api/toggle", "/api/delete", "/api/profile"):
            if self.companion.busy:
                return 409, {"error": "답장을 받은 뒤 수정해주세요."}, {}
            if path == "/api/item":
                self.store.apply_reply({"reply": "기억해뒀어요.", "operations": [data["operation"]]})
            elif path == "/api/toggle":
                self.store.toggle_completed(str(data["id"]))
            elif path == "/api/delete":
                self.store.delete(str(data["id"]))
            else:
                if not isinstance(data.get("profile"), str) or len(data["profile"]) > 30000:
                    raise ValueError()
                self.store.set("profile", data["profile"])
            self.companion.panel.refresh()
        else:
            return 404, {"error": "not found"}, {}
        return 200, {"ok": True}, {}

    def vapid_key(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        private = self.store.get("mobile_vapid")
        if private:
            key = serialization.load_der_private_key(base64.urlsafe_b64decode(private + "=="), password=None)
        else:
            key = ec.generate_private_key(ec.SECP256R1())
            private = encode(key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
            self.store.set("mobile_vapid", private)
        return encode(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))

    def notify(self, texts, session=None):
        if not texts or self.closed or self.store.get("mobile_enabled") != "1":
            return
        if self.push_pending:
            self.notifications.append((texts, session))
            return
        rows = self.store.db.execute("SELECT * FROM mobile_push" + (" WHERE session=?" if session else ""), (session,) if session else ()).fetchall()
        if not rows:
            return
        self.vapid_key()
        self.push_pending = True
        private = self.store.get("mobile_vapid")
        subscriptions = [dict(row) for row in rows]
        companion_name = self.store.get("companion_name", "봉고캣")
        def send():
            from pywebpush import webpush, WebPushException
            expired = []
            failed = 0
            for row in subscriptions:
                try:
                    webpush(subscription_info=json.loads(row["subscription"]),
                            data=json.dumps({"title": companion_name, "body": "\n".join(texts)[:600], "url": "/"}, ensure_ascii=False),
                            vapid_private_key=private, vapid_claims={"sub": "mailto:doa@localhost.local"}, ttl=3600, timeout=10)
                except WebPushException as error:
                    status = getattr(getattr(error, "response", None), "status_code", None)
                    if status in (404, 410):
                        expired.append(row["endpoint"])
                    else:
                        failed += 1
                except Exception:
                    failed += 1
            if not self.closed:
                self.push_result.emit((expired, failed))
        self.executor.submit(send)

    def handle_push_result(self, result):
        expired, failed = result
        with self.store.db:
            for endpoint in expired:
                self.store.db.execute("DELETE FROM mobile_push WHERE endpoint=?", (endpoint,))
        self.push_pending = False
        self.last_error = "모바일 알림 발송에 실패했어요. 인터넷 연결과 알림 등록을 확인해주세요." if failed else ""
        if self.notifications:
            texts, session = self.notifications.pop(0)
            self.notify(texts, session)
