import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "tracebook"
HOOK_PATH = PLUGIN_ROOT / "hooks" / "tracebook_hook.py"
WINDOWS_HOOK_PATH = PLUGIN_ROOT / "hooks" / "tracebook_hook.ps1"

SPEC = importlib.util.spec_from_file_location("tracebook_hook", HOOK_PATH)
assert SPEC is not None and SPEC.loader is not None
HOOK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HOOK)


class HookTest(unittest.TestCase):
    def test_hook_config_uses_default_plugin_location_and_safe_events(self) -> None:
        config = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))

        self.assertEqual({"UserPromptSubmit", "Stop"}, set(config["hooks"]))
        for event_name, event in config["hooks"].items():
            handler = event[0]["hooks"][0]
            self.assertEqual("command", handler["type"])
            self.assertIn("PLUGIN_ROOT", handler["command"])
            self.assertIn("PLUGIN_ROOT", handler["commandWindows"])
            self.assertIn("SystemRoot", handler["commandWindows"])
            self.assertIn("tracebook_hook.ps1", handler["commandWindows"])
            self.assertIn(f"-HookEvent {event_name}", handler["commandWindows"])
            self.assertLessEqual(handler["timeout"], 5)
        self.assertTrue(WINDOWS_HOOK_PATH.is_file())

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
        self.assertIn("deterministic context retrieval", start["systemMessage"])
        self.assertEqual(True, stop["continue"])
        self.assertIn("final reminder", stop["systemMessage"])
        self.assertIn("no skip report", stop["systemMessage"])
        self.assertNotIn("stopReason", stop)

    def test_unknown_event_is_ignored(self) -> None:
        with patch.object(HOOK, "_inside_git_work_tree", return_value=True):
            self.assertIsNone(HOOK.build_output({"cwd": str(ROOT), "hook_event_name": "SessionStart"}))

    @staticmethod
    def _windows_hook_environment(*, include_git: bool) -> dict[str, str]:
        system_root = os.environ["SystemRoot"]
        environment = os.environ.copy()
        environment["ComSpec"] = os.environ.get("ComSpec", str(Path(system_root) / "System32" / "cmd.exe"))
        environment["SystemRoot"] = system_root
        environment["PATH"] = str(Path(system_root) / "System32")
        environment["PATHEXT"] = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD")
        if include_git:
            git_path = shutil.which("git")
            if git_path is None:
                raise unittest.SkipTest("git is unavailable for the Windows Hook process test")
            environment["PATH"] += os.pathsep + str(Path(git_path).parent)
        return environment

    @staticmethod
    def _run_windows_hook(
        payload: object,
        *,
        plugin_root: Path = PLUGIN_ROOT,
        include_git: bool = True,
        raw_input: str | None = None,
        event: str = "UserPromptSubmit",
        cwd: Path = ROOT,
    ) -> subprocess.CompletedProcess[str]:
        config = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        command = config["hooks"][event][0]["hooks"][0]["commandWindows"]
        environment = HookTest._windows_hook_environment(include_git=include_git)
        environment["PLUGIN_ROOT"] = str(plugin_root)
        return subprocess.run(
            f'"{environment["ComSpec"]}" /d /c {command}',
            input=raw_input if raw_input is not None else json.dumps(payload),
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="strict",
            env=environment,
            cwd=cwd,
            timeout=5,
        )

    @unittest.skipUnless(os.name == "nt", "Windows-only Hook process test")
    def test_windows_hook_uses_no_python_path_and_matches_python_semantics(self) -> None:
        for event in ("UserPromptSubmit", "Stop"):
            payload = {"cwd": str(ROOT), "hook_event_name": event}
            result = self._run_windows_hook(payload, event=event)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stderr)
            self.assertNotEqual("", result.stdout, f"stdout was empty: returncode={result.returncode}")
            self.assertEqual(
                HOOK.build_output(payload),
                json.loads(result.stdout),
            )

    @unittest.skipUnless(os.name == "nt", "Windows-only Hook process test")
    def test_windows_hook_ignores_invalid_stdin_and_uses_explicit_event(self) -> None:
        payload = {"cwd": str(ROOT), "hook_event_name": "UserPromptSubmit"}
        for raw_input in ("", "not-json", '{"cwd":"unterminated'):
            result = self._run_windows_hook(payload, raw_input=raw_input)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stderr)
            self.assertNotEqual("", result.stdout)
            self.assertEqual(HOOK.build_output(payload), json.loads(result.stdout))

    @unittest.skipUnless(os.name == "nt", "Windows-only Hook process test")
    def test_windows_hook_fails_open_for_invalid_and_missing_prerequisites(self) -> None:
        with TemporaryDirectory() as temp:
            result = self._run_windows_hook(
                {"cwd": temp, "hook_event_name": "UserPromptSubmit"},
                raw_input="not-json",
                cwd=Path(temp),
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout)
            self.assertEqual("", result.stderr)

        result = self._run_windows_hook(
            {"cwd": str(ROOT), "hook_event_name": "UserPromptSubmit"},
            include_git=False,
            raw_input="not-json",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)
        self.assertEqual("", result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows-only Hook process test")
    def test_windows_hook_supports_plugin_roots_with_spaces(self) -> None:
        with TemporaryDirectory() as temp:
            plugin_root = Path(temp) / "plugin root with spaces"
            shutil.copytree(PLUGIN_ROOT / "hooks", plugin_root / "hooks")
            payload = {"cwd": str(ROOT), "hook_event_name": "UserPromptSubmit"}
            result = self._run_windows_hook(payload, plugin_root=plugin_root, raw_input="not-json")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotEqual("", result.stdout, f"stdout was empty: returncode={result.returncode}")
            self.assertEqual(HOOK.build_output(payload), json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
