import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop/python"))
import speech


class SpeechTests(unittest.TestCase):
    @patch.object(speech, "build_opener")
    def test_resolves_voice_and_sends_japanese(self, build):
        wav = b"RIFF\x00\x00\x00\x00WAVEdata"
        build.return_value.open.side_effect = [
            io.BytesIO(json.dumps([{"name": speech.VOICE, "styles": [{"name": "ノーマル", "id": 88}]}]).encode()),
            io.BytesIO(b'{"speedScale": 1}'), io.BytesIO(wav),
        ]
        self.assertEqual(speech.synthesize("こんにちは！"), wav)
        requests = build.return_value.open.call_args_list
        self.assertIn("speaker=88", requests[1].args[0].full_url)
        self.assertIn("%E3", requests[1].args[0].full_url)
        self.assertEqual(json.loads(requests[2].args[0].data)["speedScale"], 1.08)

    @patch.object(speech, "build_opener")
    def test_missing_voice_does_not_synthesize(self, build):
        build.return_value.open.return_value = io.BytesIO(b'[]')
        with self.assertRaisesRegex(ValueError, speech.VOICE):
            speech.synthesize("こんにちは")
        self.assertEqual(build.return_value.open.call_count, 1)

    @patch("engine.request_reply", return_value={"speech_ja": "こんにちは"})
    @patch.object(speech, "synthesize", return_value=b"audio")
    def test_korean_reminder_is_translated_without_search(self, synthesize, reply):
        worker = speech.SpeechWorker("안녕", None, japanese=False)
        worker.run()
        synthesize.assert_called_once_with("こんにちは")
        context = reply.call_args.args[0]
        self.assertEqual(context["task"], "speech_translation")
        self.assertFalse(context["web_search_enabled"])
        self.assertNotIn("history", context)

    def test_empty_translation_rejected(self):
        with self.assertRaises(ValueError):
            speech.synthesize("")
