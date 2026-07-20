import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts import transaction


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
            base = Path(temp).resolve()
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
            self.assertEqual("en", payload["knowledge_language"])
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

    def test_transaction_inspection_is_read_only_and_recovery_is_explicit(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            root.mkdir()
            target = root / "entry.md"
            target.write_text("old\n", encoding="utf-8")

            with patch.object(
                transaction,
                "_replace_target",
                side_effect=OSError("simulated crash"),
            ):
                with self.assertRaisesRegex(OSError, "simulated crash"):
                    transaction.commit_updates(
                        root,
                        "project-demo",
                        "capture",
                        {target: "new\n"},
                        transaction_id="runner-inspect",
                    )
            inspected = self._run_runner(
                base,
                "transactions",
                "--root", str(root),
            )

            self.assertEqual(str(root), inspected["root"])
            self.assertEqual("recoverable", inspected["transactions"][0]["disposition"])
            self.assertEqual("old\n", target.read_text(encoding="utf-8"))

            recovered = self._run_runner(
                base,
                "recover-transactions",
                "--root", str(root),
            )

            self.assertEqual([str(target)], recovered["recovered_paths"])
            self.assertEqual("new\n", target.read_text(encoding="utf-8"))

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
                    changed_paths = [str(path) for path in captured["changed_paths"]]
                    new_paths = [str(path) for path in captured["new_paths"]]
                    self.assertGreaterEqual(len(changed_paths), 2)
                    self.assertGreaterEqual(len(new_paths), 1)

                    check_arguments = [
                        "check",
                        "--root", str(root),
                        "--cwd", str(repo),
                        "--source-root", str(repo),
                        "--today", "2026-07-19",
                        "--scope", health_scope,
                    ]
                    for path in changed_paths:
                        check_arguments.extend(("--changed", path))
                    for path in new_paths:
                        check_arguments.extend(("--new-path", path))
                    checked = self._run_runner(base, *check_arguments)
                    self.assertEqual("Light", checked["check_type"])

                    status = root / "00-global" / "health" / "scopes" / f"{scope}-status.md"
                    checked_status = status.read_text(encoding="utf-8")
                    self.assertIn(
                        f"Changes Since Last Regular Check: {len(set(changed_paths))}",
                        checked_status,
                    )
                    self.assertIn(
                        f"New Pages Since Last Regular Check: {len(set(new_paths))}",
                        checked_status,
                    )

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

                    log = root / "00-global" / "health" / "logs" / scope / "2026-07.md"
                    aggregate = root / "00-global" / "health" / "health-status.md"
                    self.assertIn("Last Deep Check: 2026-07-19", status.read_text(encoding="utf-8"))
                    self.assertIn(str(resolved["project"]["identity"]), log.read_text(encoding="utf-8"))
                    self.assertIn(f"| {scope} | {scope} |", aggregate.read_text(encoding="utf-8"))

    def test_skill_uses_its_own_directory_for_runner_invocation(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("$SKILL_DIR/scripts/tracebook_runner.py", skill)
        self.assertIn("resolve --root", skill)
        verify_heading = "## Verify Knowledge Writes"
        final_heading = "## Final Task Report"
        self.assertIn(verify_heading, skill)
        self.assertIn(final_heading, skill)
        verify_workflow = skill.split(verify_heading, 1)[1].split(final_heading, 1)[0]
        verify_workflow = " ".join(verify_workflow.split())

        self.assertIn(
            "After every successful capture, require `changed_paths`, `new_paths`, "
            "and `health_scope` in its structured JSON.",
            verify_workflow,
        )
        self.assertIn(
            "Stop and report an incomplete runner response",
            verify_workflow,
        )
        self.assertIn(
            "`health_scope` is absent or is not `project`, `domain`, or `pattern`;",
            verify_workflow,
        )
        self.assertIn(
            "do not fall back to the default project scope.",
            verify_workflow,
        )
        self.assertIn(
            "Pass every capture `changed_paths` item as `--changed`",
            verify_workflow,
        )
        self.assertIn(
            "every `new_paths` item as `--new-path`",
            verify_workflow,
        )
        self.assertIn(
            "the capture `health_scope` as `--scope`.",
            verify_workflow,
        )
        self.assertIn(
            "Run `$SKILL_DIR/scripts/tracebook_runner.py audit` with the same "
            "`--root`, `--cwd`, `--today`, and `--source-root` values, plus the "
            "same scope supplied to check as `--scope`.",
            verify_workflow,
        )


if __name__ == "__main__":
    unittest.main()
