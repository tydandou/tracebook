import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "tracebook"
HOOK_PATH = PLUGIN_ROOT / "hooks" / "tracebook_hook.py"

SPEC = importlib.util.spec_from_file_location("tracebook_hook", HOOK_PATH)
assert SPEC is not None and SPEC.loader is not None
HOOK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HOOK)


class HookTest(unittest.TestCase):
    def test_hook_config_uses_default_plugin_location_and_safe_events(self) -> None:
        config = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))

        self.assertEqual({"UserPromptSubmit", "Stop"}, set(config["hooks"]))
        for event in config["hooks"].values():
            handler = event[0]["hooks"][0]
            self.assertEqual("command", handler["type"])
            self.assertIn("PLUGIN_ROOT", handler["command"])
            self.assertIn("PLUGIN_ROOT", handler["commandWindows"])
            self.assertLessEqual(handler["timeout"], 5)

    def test_non_git_directory_is_ignored(self) -> None:
        with TemporaryDirectory() as temp:
            payload = {"cwd": temp, "hook_event_name": "UserPromptSubmit"}
            self.assertIsNone(HOOK.build_output(payload))

    def test_repository_events_emit_non_blocking_gate_messages(self) -> None:
        with patch.object(HOOK, "_inside_git_work_tree", return_value=True):
            start = HOOK.build_output({"cwd": str(ROOT), "hook_event_name": "UserPromptSubmit"})
            stop = HOOK.build_output({"cwd": str(ROOT), "hook_event_name": "Stop"})

        self.assertEqual(True, start["continue"])
        self.assertIn("resolve/read", start["systemMessage"])
        self.assertIn("user-disabled", start["systemMessage"])
        self.assertEqual(True, stop["continue"])
        self.assertIn("final gate", stop["systemMessage"])
        self.assertNotIn("stopReason", stop)

    def test_unknown_event_is_ignored(self) -> None:
        with patch.object(HOOK, "_inside_git_work_tree", return_value=True):
            self.assertIsNone(HOOK.build_output({"cwd": str(ROOT), "hook_event_name": "SessionStart"}))


if __name__ == "__main__":
    unittest.main()
