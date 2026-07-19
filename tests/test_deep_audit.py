from datetime import date
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.check_knowledge import run_deep_audit
from plugins.tracebook.skills.tracebook.scripts.health_state import (
    health_log_path,
    health_path,
)
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
            health = health_path(context.root, "project", context.record.slug)
            log = health_log_path(
                context.root, "project", context.record.slug, date(2026, 7, 13)
            )
            aggregate = context.root / "00-global" / "health" / "health-status.md"
            before = health.read_text(encoding="utf-8")

            requirement = check(context, [page], date(2026, 7, 13), source_root=repo)
            self.assertEqual(before, health.read_text(encoding="utf-8"))
            result = audit(context, date(2026, 7, 13), source_root=repo)

            after = health.read_text(encoding="utf-8")
            self.assertEqual(requirement.report.check_type, "Deep")
            self.assertEqual(requirement.changed_paths, ())
            self.assertEqual(result.changed_paths, (health, log, aggregate))
            self.assertIn("Last Deep Check: 2026-07-13", after)
            self.assertNotEqual(before, after)
            aggregate_content = aggregate.read_text(encoding="utf-8")
            self.assertIn(context.record.identity, aggregate_content)
            self.assertIn("2026-07-13", aggregate_content)
            self.assertFalse((repo / "AGENTS.md").exists())

    def test_deep_audit_scans_active_pages_in_every_knowledge_scope(self) -> None:
        with TemporaryDirectory() as temp:
            context, repo = self._context(Path(temp))
            project = context.root / context.record.relative_path
            project_child = project / "business-rules" / "refunds.md"
            domain = context.root / "02-domain" / "settlement.md"
            pattern = context.root / "03-patterns" / "retry.md"
            for page in (project_child, domain, pattern):
                page.parent.mkdir(parents=True, exist_ok=True)
                page.write_text(
                    "# Knowledge\n\n## Rule\n\nThe RETRY limit is 3.\n",
                    encoding="utf-8",
                )

            project_report = run_deep_audit(context.root, project, repo)
            domain_report = run_deep_audit(context.root, domain.parent, repo)
            pattern_report = run_deep_audit(context.root, pattern.parent, repo)

            self.assertTrue(
                any("business-rules/refunds.md:L5" in item for item in project_report.fact_candidates)
            )
            self.assertTrue(
                any("02-domain/settlement.md:L5" in item for item in domain_report.fact_candidates)
            )
            self.assertTrue(
                any("03-patterns/retry.md:L5" in item for item in pattern_report.fact_candidates)
            )

    def test_deep_audit_excludes_navigation_status_logs_and_archives(self) -> None:
        with TemporaryDirectory() as temp:
            context, repo = self._context(Path(temp))
            project = context.root / context.record.relative_path
            pages = (
                project / "index.md",
                project / "project-status.md",
                project / "health-status.md",
                project / "logs" / "2026-07.md",
                project / "archive" / "business-rules.md",
            )
            for page in pages:
                page.parent.mkdir(parents=True, exist_ok=True)
                page.write_text("# Metadata\nThe RETRY limit is 9.\n", encoding="utf-8")

            report = run_deep_audit(context.root, project, repo)

            self.assertEqual([], report.fact_candidates)

    def test_deep_audit_applies_evidence_and_pending_state_per_entry(self) -> None:
        with TemporaryDirectory() as temp:
            context, repo = self._context(Path(temp))
            project = context.root / context.record.relative_path
            page = project / "architecture.md"
            page.write_text(
                "\n".join(
                    [
                        "# Architecture",
                        "",
                        "## Verified topology",
                        "",
                        "The API runs with 3 replicas.",
                        "",
                        "Evidence:",
                        "- `src/app.py:L1-L2`",
                        "",
                        "## Pending topology",
                        "",
                        "The API may need 4 replicas.",
                        "",
                        "Status: Pending",
                        "",
                        "## Unverified topology",
                        "",
                        "The API runs with 5 workers.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            report = run_deep_audit(context.root, project, repo)

            self.assertEqual(
                [
                    f"01-projects/{context.record.slug}/architecture.md:L18: "
                    "factual claim requires evidence review"
                ],
                report.fact_candidates,
            )

    def test_deep_audit_does_not_treat_pending_in_claim_text_as_status(self) -> None:
        with TemporaryDirectory() as temp:
            context, repo = self._context(Path(temp))
            project = context.root / context.record.relative_path
            page = project / "architecture.md"
            page.write_text(
                "# Architecture\n\n## Queue\n\nThe PENDING queue limit is 3.\n",
                encoding="utf-8",
            )

            report = run_deep_audit(context.root, project, repo)

            self.assertEqual(
                [
                    f"01-projects/{context.record.slug}/architecture.md:L5: "
                    "factual claim requires evidence review"
                ],
                report.fact_candidates,
            )

    def test_deep_audit_recognizes_markdown_indented_level_two_entries(self) -> None:
        with TemporaryDirectory() as temp:
            context, repo = self._context(Path(temp))
            project = context.root / context.record.relative_path
            page = project / "architecture.md"
            page.write_text(
                "\n".join(
                    [
                        "# Architecture",
                        "",
                        "   ## Unverified",
                        "The API runs with 3 workers.",
                        "",
                        "   ## Verified",
                        "The API runs with 4 replicas.",
                        "Evidence:",
                        "- `src/app.py:L1-L2`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            report = run_deep_audit(context.root, project, repo)

            self.assertEqual(
                [
                    f"01-projects/{context.record.slug}/architecture.md:L4: "
                    "factual claim requires evidence review"
                ],
                report.fact_candidates,
            )


if __name__ == "__main__":
    unittest.main()
