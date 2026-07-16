from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.check_knowledge import run_check
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import check, resolve


class RegularHealthTest(unittest.TestCase):
    def _health_status(self, root: Path, changes: int = 10) -> None:
        status = root / "00-global" / "health" / "health-status.md"
        status.parent.mkdir(parents=True, exist_ok=True)
        status.write_text(
            "\n".join(
                [
                    "# Knowledge Health Status",
                    "",
                    "## Current Status",
                    "",
                    "- Last Light Check: Not run",
                    "- Last Regular Check: Not run",
                    "- Last Deep Check: Not run",
                    f"- Changes Since Last Regular Check: {changes}",
                    "- New Pages Since Last Regular Check: 0",
                    "- Pending Confirmations: 0",
                    "- Missing Sources: 0",
                    "- Broken Links: 0",
                    "- Orphan Pages: 0",
                    "",
                    "## Current Risk Level",
                    "",
                    "Unknown",
                    "",
                    "## Open Issues",
                    "",
                    "None recorded.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def test_regular_check_reports_duplicate_pages_and_log_growth(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "01-projects" / "sample"
            project.mkdir(parents=True)
            self._health_status(root)
            first = project / "architecture.md"
            second = project / "modules.md"
            first.write_text("# Architecture\n\nSame durable conclusion.\n", encoding="utf-8")
            second.write_text("# Modules\n\nSame durable conclusion.\n", encoding="utf-8")
            log = project / "logs" / "2026-07.md"
            log.parent.mkdir()
            log.write_text("line\n" * 301, encoding="utf-8")

            report = run_check(root, project, [first], date(2026, 7, 13))

            self.assertEqual(report.check_type, "Regular")
            self.assertIn(
                "01-projects/sample/architecture.md <-> 01-projects/sample/modules.md",
                report.duplicate_pages,
            )
            self.assertIn("01-projects/sample/logs/2026-07.md: 301 lines", report.log_growth)

    def test_persistence_updates_regular_baseline_and_deduplicates_generated_risks(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)
            self._health_status(context.root)
            page = context.root / context.record.relative_path / "architecture.md"
            page.write_text("# Architecture\nUnsourced topology.\n", encoding="utf-8")

            first = check(context, [page], date(2026, 7, 13), source_root=repo)
            second = check(context, [page], date(2026, 7, 13), source_root=repo)

            status = (context.root / "00-global" / "health" / "health-status.md").read_text(encoding="utf-8")
            self.assertEqual(first.report.check_type, "Regular")
            self.assertEqual(second.report.check_type, "Light")
            self.assertIn("Last Regular Check: 2026-07-13", status)
            self.assertIn("Changes Since Last Regular Check: 1", status)
            self.assertIn("New Pages Since Last Regular Check: 0", status)
            self.assertIn("Missing Sources: 1", status)
            self.assertIn("High", status)
            self.assertEqual(status.count("01-projects/"), 1)


if __name__ == "__main__":
    unittest.main()
