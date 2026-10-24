"""Local DOA memory and reminders. No web server or account database required."""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
KINDS = {"todo": "데드라인", "bucket": "버킷리스트", "routine": "루틴", "schedule": "일정"}
WEATHERS = ["☀️ 맑음", "⛅ 구름 조금", "☁️ 흐림", "🌧️ 비", "⛈️ 천둥번개", "❄️ 눈", "🌫️ 안개", "💨 바람"]
MOODS = ["😊 좋음", "🥰 행복", "😌 평온", "😐 그저 그럼", "😴 피곤", "😢 슬픔", "😰 불안", "😠 화남"]


def now_kst():
    return datetime.now(KST)


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("시간은 ISO 형식 문자열이어야 합니다.")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("시간대가 포함된 날짜와 시간이 필요합니다.")
    return result.astimezone(KST)


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL,
                created_at TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                at TEXT, days TEXT NOT NULL DEFAULT '[]', time TEXT,
                done INTEGER NOT NULL DEFAULT 0, completed_day TEXT);
            CREATE TABLE IF NOT EXISTS subtasks (
                id TEXT PRIMARY KEY, parent_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                title TEXT NOT NULL, position INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0,
                completed_day TEXT);
            CREATE INDEX IF NOT EXISTS subtasks_parent ON subtasks(parent_id, position);
            CREATE TABLE IF NOT EXISTS chat_media (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
                png BLOB NOT NULL, active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS message_stickers (
                message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
                media_id TEXT NOT NULL REFERENCES chat_media(id));
            CREATE TABLE IF NOT EXISTS message_items (
                message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                item_id TEXT NOT NULL, title TEXT NOT NULL, kind TEXT NOT NULL,
                PRIMARY KEY(message_id,item_id));
            CREATE TABLE IF NOT EXISTS diary (
                date TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reminders (key TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS bookmarks (
                message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL);
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(diary)")}
        for column, definition in (("weather", "TEXT NOT NULL DEFAULT ''"), ("mood", "TEXT NOT NULL DEFAULT ''"), ("tags", "TEXT NOT NULL DEFAULT '[]'")):
            if column not in columns:
                self.db.execute(f"ALTER TABLE diary ADD COLUMN {column} {definition}")
        self.db.commit()
        path.chmod(0o600)

    def get(self, key, default=""):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def _set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, str(value)))

    def set(self, key, value):
        with self.db:
            self._set(key, value)

    def _message(self, role, content, now):
        cursor = self.db.execute("INSERT INTO messages(role,content,created_at) VALUES (?,?,?)",
                        (role, content, now.isoformat()))
        if role == "user":
            self._set("last_seen", now.isoformat())
        return cursor.lastrowid

    def message(self, role, content, now=None):
        with self.db:
            self._message(role, content, now or now_kst())

    def history(self, limit=80, before=None):
        rows = self.db.execute("SELECT * FROM messages WHERE id < ? ORDER BY id DESC LIMIT ?",
                               (before if before is not None else 9223372036854775807, limit)).fetchall()
        result = [dict(row) for row in reversed(rows)]
        if result:
            links = {}
            placeholders = ",".join("?" for _ in result)
            for row in self.db.execute(f"SELECT m.*, i.id IS NOT NULL AS available, COALESCE(i.title,m.title) AS current_title FROM message_items m LEFT JOIN items i ON i.id=m.item_id WHERE m.message_id IN ({placeholders}) ORDER BY m.rowid", [m["id"] for m in result]):
                links.setdefault(row["message_id"], []).append({"id": row["item_id"], "title": row["current_title"], "kind": row["kind"], "available": bool(row["available"])})
            for message in result:
                message["created_items"] = links.get(message["id"], [])
        if result:
            stickers = {row["message_id"]: {"id": row["id"], "name": row["name"]} for row in self.db.execute(
                f"SELECT s.message_id,m.id,m.name FROM message_stickers s JOIN chat_media m ON m.id=s.media_id WHERE s.message_id IN ({placeholders})", [m["id"] for m in result])}
            for message in result:
                if message["id"] in stickers:
                    message["sticker"] = stickers[message["id"]]
            marked = {row[0] for row in self.db.execute(f"SELECT message_id FROM bookmarks WHERE message_id IN ({placeholders})", [m["id"] for m in result])}
            for message in result:
                message["bookmarked"] = message["id"] in marked
        return result

    def toggle_bookmark(self, message_id):
        if type(message_id) is not int or not self.db.execute("SELECT 1 FROM messages WHERE id=?", (message_id,)).fetchone():
            raise ValueError("북마크할 말풍선을 찾을 수 없어요.")
        with self.db:
            if not self.db.execute("DELETE FROM bookmarks WHERE message_id=?", (message_id,)).rowcount:
                self.db.execute("INSERT INTO bookmarks VALUES (?,?)", (message_id, now_kst().isoformat()))

    def bookmarks(self):
        rows = self.db.execute("SELECT m.id,m.role,m.content,m.created_at,b.created_at AS bookmarked_at FROM bookmarks b "
                               "JOIN messages m ON m.id=b.message_id ORDER BY b.created_at DESC, m.id DESC").fetchall()
        return [dict(row) for row in rows]

    def media_assets(self, include_archived=False):
        return [dict(row) for row in self.db.execute("SELECT id,kind,name,active FROM chat_media" + ("" if include_archived else " WHERE active=1") + " ORDER BY rowid")]

    def media_image(self, asset_id):
        row = self.db.execute("SELECT png FROM chat_media WHERE id=?", (asset_id,)).fetchone()
        if not row:
            raise ValueError("이미지를 찾을 수 없어요.")
        return bytes(row[0])

    def add_media(self, kind, name, png):
        if kind not in ("emoji", "sticker") or not isinstance(name,str) or not name.strip() or len(name.strip()) > 40:
            raise ValueError("종류와 이름(40자 이하)을 확인해주세요.")
        if not isinstance(png,bytes) or len(png)>4*1024*1024 or not (png.startswith(b"\x89PNG\r\n\x1a\n") or png.startswith((b"GIF87a", b"GIF89a")) or (png.startswith(b"RIFF") and png[8:12] == b"WEBP")):
            raise ValueError("올바른 이미지를 선택해주세요.")
        if len(self.media_assets()) >= 200:
            raise ValueError("이모지와 스티커는 합쳐서 200개까지 등록할 수 있어요.")
        asset_id = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO chat_media(id,kind,name,png) VALUES (?,?,?,?)", (asset_id,kind,name.strip(),png))
        return asset_id

    def rename_media(self, asset_id, name):
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 40:
            raise ValueError('이름은 1~40자로 입력해주세요.')
        with self.db:
            if not self.db.execute("UPDATE chat_media SET name=? WHERE id=? AND active=1", (name.strip(), asset_id)).rowcount:
                raise ValueError('등록된 이미지를 찾을 수 없어요.')

    def archive_media(self, asset_id):
        with self.db:
            self.db.execute("UPDATE chat_media SET active=0 WHERE id=?", (asset_id,))

    def send_sticker(self, asset_id):
        row = self.db.execute("SELECT name FROM chat_media WHERE id=? AND kind='sticker' AND active=1", (asset_id,)).fetchone()
        if not row:
            raise ValueError("등록된 스티커를 선택해주세요.")
        with self.db:
            message_id = self._message("user", "[스티커: " + row["name"] + "]", now_kst())
            self.db.execute("INSERT INTO message_stickers VALUES (?,?)", (message_id,asset_id))
        return message_id

    def ai_history(self, history):
        names = {m["id"]:m["name"] for m in self.media_assets(include_archived=True)}
        pattern = re.compile(r':emoji_([a-f0-9]{32}):')
        return [dict(role=m["role"], content=pattern.sub(lambda match: "[이모지: " + names.get(match[1], "알 수 없음") + "]", m["content"]), created_at=m["created_at"]) for m in history if not m.get("sticker")]

    def confirm(self, message_id):
        with self.db:
            self.db.execute("UPDATE messages SET confirmed=1-confirmed WHERE id=? AND role='assistant'", (message_id,))

    def items(self, now=None):
        rows = self.db.execute("SELECT * FROM items ORDER BY done, at, title").fetchall()
        day = ((now or now_kst()) - timedelta(hours=5)).date().isoformat()
        counts = {row["parent_id"]: row for row in self.db.execute("""
            SELECT s.parent_id, COUNT(*) AS total,
            SUM(CASE WHEN i.kind='routine' THEN s.completed_day=? ELSE s.done END) AS completed
            FROM subtasks s JOIN items i ON i.id=s.parent_id GROUP BY s.parent_id
        """, (day,))}
        result = []
        for row in rows:
            item = dict(row)
            count = counts.get(item["id"])
            item["subtask_total"] = count["total"] if count else 0
            item["subtask_done"] = int(count["completed"] or 0) if count else 0
            item["days"] = json.loads(item["days"])
            result.append(item)
        return result

    @staticmethod
    def diary_date(value):
        if not isinstance(value, str) or len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            raise ValueError("일기 날짜를 확인해주세요.")
        return value

    @staticmethod
    def diary_row(row):
        entry = dict(row)
        entry["tags"] = json.loads(entry["tags"])
        return entry

    def diary_entry(self, day):
        day = self.diary_date(day)
        row = self.db.execute("SELECT * FROM diary WHERE date=?", (day,)).fetchone()
        return self.diary_row(row) if row else None

    @staticmethod
    def diary_tags(tags):
        if tags is None:
            return []
        if isinstance(tags, str):
            tags = tags.split(",")
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError("태그를 확인해주세요.")
        result = list(dict.fromkeys(tag.strip().lstrip("#").strip() for tag in tags if tag.strip().lstrip("#").strip()))
        if len(result) > 20 or any(len(tag) > 30 for tag in result):
            raise ValueError("태그는 20개, 각 30자까지 달 수 있어요.")
        return result

    def save_diary(self, day, title, content, weather=None, mood=None, tags=None):
        """Weather, mood and tags left as None keep the saved values."""
        day = self.diary_date(day)
        if not isinstance(title, str) or not isinstance(content, str) or len(title) > 200 or len(content) > 30000:
            raise ValueError("일기는 제목 200자, 본문 30,000자까지 저장할 수 있어요.")
        if any(value is not None and (not isinstance(value, str) or len(value) > 20) for value in (weather, mood)):
            raise ValueError("날씨와 기분을 확인해주세요.")
        old = self.diary_entry(day) or {"weather": "", "mood": "", "tags": []}
        weather = old["weather"] if weather is None else weather.strip()
        mood = old["mood"] if mood is None else mood.strip()
        tags = old["tags"] if tags is None else self.diary_tags(tags)
        stamp = now_kst().isoformat()
        with self.db:
            self.db.execute("INSERT INTO diary(date,title,content,created_at,updated_at,weather,mood,tags) VALUES (?,?,?,?,?,?,?,?) "
                            "ON CONFLICT(date) DO UPDATE SET title=excluded.title, content=excluded.content, updated_at=excluded.updated_at, "
                            "weather=excluded.weather, mood=excluded.mood, tags=excluded.tags",
                            (day, title.strip(), content, stamp, stamp, weather, mood, json.dumps(tags, ensure_ascii=False)))
        return self.diary_entry(day)

    def diary_entries(self, tag=None):
        entries = [self.diary_row(row) for row in self.db.execute("SELECT * FROM diary ORDER BY date DESC")]
        return [entry for entry in entries if not tag or tag in entry["tags"]]

    def diary_tag_counts(self):
        counts = {}
        for entry in self.diary_entries():
            for tag in entry["tags"]:
                counts[tag] = counts.get(tag, 0) + 1
        return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

    def delete_diary(self, day):
        with self.db:
            self.db.execute("DELETE FROM diary WHERE date=?", (self.diary_date(day),))

    def export_diary(self, format="json"):
        entries = [self.diary_row(row) for row in self.db.execute("SELECT * FROM diary ORDER BY date")]
        if format == "json":
            return json.dumps({"version": 1, "timezone": "Asia/Seoul", "entries": entries}, ensure_ascii=False, indent=2) + "\n"
        if format == "markdown":
            parts = ["# 날도와줘 일기\n"]
            for entry in entries:
                parts.append("## " + entry["date"] + (" · " + entry["title"].replace("\n", " ") if entry["title"] else ""))
                labels = [value for value in (entry["weather"], entry["mood"]) if value] + ["#" + tag for tag in entry["tags"]]
                if labels:
                    parts.append(" ".join(labels))
                parts.append(entry["content"])
                parts.append("---")
            return "\n\n".join(parts) + "\n"
        raise ValueError("지원하지 않는 내보내기 형식이에요.")

    def subtasks(self, parent_id, now=None):
        if not isinstance(parent_id, str):
            raise ValueError("1차 일정을 확인해주세요.")
        parent = self.db.execute("SELECT kind FROM items WHERE id=?", (parent_id,)).fetchone()
        if not parent:
            raise ValueError("1차 일정을 찾을 수 없어요.")
        day = ((now or now_kst()) - timedelta(hours=5)).date().isoformat()
        result = []
        for row in self.db.execute("SELECT * FROM subtasks WHERE parent_id=? ORDER BY position,id", (parent_id,)):
            item = dict(row)
            if parent["kind"] == "routine":
                item["done"] = int(item["completed_day"] == day)
            result.append(item)
        return result

    def change_subtask(self, parent_id, action, subtask_id=None, title=None, direction=None, now=None):
        if not isinstance(parent_id, str):
            raise ValueError("1차 일정을 확인해주세요.")
        parent = self.db.execute("SELECT kind FROM items WHERE id=?", (parent_id,)).fetchone()
        if not parent:
            raise ValueError("1차 일정을 먼저 저장해주세요.")
        if action not in ("add", "update", "toggle", "delete", "move"):
            raise ValueError("알 수 없는 2차 일정 변경이에요.")
        if action in ("add", "update") and (not isinstance(title, str) or not title.strip() or len(title) > 500):
            raise ValueError("2차 일정 제목은 1~500자로 적어주세요.")
        items = self.subtasks(parent_id, now)
        old = next((item for item in items if item["id"] == subtask_id), None)
        if action != "add" and old is None:
            raise ValueError("2차 일정을 찾을 수 없어요.")
        with self.db:
            if action == "add":
                position = max((item["position"] for item in items), default=-1) + 1
                self.db.execute("INSERT INTO subtasks(id,parent_id,title,position) VALUES (?,?,?,?)", (str(uuid.uuid4()), parent_id, title.strip(), position))
            elif action == "update":
                self.db.execute("UPDATE subtasks SET title=? WHERE id=?", (title.strip(), subtask_id))
            elif action == "delete":
                self.db.execute("DELETE FROM subtasks WHERE id=?", (subtask_id,))
            elif action == "toggle":
                day = ((now or now_kst()) - timedelta(hours=5)).date().isoformat()
                self.db.execute("UPDATE subtasks SET done=?,completed_day=? WHERE id=?", (not old["done"], None if old["done"] else day, subtask_id))
            elif action == "move":
                if type(direction) is not int or direction not in (-1, 1):
                    raise ValueError("이동 방향을 확인해주세요.")
                index = items.index(old)
                target = index + direction
                if 0 <= target < len(items):
                    items[index], items[target] = items[target], items[index]
                    self.db.executemany("UPDATE subtasks SET position=? WHERE id=?", [(i, item["id"]) for i, item in enumerate(items)])
        return self.subtasks(parent_id, now)

    def diary_context(self, limit=14, budget=24000):
        entries = []
        for row in self.db.execute("SELECT * FROM diary ORDER BY date DESC LIMIT ?", (limit,)):
            entry = self.diary_row(row)
            content = entry["content"][:min(4000, budget)]
            entry["truncated"] = len(content) != len(entry["content"])
            entry["content"] = content
            entries.append(entry)
            budget -= len(content)
            if budget <= 0:
                break
        return entries

    def diary_draft_context(self, day):
        day = self.diary_date(day)
        rows = self.db.execute("SELECT m.* FROM messages m WHERE substr(created_at,1,10)=? AND NOT EXISTS (SELECT 1 FROM message_stickers s WHERE s.message_id=m.id) ORDER BY id DESC LIMIT 200", (day,)).fetchall()
        history, budget = [], 24000
        for row in rows:
            message = dict(row)
            message["content"] = message["content"][:min(4000, budget)]
            history.append(message)
            budget -= len(message["content"])
            if budget <= 0:
                break
        if not any(message["role"] == "user" for message in history):
            raise ValueError("이 날짜의 대화가 없어요. 대화한 날짜를 선택해주세요.")
        return {"companion_name": self.get("companion_name", "봉고캣"), "now": now_kst().isoformat(), "task": "diary_draft", "date": day,
                "history": self.ai_history(list(reversed(history))), "existing_diary": self.diary_entry(day),
                "current_request": "이 날짜의 대화를 바탕으로 사용자의 1인칭 한국어 일기 본문 초안을 써주세요. 사용자가 실제로 말한 일과 감정만 반영하고, AI가 제안한 일을 실제로 했다고 쓰거나 모르는 사실을 만들지 마세요. 짧고 자연스럽게, 본문만 reply에 넣고 operations는 빈 배열로 반환하세요."}

    def context(self):
        return {"companion_name": self.get("companion_name", "봉고캣"), "web_search_enabled": self.get("web_search_enabled", "1") == "1", "now": now_kst().isoformat(), "profile": self.get("profile"),
                "items": self.items(), "history": self.ai_history(self.history(50)), "diaries": self.diary_context()}

    def complete(self, item_id, now=None):
        now = now or now_kst()
        with self.db:
            self._complete(item_id, now)

    def toggle_completed(self, item_id, now=None):
        now = now or now_kst()
        day = (now - timedelta(hours=5)).date().isoformat()
        with self.db:
            row = self.db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise ValueError("항목을 찾지 못했어요.")
            if row["kind"] == "routine":
                value = None if row["completed_day"] == day else day
                self.db.execute("UPDATE items SET completed_day=? WHERE id=?", (value, item_id))
            else:
                done = not row["done"]
                self.db.execute("UPDATE items SET done=?,completed_day=? WHERE id=?", (done, day if done else None, item_id))

    def _complete(self, item_id, now):
        day = (now - timedelta(hours=5)).date().isoformat()
        cursor = self.db.execute("UPDATE items SET done=CASE WHEN kind='routine' THEN 0 ELSE 1 END, "
                                 "completed_day=? WHERE id=?", (day, item_id))
        if not cursor.rowcount:
            raise ValueError("완료할 항목을 찾을 수 없어요.")

    def delete(self, item_id):
        with self.db:
            self.db.execute("DELETE FROM items WHERE id=?", (item_id,))

    def apply_reply(self, result, *, link_created=False):
        """Apply all changes and the assistant reply atomically, or none of them."""
        if not isinstance(result, dict) or not isinstance(result.get("reply"), str) or not result["reply"].strip():
            raise ValueError("답장 형식이 올바르지 않아요.")
        operations = result.get("operations")
        if not isinstance(operations, list) or len(operations) > 30:
            raise ValueError("기억 변경 목록이 올바르지 않아요.")
        now = now_kst()
        created = []
        with self.db:
            for op in operations:
                if not isinstance(op, dict):
                    raise ValueError("기억 변경 형식이 올바르지 않아요.")
                action, kind = op.get("action"), op.get("kind")
                if kind == "profile":
                    note = op.get("title")
                    if action not in ("add", "update") or not isinstance(note, str) or not note.strip():
                        raise ValueError("프로필 메모가 올바르지 않아요.")
                    previous = self.get("profile")
                    self._set("profile", (previous + "\n" + note).strip() if action == "add" else note)
                    continue
                if kind not in KINDS or action not in ("add", "update", "complete", "delete"):
                    raise ValueError("알 수 없는 기억 변경이에요.")
                item_id = op.get("id")
                old = None
                if action != "add":
                    old = self.db.execute("SELECT * FROM items WHERE id=? AND kind=?", (item_id, kind)).fetchone()
                    if not old:
                        raise ValueError("수정할 기억을 찾지 못했어요. 다시 말씀해주세요.")
                if action == "delete":
                    self.db.execute("DELETE FROM items WHERE id=?", (item_id,))
                    continue
                if action == "complete":
                    self._complete(item_id, now)
                    continue
                title = op.get("title")
                if not isinstance(title, str) or not title.strip() or len(title) > 500:
                    raise ValueError("항목 제목을 확인해주세요.")
                at, days, time = op.get("at"), op.get("days") or [], op.get("time")
                if kind in ("todo", "schedule") and at is not None:
                    at = parse_time(at).isoformat()
                if kind == "schedule" and at is None:
                    raise ValueError("일정 시간이 필요해요.")
                if kind == "routine":
                    at = None
                    if not days or any(type(d) is not int or d not in range(7) for d in days):
                        raise ValueError("루틴 요일을 확인해주세요.")
                    if not isinstance(time, str) or len(time) != 5:
                        raise ValueError("루틴 시각을 확인해주세요.")
                    datetime.strptime(time, "%H:%M")
                else:
                    time, days = None, []
                if kind == "bucket":
                    at = None
                if action == "add":
                    duplicate = self.db.execute("SELECT id FROM items WHERE kind=? AND title=? AND done=0",
                                                (kind, title.strip())).fetchone()
                    if duplicate:
                        continue
                    item_id = str(uuid.uuid4())
                    self.db.execute("INSERT INTO items(id,kind,title,at,days,time) VALUES (?,?,?,?,?,?)",
                                    (item_id, kind, title.strip(), at, json.dumps(sorted(set(days))), time))
                    created.append((item_id, title.strip(), kind))
                else:
                    self.db.execute("UPDATE items SET title=?,at=?,days=?,time=? WHERE id=?",
                                    (title.strip(), at, json.dumps(sorted(set(days))), time, item_id))
                    # An edited reminder gets a new generation without replaying unchanged reminders.
                    if old["at"] != at or old["time"] != time or json.loads(old["days"]) != sorted(set(days)):
                        self.db.execute("DELETE FROM reminders WHERE key LIKE ?", (item_id + ":%",))
            message_id = self._message("assistant", result["reply"].strip(), now)
            if link_created:
                self.db.executemany("INSERT INTO message_items(message_id,item_id,title,kind) VALUES (?,?,?,?)",
                                    [(message_id, *item) for item in created])
        return result["reply"].strip()

    def reminders(self, now=None):
        """Durably save reminder and message in the same transaction, including across restarts."""
        now = now or now_kst()
        candidates = []
        for item in self.items():
            if item["done"]:
                continue
            key = item["id"]
            kind, title = item["kind"], item["title"]
            if kind == "routine":
                day = now.date().isoformat()
                if (now.weekday() + 1) % 7 in item["days"] and item["time"] <= now.strftime("%H:%M"):
                    # Catch up today's routine after sleep, once per calendar day.
                    candidates.append((key + ":" + day, f'“{title}” 하실 시간이에요'))
            elif item["at"]:
                at = parse_time(item["at"])
                if kind == "schedule" and now >= at:
                    candidates.append((key + ":schedule", f'“{title}” 일정 시간이 되었어요!'))
                elif kind == "todo":
                    point = (at - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
                    if point <= now < at:
                        candidates.append((key + ":deadline", f'“{title}” 마감이 {at:%m월 %d일}이에요. 미리 챙겨볼까요?'))
        last_seen = self.get("last_seen")
        if last_seen and now - parse_time(last_seen) >= timedelta(hours=24):
            last_ping = self.get("last_idle")
            if not last_ping or now - parse_time(last_ping) >= timedelta(hours=24):
                candidates.append(("idle:" + now.date().isoformat(), "뭐 하고 계세요? 잠깐 이야기 나누고 싶어요"))
        sent = []
        with self.db:
            for key, text in candidates:
                cursor = self.db.execute("INSERT OR IGNORE INTO reminders VALUES (?)", (key,))
                if cursor.rowcount:
                    self._message("assistant", text, now)
                    sent.append(text)
                    if key.startswith("idle:"):
                        self._set("last_idle", now.isoformat())
        return sent
