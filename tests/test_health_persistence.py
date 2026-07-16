from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import check, resolve


class HealthPersistenceTest(unittest.TestCase):
    def test_actual_light_check_persists_status_log_and_high_risk_issue(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)
            page = context.root / context.record.relative_path / "architecture.md"
            page.write_text("# Architecture\nThe service has three replicas.\n", encoding="utf-8")

            result = check(context, [page], date(2026, 7, 13), source_root=repo)

            status = (context.root / "00-global" / "health" / "health-status.md").read_text(encoding="utf-8")
            log = context.root / "00-global" / "health" / "logs" / "2026-07.md"
            self.assertEqual(result.report.check_type, "Light")
            self.assertIn("Last Light Check: 2026-07-13", status)
            self.assertIn("Missing Sources: 1", status)
            self.assertIn("Open Issues", status)
            self.assertIn("architecture.md", status)
            self.assertTrue(log.is_file())

    def test_ambiguous_wikilink_persists_medium_risk(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)
            project = context.root / context.record.relative_path
            index = project / "index.md"
            first = project / "notes" / "duplicate.md"
            second = project / "decisions" / "duplicate.md"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_text("# First\n", encoding="utf-8")
            second.write_text("# Second\n", encoding="utf-8")
            index.write_text("# Index\n\n[[duplicate]]\n", encoding="utf-8")

            result = check(context, [index], date(2026, 7, 14), source_root=repo)

            status = (context.root / "00-global" / "health" / "health-status.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual("Light", result.report.check_type)
            self.assertEqual(1, len(result.report.ambiguous_wikilinks))
            self.assertIn("Medium", status)
    def test_local_check_does_not_mutate_health_status(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)
            health = context.root / "00-global" / "health" / "health-status.md"
            before = health.read_text(encoding="utf-8")

            result = check(context, [], date(2026, 7, 13), source_root=repo)

            self.assertEqual(result.report.check_type, "Local")
            self.assertEqual(health.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
