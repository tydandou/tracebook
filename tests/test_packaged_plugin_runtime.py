"""Verify the distributable plugin tree preserves the health command contract."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "tracebook"


class PackagedPluginRuntimeTest(unittest.TestCase):
    def _run(self, runner: Path, base: Path, *arguments: str) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(runner), *arguments],
            cwd=base,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            0,
            result.returncode,
            result.stderr.decode("utf-8", errors="replace"),
        )
        self.assertTrue(result.stdout)
        return json.loads(result.stdout.decode("utf-8"))

    def test_copied_plugin_tree_refreshes_aggregate_for_first_direct_health_command(self) -> None:
        for command in ("check", "audit"):
            with self.subTest(command=command), TemporaryDirectory() as temp:
                base = Path(temp).resolve()
                package = base / "plugin"
                shutil.copytree(PLUGIN, package)
                runner = package / "skills" / "tracebook" / "scripts" / "tracebook_runner.py"
                root = base / "knowledge"
                first = base / "first"
                second = base / "second"
                (first / ".git").mkdir(parents=True)
                (second / ".git").mkdir(parents=True)

                self._run(runner, base, "resolve", "--root", str(root), "--cwd", str(first))
                aggregate = root / "00-global" / "health" / "health-status.md"
                self.assertEqual(1, aggregate.read_text(encoding="utf-8").count("| project |"))

                payload = self._run(
                    runner,
                    base,
                    command,
                    "--root",
                    str(root),
                    "--cwd",
                    str(second),
                    "--today",
                    "2026-08-21",
                )

                self.assertEqual(2, aggregate.read_text(encoding="utf-8").count("| project |"))
                self.assertIn(str(aggregate), payload["changed_paths"])
                pointers = list(
                    (root / ".tracebook-state" / "snapshots").glob("*/current.json")
                )
                self.assertEqual(2, len(pointers))


if __name__ == "__main__":
    unittest.main()
