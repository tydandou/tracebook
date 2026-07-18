from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.health_state import (
    HealthState,
    load_health_state,
    render_health_state,
)
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import check, resolve


class HealthPersistenceTest(unittest.TestCase):
    def test_health_state_uses_exact_managed_labels_and_preserves_human_content(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "health-status.md"
            initial = HealthState(
                scope="project",
                identity="github.com/acme/widgets",
                last_light=date(2026, 7, 17),
                last_regular=date(2026, 7, 10),
                changes_since_regular=4,
                new_pages_since_regular=2,
                pending_confirmations=1,
                missing_sources=3,
                broken_links=5,
                orphan_pages=6,
                risk_level="High",
                issues=("generated issue",),
            )
            human = (
                "\n## Human Notes\n"
                "Keep this prose and this similarly named field.\n"
                "- Last Light Review: 1999-01-01\n"
                "- Human issue must survive.\n"
            )
            path.write_text(render_health_state(initial) + human, encoding="utf-8")

            parsed = load_health_state(path)
            self.assertEqual(initial, parsed)
            updated = HealthState(
                **{
                    **initial.__dict__,
                    "last_light": date(2026, 7, 18),
                    "issues": ("replacement generated issue",),
                }
            )
            rendered = render_health_state(updated, path.read_text(encoding="utf-8"))

            for label in (
                "Scope",
                "Identity",
                "Last Light Check",
                "Last Regular Check",
                "Last Deep Check",
                "Changes Since Last Regular Check",
                "New Pages Since Last Regular Check",
                "Pending Confirmations",
                "Missing Sources",
                "Broken Links",
                "Orphan Pages",
            ):
                self.assertEqual(1, rendered.count(f"- {label}:"))
            self.assertEqual(1, rendered.count("<!-- tracebook:generated-issues:start -->"))
            self.assertEqual(1, rendered.count("<!-- tracebook:generated-issues:end -->"))
            self.assertNotIn("\n- generated issue\n", rendered)
            self.assertIn("replacement generated issue", rendered)
            self.assertIn(human, rendered)
            path.write_text(rendered, encoding="utf-8")
            self.assertEqual(updated, load_health_state(path))

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
