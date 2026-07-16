from datetime import date
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.check_knowledge import run_deep_audit
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import audit, check, resolve


class DeepAuditTest(unittest.TestCase):
    def _context(self, base: Path):
        repo = base / "business"
        (repo / ".git").mkdir(parents=True)
        return resolve(base / "knowledge", repo), repo

    def test_deep_audit_outputs_candidates_without_asserting_business_truth(self) -> None:
        with TemporaryDirectory() as temp:
            context, repo = self._context(Path(temp))
            project = context.root / context.record.relative_path
            (repo / "src").mkdir()
            (repo / "src" / "order.py").write_text("STATE = 'REFUNDING'\n", encoding="utf-8")
            (project / "business-rules.md").write_text(
                "# Rules\nOrder state `REFUNDING` has a retry limit of 3.\n\n"
                "Evidence:\n- `src/order.py:L1-L1`\n",
                encoding="utf-8",
            )
            (project / "api.md").write_text(
                "# API\nThe API returns status `REFUNDING` after 3 retries.\n",
                encoding="utf-8",
            )
            (project / "database.md").write_text(
                "# Database\nRoot cause: order_id was written before transaction commit.\n\n"
                "Evidence:\n- `src/missing.py:L1-L2`\n",
                encoding="utf-8",
            )
            status = project / "project-status.md"
            status.write_text("# Project Status\n", encoding="utf-8")
            log = project / "logs" / "2026-07.md"
            log.parent.mkdir()
            log.write_text("## Bug\n- New incident\n", encoding="utf-8")
            os.utime(status, (1, 1))

            report = run_deep_audit(context.root, project, repo)

            self.assertIn(
                "01-projects/" + context.record.slug + "/api.md:L2: factual claim requires evidence review",
                report.fact_candidates,
            )
            self.assertIn(
                "01-projects/" + context.record.slug + "/database.md -> src/missing.py",
                report.missing_source_paths,
            )
            self.assertIn(
                "01-projects/" + context.record.slug + "/database.md:L2: root-cause claim requires human review",
                report.root_cause_candidates,
            )
            self.assertIn(
                "01-projects/" + context.record.slug + "/project-status.md is older than logs/2026-07.md",
                report.status_log_drift,
            )
            self.assertIn("candidate", report.to_markdown().lower())

    def test_explicit_audit_persists_last_deep_check_but_deep_requirement_does_not(self) -> None:
        with TemporaryDirectory() as temp:
            context, repo = self._context(Path(temp))
            page = context.root / context.record.relative_path / "business-rules.md"
            page.write_text("# Rules\n" + "rule\n" * 300, encoding="utf-8")
            health = context.root / "00-global" / "health" / "health-status.md"
            before = health.read_text(encoding="utf-8")

            requirement = check(context, [page], date(2026, 7, 13), source_root=repo)
            result = audit(context, date(2026, 7, 13), source_root=repo)

            after = health.read_text(encoding="utf-8")
            self.assertEqual(requirement.report.check_type, "Deep")
            self.assertEqual(requirement.changed_paths, ())
            self.assertEqual(result.changed_paths[0], health)
            self.assertIn("Last Deep Check: 2026-07-13", after)
            self.assertNotEqual(before, after)
            self.assertFalse((repo / "AGENTS.md").exists())


if __name__ == "__main__":
    unittest.main()
