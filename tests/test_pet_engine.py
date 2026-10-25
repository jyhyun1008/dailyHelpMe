import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop/python"))
import engine


class EngineTests(unittest.TestCase):
    def test_api_keys_not_forwarded(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret", "CODEX_API_KEY": "secret", "DOA_TEST": "ok"}):
            env = engine.clean_env()
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("CODEX_API_KEY", env)
        self.assertEqual(env["DOA_TEST"], "ok")

    @patch.object(engine, "codex_binary", return_value="codex")
    @patch.object(engine.subprocess, "run")
    def test_api_login_is_rejected(self, run, binary):
        run.return_value = subprocess.CompletedProcess([], 0, "Logged in using an API key", "")
        self.assertFalse(engine.login_status())
        with self.assertRaisesRegex(RuntimeError, "ChatGPT"):
            engine.request_reply({})
        self.assertEqual(run.call_count, 2)  # Login checks only; no inference.

    @patch.object(engine, "login_status", return_value=True)
    @patch.object(engine, "codex_binary", return_value="codex")
    @patch.object(engine.subprocess, "run")
    def test_translation_schema_only_for_enabled_chat(self, run, binary, status):
        for context, enabled in [({}, False), ({"speech_enabled": True}, True),
                                 ({"speech_enabled": True, "task": "diary_draft"}, False)]:
            def fake(command, **kwargs):
                schema = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
                self.assertEqual("speech_ja" in schema["required"], enabled)
                Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps({"reply": "안녕", "operations": []}))
                return subprocess.CompletedProcess(command, 0, "", "")
            run.side_effect = fake
            engine.request_reply(context)
        self.assertNotIn("speech_ja", engine.SCHEMA["properties"])

    @patch.object(engine, "login_status", return_value=True)
    @patch.object(engine, "codex_binary", return_value="codex")
    @patch.object(engine.subprocess, "run")
    def test_search_settings_and_diary_isolation(self, run, binary, status):
        for context, enabled in [({}, True), ({"web_search_enabled": False}, False), ({"task": "diary_draft", "web_search_enabled": True}, False), ({"task": "speech_translation", "speech_enabled": True}, False)]:
            with self.subTest(context=context):
                def fake(command, **kwargs):
                    self.assertIn('web_search="live"' if enabled else 'web_search="disabled"', command)
                    self.assertIn('"web_search_enabled": ' + str(enabled).lower(), kwargs["input"])
                    Path(command[command.index("--output-last-message")+1]).write_text(json.dumps({"reply": "답변", "operations": []}))
                    return subprocess.CompletedProcess(command, 0, "", "")
                run.side_effect = fake
                self.assertEqual(engine.request_reply(context)["operations"], [])

    @patch.object(engine, "login_status", return_value=True)
    @patch.object(engine, "codex_binary", return_value="codex")
    @patch.object(engine.subprocess, "run")
    def test_structured_reply_uses_empty_directory_and_chatgpt(self, run, binary, status):
        def fake(command, **kwargs):
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(json.dumps({"reply": "안녕하세요", "operations": []}))
            self.assertIn("--ignore-user-config", command)
            self.assertIn('--ephemeral', command)
            self.assertIn('forced_login_method="chatgpt"', command)
            self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
            self.assertIn("doa-chat-", str(kwargs["cwd"]))
            self.assertIn("안녕", kwargs["input"])
            return subprocess.CompletedProcess(command, 0, "", "")
        run.side_effect = fake
        self.assertEqual(engine.request_reply({"text": "안녕"})["reply"], "안녕하세요")

    @patch.object(engine, "login_status", return_value=True)
    @patch.object(engine, "codex_binary", return_value="codex")
    @patch.object(engine.subprocess, "run", side_effect=subprocess.TimeoutExpired("codex", 180))
    def test_timeout_is_actionable(self, run, binary, status):
        with self.assertRaisesRegex(RuntimeError, "초과"):
            engine.request_reply({})


if __name__ == "__main__":
    unittest.main()
