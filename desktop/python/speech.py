"""Local VOICEVOX synthesis and nonblocking macOS playback."""
import json
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler

from PySide6.QtCore import QObject, QProcess, QThread, Signal

BASE = "http://127.0.0.1:50021"
VOICE = "春日部つむぎ"


def synthesize(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 5000:
        raise ValueError("읽을 일본어 문장이 없거나 너무 길어요.")
    opener = build_opener(ProxyHandler({}))

    def request(path, data=None):
        req = Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
        with opener.open(req, timeout=15) as response:
            return response.read()

    speakers = json.loads(request("/speakers"))
    speaker = next((s for s in speakers if s["name"] == VOICE), None)
    if speaker is None:
        raise ValueError("VOICEVOX에 春日部つむぎ 음성이 필요해요.")
    style = next((s for s in speaker["styles"] if s["name"] == "ノーマル"), None)
    if style is None:
        raise ValueError("春日部つむぎ의 ノーマル 스타일을 찾지 못했어요.")
    query = json.loads(request("/audio_query?" + urlencode({"text": text, "speaker": style["id"]}), b""))
    query["speedScale"] = 1.08
    audio = request("/synthesis?" + urlencode({"speaker": style["id"]}), json.dumps(query).encode())
    if not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
        raise ValueError("음성 데이터를 읽지 못했어요.")
    return audio


class SpeechWorker(QThread):
    ready = Signal(bytes)
    failed = Signal(str)

    def __init__(self, text, parent, japanese=True):
        super().__init__(parent)
        self.text = text
        self.japanese = japanese

    def run(self):
        try:
            text = self.text
            if not self.japanese:
                from engine import request_reply
                result = request_reply({"task": "speech_translation", "speech_enabled": True,
                                        "web_search_enabled": False, "current_request": text})
                text = result.get("speech_ja", "")
            self.ready.emit(synthesize(text))
        except Exception:
            self.failed.emit("음성을 만들지 못했어요. VOICEVOX 실행·春日部つむぎ 음성·ChatGPT 연결을 확인해주세요.")


class SpeechPlayer(QObject):
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.generation = 0
        self.cache = {}
        self.pending = None
        self.closing = False
        self.directory = tempfile.TemporaryDirectory(prefix="doa-speech-")
        self.path = Path(self.directory.name) / "voice.wav"
        self.process = QProcess(self)
        self.process.finished.connect(lambda *_: self.path.unlink(missing_ok=True))
        self.process.errorOccurred.connect(lambda *_: self.status.emit("음성 재생에 실패했어요."))

    def stop(self):
        self.generation += 1
        self.pending = None
        self.process.kill()
        self.process.waitForFinished(1000)
        self.path.unlink(missing_ok=True)
        self.status.emit("")

    def speak(self, text, japanese=True):
        self.stop()
        if not isinstance(text, str) or not text.strip() or len(text) > 5000:
            self.status.emit("읽을 문장이 없거나 너무 길어요.")
            return
        if self.closing:
            return
        if self.worker is not None:
            self.pending = (text, japanese)
            self.status.emit("이전 음성 준비가 끝나면 재생할게요…")
            return
        key = (text, japanese)
        if key in self.cache:
            self.play(self.cache[key])
            return
        generation = self.generation
        self.worker = SpeechWorker(text, self, japanese)
        self.worker.ready.connect(lambda audio: self.accept_audio(key, audio, generation))
        self.worker.failed.connect(lambda message: self.status.emit(message) if generation == self.generation else None)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.finished.connect(self.clear_worker)
        self.status.emit("일본어 음성을 준비하고 있어요…")
        self.worker.start()

    def accept_audio(self, key, audio, generation):
        if self.closing:
            return
        if len(self.cache) >= 8:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = audio
        if generation == self.generation:
            self.play(audio)

    def clear_worker(self):
        self.worker = None
        pending, self.pending = self.pending, None
        if pending and not self.closing:
            self.speak(*pending)

    def play(self, audio):
        self.path.write_bytes(audio)
        self.process.start("/usr/bin/afplay", [str(self.path)])
        self.status.emit("")

    def close(self):
        self.closing = True
        self.stop()
        if self.worker:
            self.worker.wait()
        self.cache.clear()
        self.directory.cleanup()
