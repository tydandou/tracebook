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
            self.assertEqual(len(payload["read_paths"]), 4)
            self.assertFalse((repo / "AGENTS.md").exists())

    def test_installed_runner_executes_an_explicit_deep_audit(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)

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
            health = root / "00-global" / "health" / "health-status.md"
            self.assertIn("Last Deep Check: 2026-07-13", health.read_text(encoding="utf-8"))
    def test_skill_uses_its_own_directory_for_runner_invocation(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("$SKILL_DIR/scripts/tracebook_runner.py", skill)
        self.assertIn("resolve --root", skill)


if __name__ == "__main__":
    unittest.main()
