from contextlib import contextmanager
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts import health_state, tracebook_runner
from plugins.tracebook.skills.tracebook.scripts.check_knowledge import (
    CheckReport,
    DeepAuditReport,
)
from plugins.tracebook.skills.tracebook.scripts.health_state import (
    HealthAggregateRebuildError,
    HealthState,
    health_log_path,
    health_path,
    load_health_state,
    persist_audit,
    persist_check,
    render_health_state,
)
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import audit, check, resolve


class HealthPersistenceTest(unittest.TestCase):
    @staticmethod
    def _report(**overrides: object) -> CheckReport:
        values: dict[str, object] = {
            "check_type": "Light",
            "trigger_reasons": ["Knowledge files changed"],
            "broken_links": [],
            "ambiguous_wikilinks": [],
            "orphan_pages": [],
            "missing_sources": [],
            "outdated_paths": [],
            "pending_confirmations": [],
            "duplicate_pages": [],
            "log_growth": [],
        }
        values.update(overrides)
        return CheckReport(**values)

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

            status_path = health_path(
                context.root, "project", context.record.slug
            )
            status = status_path.read_text(encoding="utf-8")
            log = health_log_path(
                context.root, "project", context.record.slug, date(2026, 7, 13)
            )
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

            status = health_path(
                context.root, "project", context.record.slug
            ).read_text(
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

    def test_scope_dates_and_counters_are_independent(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)
            changed = context.root / context.record.relative_path / "architecture.md"
            another = context.root / context.record.relative_path / "api.md"

            persist_check(
                context.root,
                context.record,
                "project",
                self._report(),
                [changed, changed, another],
                [another, another],
                date(2026, 7, 16),
            )
            persist_check(
                context.root,
                context.record,
                "domain",
                self._report(),
                [context.root / "02-domain" / "billing.md"],
                [],
                date(2026, 7, 17),
            )
            persist_check(
                context.root,
                context.record,
                "pattern",
                self._report(check_type="Regular"),
                [context.root / "03-patterns" / "retry.md"],
                [context.root / "03-patterns" / "retry.md"],
                date(2026, 7, 18),
            )

            project = load_health_state(
                health_path(context.root, "project", context.record.slug)
            )
            domain = load_health_state(health_path(context.root, "domain", "domain"))
            pattern = load_health_state(
                health_path(context.root, "pattern", "pattern")
            )
            self.assertEqual(date(2026, 7, 16), project.last_light)
            self.assertEqual((2, 1), (project.changes_since_regular, project.new_pages_since_regular))
            self.assertEqual(date(2026, 7, 17), domain.last_light)
            self.assertEqual((1, 0), (domain.changes_since_regular, domain.new_pages_since_regular))
            self.assertEqual(date(2026, 7, 18), pattern.last_regular)
            self.assertEqual((0, 0), (pattern.changes_since_regular, pattern.new_pages_since_regular))

    def test_scope_status_and_log_commit_once_before_aggregate_lock(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)
            active: list[str] = []
            commits: list[tuple[str, tuple[Path, ...]]] = []
            actual_lock = health_state.file_lock
            actual_commit = health_state.commit_updates
            aggregate = context.root / "00-global" / "health" / "health-status.md"

            @contextmanager
            def recording_lock(root: Path, name: str, *, operation: str, **options: object):
                with actual_lock(root, name, operation=operation, **options):
                    active.append(name)
                    try:
                        yield
                    finally:
                        active.remove(name)

            def recording_commit(root: Path, scope: str, operation: str, updates: object):
                self.assertIn(f"project-{context.record.slug}", active)
                paths = tuple(updates)
                commits.append((scope, paths))
                return actual_commit(root, scope, operation, updates)

            def recording_rebuild(root: Path) -> Path:
                self.assertNotIn(f"project-{context.record.slug}", active)
                return aggregate

            with patch.object(health_state, "file_lock", recording_lock), patch.object(
                health_state, "commit_updates", side_effect=recording_commit
            ), patch.object(
                health_state, "rebuild_global_health", side_effect=recording_rebuild
            ):
                changed = persist_check(
                    context.root,
                    context.record,
                    "project",
                    self._report(),
                    [],
                    [],
                    date(2026, 7, 18),
                )

            status = health_path(context.root, "project", context.record.slug)
            log = health_log_path(
                context.root, "project", context.record.slug, date(2026, 7, 18)
            )
            self.assertEqual([(f"project-{context.record.slug}", (status, log))], commits)
            self.assertEqual((status, log, aggregate), changed)

    def test_aggregate_failure_exposes_committed_scope_paths_and_original_error(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)
            failure = RuntimeError("aggregate write failed")

            with patch.object(
                health_state, "rebuild_global_health", side_effect=failure
            ), self.assertRaises(HealthAggregateRebuildError) as raised:
                persist_check(
                    context.root,
                    context.record,
                    "project",
                    self._report(missing_sources=["complete missing-source finding"]),
                    [],
                    [],
                    date(2026, 7, 18),
                )

            status = health_path(context.root, "project", context.record.slug)
            log = health_log_path(
                context.root, "project", context.record.slug, date(2026, 7, 18)
            )
            self.assertEqual((status, log), raised.exception.committed_paths)
            self.assertIs(failure, raised.exception.aggregate_error)
            self.assertIs(failure, raised.exception.__cause__)
            self.assertEqual("High", load_health_state(status).risk_level)
            self.assertIn("complete missing-source finding", log.read_text(encoding="utf-8"))

    def test_medium_findings_are_stably_deduplicated_without_truncation(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)
            finding = "01-projects/widgets/api.md:L123 -> [[Shared API]] matches 2 pages"

            persist_check(
                context.root,
                context.record,
                "project",
                self._report(
                    pending_confirmations=[finding, finding],
                    ambiguous_wikilinks=[finding],
                ),
                [],
                [],
                date(2026, 7, 18),
            )

            state = load_health_state(
                health_path(context.root, "project", context.record.slug)
            )
            self.assertEqual("Medium", state.risk_level)
            self.assertEqual(2, state.pending_confirmations)
            self.assertEqual(1, sum(finding in issue for issue in state.issues))
            self.assertTrue(any(issue.endswith(finding) for issue in state.issues))

    def test_audit_persists_review_candidates_without_asserting_business_truth(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)
            report = DeepAuditReport(
                fact_candidates=["candidate fact"],
                missing_source_paths=["complete missing path"],
                root_cause_candidates=["candidate root cause"],
                status_log_drift=["candidate drift"],
            )

            changed = persist_audit(
                context.root,
                context.record,
                "pattern",
                report,
                date(2026, 7, 18),
            )

            status = health_path(context.root, "pattern", "pattern")
            log = health_log_path(
                context.root, "pattern", "pattern", date(2026, 7, 18)
            )
            state = load_health_state(status)
            self.assertEqual(date(2026, 7, 18), state.last_deep)
            self.assertEqual(1, state.missing_sources)
            self.assertEqual("High", state.risk_level)
            self.assertTrue(any("complete missing path" in issue for issue in state.issues))
            self.assertIn("does not assert business truth", log.read_text(encoding="utf-8"))
            self.assertEqual((status, log), changed[:2])

    def test_runner_routes_scope_scan_and_persistence_under_the_same_lock(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)
            report = self._report()
            active: list[str] = []
            aggregate = context.root / "00-global" / "health" / "health-status.md"

            @contextmanager
            def recording_lock(root: Path, name: str, *, operation: str, **_: object):
                active.append(name)
                try:
                    yield
                finally:
                    active.remove(name)

            def run(root: Path, scan_root: Path, *args: object) -> CheckReport:
                self.assertEqual(context.root / "02-domain", scan_root)
                self.assertIn("domain", active)
                return report

            def persist(*args: object) -> tuple[Path, ...]:
                self.assertIn("domain", active)
                return (health_path(context.root, "domain", "domain"),)

            with patch.object(tracebook_runner, "file_lock", recording_lock), patch.object(
                tracebook_runner, "run_check", side_effect=run
            ), patch.object(
                tracebook_runner, "_persist_check_under_lock", side_effect=persist
            ), patch.object(
                tracebook_runner, "_finish_health_persistence", return_value=(aggregate,)
            ):
                result = check(
                    context,
                    [],
                    date(2026, 7, 18),
                    scope="domain",
                )

            self.assertEqual((aggregate,), result.changed_paths)


if __name__ == "__main__":
    unittest.main()
