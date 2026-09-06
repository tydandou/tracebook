"""Multi-session CLI acceptance of v4.0.8 in source and copied packages."""

from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.request_transport import encode_envelope


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "tracebook"
RUNNER_PATH = Path("skills/tracebook/scripts/tracebook_runner.py")


def fingerprint(directory):
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*") if path.is_file()}


class RetrievalCLIWorkflowTest(unittest.TestCase):
    maxDiff = None

    def run_flow(self, runner, base, mode):
        source = base / "source"
        source.mkdir()
        if mode != "plain":
            subprocess.run(["git", "init", "-q", str(source)], check=True, capture_output=True)
        if mode == "remote":
            subprocess.run(["git", "-C", str(source), "remote", "add", "origin",
                            "https://github.com/fixture/retrieval.git"], check=True, capture_output=True)
        (source / "src").mkdir()
        (source / "src/retry.py").write_text("ATTEMPTS = 2\n", encoding="utf-8")
        source_before = fingerprint(source)
        knowledge = base / "kb"
        trace = []

        def call(command, *args, request=None, expected=0):
            argv = [sys.executable, "-B", str(runner), command, "--root", str(knowledge), *args]
            completed = subprocess.run(argv, cwd=base, capture_output=True, check=False,
                                       input=encode_envelope(json.dumps(request, ensure_ascii=False).encode("utf-8"))
                                       if request is not None else None, timeout=45)
            self.assertEqual(expected, completed.returncode,
                             completed.stdout.decode("utf-8", errors="replace") +
                             completed.stderr.decode("utf-8", errors="replace"))
            result = json.loads(completed.stdout.decode("utf-8"))
            trace.append((command, args, result))
            return result

        def write(day=1, expected=0, **changes):
            request = dict(operation="create", scope="project", kind="decision",
                           knowledge_id="retry-policy", title="重试策略 Retry policy",
                           body="Legacyhandoff 使用旧规则。", evidence=["src/retry.py:L1"], status="current")
            request.update(changes)
            result = call("capture", "--cwd", str(source), "--request", "-", "--today",
                          date(2026, 9, day).isoformat(), request=request, expected=expected)
            if expected == 0 and not result["skipped"]:
                self.assertTrue(result["changed_paths"])
                self.assertIn(result["health_scope"], ("project", "domain", "pattern"))
                health_args = ["--cwd", str(source), "--source-root", str(source),
                               "--scope", result["health_scope"], "--today", "2026-09-05"]
                for path in result["changed_paths"]:
                    health_args.extend(("--changed", path))
                for path in result["new_paths"]:
                    health_args.extend(("--new-path", path))
                checked = call("check", *health_args)
                self.assertEqual([], checked["findings"]["entity_issues"])
                self.assertEqual([], checked["findings"]["missing_sources"])
                if checked["check_type"] == "Deep":
                    call("audit", "--cwd", str(source), "--source-root", str(source),
                         "--scope", result["health_scope"], "--today", "2026-09-05")
            return result

        def read(*args, cwd=source):
            before = fingerprint(knowledge)
            result = call("context-read-path", "--cwd", str(cwd), *args)
            self.assertEqual(before, fingerprint(knowledge))
            return result

        initial = call("preflight", "--cwd", str(source))
        self.assertTrue(initial["blocked"])
        self.assertFalse(knowledge.exists())
        registered = call("resolve", "--cwd", str(source))
        identity = registered["project"]["project_id"]
        self.assertTrue((knowledge / "AGENTS.md").is_file())
        self.assertFalse((knowledge / registered["project"]["relative_path"] / "AGENTS.md").exists())
        first = write()
        self.assertTrue(write()["skipped"])
        body = "规则说明。" * 110 + "当前结论 Currenthandoff：只尝试两次，失败后停止。"
        write(day=2, operation="revise", expected_version=1, body=body)
        before_rejected = fingerprint(knowledge)
        rejected = write(day=3, operation="revise", expected_version=1, body="must not overwrite", expected=2)
        self.assertIn("expected_version conflicts", str(rejected["error"]))
        self.assertEqual(before_rejected, fingerprint(knowledge))

        self.assertEqual([], read("--query", "Legacyhandoff")["current_context"])
        self.assertEqual([], read("--query", "Legacyhandoff", "--include-history")["current_context"])
        adaptive = read("--query", "Legacyhandoff", "--profile", "adaptive")
        self.assertTrue(adaptive["adaptive_history_fallback"])
        self.assertEqual([], adaptive["historical_context"])
        self.assertEqual(2, adaptive["current_context"][0]["version"])
        self.assertEqual(1, adaptive["current_context"][0]["matched_version"])
        found = read("--query", "Legacyhandoff", "--profile", "audit")
        entity, = found["current_context"]
        self.assertEqual(2, entity["version"])
        self.assertEqual(1, entity["matched_version"])
        self.assertEqual("history", entity["match_source"])
        self.assertTrue(entity["excerpt_truncated"])
        self.assertNotIn("Currenthandoff", entity["excerpt"])
        complete = read("--knowledge-id", entity["knowledge_id"], "--full-content", "--include-history")
        self.assertEqual(body, complete["current_context"][0]["body"])
        self.assertEqual(found["read_snapshots"], complete["read_snapshots"])
        self.assertEqual([1], [item["version"] for item in complete["historical_context"]])
        past = read("--query", "Legacyhandoff", "--profile", "audit", "--as-of", "2026-09-01")
        self.assertEqual(1, past["current_context"][0]["version"])
        self.assertEqual([], read("--query", "Currenthandoff", "--profile", "audit",
                                  "--as-of", "2026-09-01")["current_context"])

        # Broad matches compete; path-only follow-up isolates the governed evidence.
        write(knowledge_id="noise-policy", body="Currenthandoff Currenthandoff",
              title="Currenthandoff", evidence=["test:noise"])
        broad = read("--query", "Currenthandoff", "--max-results", "1")
        self.assertEqual("noise-policy", broad["current_context"][0]["knowledge_id"])
        self.assertTrue(broad["truncated"])
        targeted = read("--evidence-path", "src/retry.py")
        self.assertEqual(["retry-policy"], [item["knowledge_id"] for item in targeted["current_context"]])
        self.assertTrue(targeted["current_context"][0]["evidence_match"])
        tiny = read("--knowledge-id", "retry-policy", "--full-content", "--max-chars", "1")
        self.assertEqual([], tiny["current_context"])
        self.assertTrue(tiny["truncated"])
        self.assertEqual(0, tiny["budget_chars_used"])

        write(knowledge_id="pending-rule", status="pending", body="Pendingtoken", evidence=[])
        self.assertEqual([], read("--query", "Pendingtoken", "--profile", "audit")["current_context"])
        self.assertEqual(1, read("--query", "Pendingtoken", "--status", "pending")["matched_count"])
        write(day=3, operation="change-status", expected_version=1, knowledge_id="pending-rule",
              status="deprecated", body="Removedtoken")
        self.assertEqual([], read("--query", "Pendingtoken", "--profile", "audit")["current_context"])
        self.assertEqual(2, read("--query", "Pendingtoken", "--profile", "audit",
                                "--status", "deprecated")["current_context"][0]["version"])
        write(knowledge_id="successor-rule", body="Current successor rule")
        write(day=4, operation="change-status", expected_version=2, status="superseded",
              replacement_knowledge_id="successor-rule", body="Replaced by successor")
        self.assertEqual([], read("--query", "Legacyhandoff", "--profile", "audit")["current_context"])
        retired = read("--query", "Legacyhandoff", "--profile", "audit", "--status", "superseded")
        self.assertEqual("successor-rule", retired["current_context"][0]["replacement_knowledge_id"])

        for scope in ("domain", "pattern"):
            write(scope=scope, knowledge_id="shared-rule", body="sharedlegacy")
            write(day=2, scope=scope, knowledge_id="shared-rule", operation="revise",
                  expected_version=1, body="sharedcurrent")
            shared = read("--query", "sharedlegacy", "--profile", "audit", "--scope", scope)
            self.assertEqual(2, shared["current_context"][0]["version"])
            self.assertNotIn("source_project", shared["current_context"][0])
        self.assertEqual([], read("--query", "sharedlegacy", "--profile", "audit")["current_context"])

        self.assertEqual(source_before, fingerprint(source))
        if mode == "remote":
            second = base / "second"
            subprocess.run(["git", "init", "-q", str(second)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(second), "remote", "add", "origin",
                            "git@github.com:fixture/retrieval.git"], check=True, capture_output=True)
            same = call("resolve", "--cwd", str(second))
            self.assertEqual(identity, same["project"]["project_id"])
            self.assertEqual(identity, read("--knowledge-id", "successor-rule", cwd=second)["project"]["project_id"])
        for scope in ("project", "domain", "pattern"):
            audited = call("audit", "--cwd", str(source), "--source-root", str(source),
                           "--scope", scope, "--today", "2026-09-05")
            self.assertIn("## Deep Knowledge Audit", audited["report"])
        self.assertEqual([], call("transactions")["transactions"])
        self.assertEqual(identity, call("preflight", "--cwd", str(source))["project"]["project_id"])
        self.assertEqual(source_before, fingerprint(source))
        self.assertTrue({"preflight", "resolve", "capture", "check", "audit",
                         "context-read-path", "transactions"}
                        <= {command for command, _, _ in trace})
        self.assertTrue(Path(first["new_paths"][0]).is_file())

    def test_source_cli_three_project_modes(self):
        for mode in ("plain", "git", "remote"):
            with self.subTest(mode=mode), TemporaryDirectory(prefix="tbc-") as temporary:
                self.run_flow(PLUGIN / RUNNER_PATH, Path(temporary).resolve(), mode)

    def test_copied_package_cli_three_project_modes(self):
        for mode in ("plain", "git", "remote"):
            with self.subTest(mode=mode), TemporaryDirectory(prefix="tbp-") as temporary:
                base = Path(temporary).resolve()
                package = base / "plugin"
                shutil.copytree(PLUGIN, package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                self.run_flow(package / RUNNER_PATH, base, mode)


if __name__ == "__main__":
    unittest.main()
