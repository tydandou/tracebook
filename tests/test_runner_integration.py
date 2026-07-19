import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "plugins" / "tracebook" / "skills" / "tracebook"
RUNNER = SKILL_ROOT / "scripts" / "tracebook_runner.py"


class RunnerIntegrationTest(unittest.TestCase):
    def _run_runner(self, base: Path, *arguments: str) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(RUNNER), *arguments],
            cwd=base,
            capture_output=True,
            check=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_installed_runner_resolves_project_from_an_arbitrary_working_directory(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "resolve",
                    "--root",
                    str(root),
                    "--cwd",
                    str(repo),
                ],
                cwd=base,
                capture_output=True,
                check=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["root"], str(root))
            self.assertEqual(len(payload["read_paths"]), 5)
            self.assertFalse((repo / "AGENTS.md").exists())

    def test_installed_runner_executes_an_explicit_deep_audit(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)

            resolved = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "resolve",
                    "--root",
                    str(root),
                    "--cwd",
                    str(repo),
                ],
                cwd=base,
                capture_output=True,
                check=True,
                text=True,
            )
            resolved_payload = json.loads(resolved.stdout)
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "audit",
                    "--root",
                    str(root),
                    "--cwd",
                    str(repo),
                    "--source-root",
                    str(repo),
                    "--today",
                    "2026-07-13",
                ],
                cwd=base,
                capture_output=True,
                check=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            self.assertIn("Deep Knowledge Audit", payload["report"])
            health = (
                root
                / "01-projects"
                / resolved_payload["project"]["slug"]
                / "health-status.md"
            )
            self.assertIn("Last Deep Check: 2026-07-13", health.read_text(encoding="utf-8"))
            aggregate = (
                root / "00-global" / "health" / "health-status.md"
            ).read_text(encoding="utf-8")
            self.assertIn(
                f"| project | {resolved_payload['project']['identity']} |",
                aggregate,
            )
            self.assertIn("2026-07-13", aggregate)

    def test_capture_scope_flows_to_check_and_audit(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            resolved = self._run_runner(
                base,
                "resolve",
                "--root", str(root),
                "--cwd", str(repo),
            )

            for scope, category, title in (
                ("domain", "terminology", "Settlement term"),
                ("pattern", "backend", "Idempotent consumer"),
            ):
                with self.subTest(scope=scope):
                    request = base / f"{scope}-capture.json"
                    request.write_text(
                        json.dumps(
                            {
                                "scope": scope,
                                "kind": scope,
                                "category": category,
                                "title": title,
                                "body": f"Verified {scope} knowledge.",
                                "evidence": ["src/example.py:L1-L1"],
                                "status": "Current",
                                "write_intent": "durable",
                                "content_kind": "knowledge",
                            }
                        ),
                        encoding="utf-8",
                    )
                    captured = self._run_runner(
                        base,
                        "capture",
                        "--root", str(root),
                        "--cwd", str(repo),
                        "--request", str(request),
                        "--today", "2026-07-19",
                    )
                    health_scope = str(captured["health_scope"])
                    self.assertEqual(scope, health_scope)

                    check_arguments = [
                        "check",
                        "--root", str(root),
                        "--cwd", str(repo),
                        "--source-root", str(repo),
                        "--today", "2026-07-19",
                        "--scope", health_scope,
                    ]
                    for path in captured["changed_paths"]:
                        check_arguments.extend(("--changed", str(path)))
                    for path in captured["new_paths"]:
                        check_arguments.extend(("--new-path", str(path)))
                    checked = self._run_runner(base, *check_arguments)
                    self.assertEqual("Light", checked["check_type"])

                    audited = self._run_runner(
                        base,
                        "audit",
                        "--root", str(root),
                        "--cwd", str(repo),
                        "--source-root", str(repo),
                        "--today", "2026-07-19",
                        "--scope", health_scope,
                    )
                    self.assertIn("Deep Knowledge Audit", audited["report"])

                    status = root / "00-global" / "health" / "scopes" / f"{scope}-status.md"
                    log = root / "00-global" / "health" / "logs" / scope / "2026-07.md"
                    aggregate = root / "00-global" / "health" / "health-status.md"
                    self.assertIn("Last Deep Check: 2026-07-19", status.read_text(encoding="utf-8"))
                    self.assertIn(str(resolved["project"]["identity"]), log.read_text(encoding="utf-8"))
                    self.assertIn(f"| {scope} | {scope} |", aggregate.read_text(encoding="utf-8"))

    def test_skill_uses_its_own_directory_for_runner_invocation(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("$SKILL_DIR/scripts/tracebook_runner.py", skill)
        self.assertIn("resolve --root", skill)
        self.assertIn("health_scope", skill)
        self.assertIn("--scope", skill)
        self.assertRegex(
            skill,
            r"(?s)health_scope.*?check.*?--scope.*?audit.*?same scope",
        )


if __name__ == "__main__":
    unittest.main()
