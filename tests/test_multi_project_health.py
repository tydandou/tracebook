from contextlib import contextmanager
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts import health_state
from plugins.tracebook.skills.tracebook.scripts.check_knowledge import CheckReport
from plugins.tracebook.skills.tracebook.scripts.errors import TracebookError
from plugins.tracebook.skills.tracebook.scripts.health_state import (
    HealthState,
    ensure_health_layout,
    health_log_path,
    health_path,
    load_health_state,
    persist_check,
    rebuild_global_health,
    render_health_state,
    rollback_health_migration,
)
from plugins.tracebook.skills.tracebook.scripts.project_registry import ProjectRecord


class MultiProjectHealthTest(unittest.TestCase):
    @staticmethod
    def _record(identity: str, slug: str) -> ProjectRecord:
        return ProjectRecord(identity, slug, f"01-projects/{slug}")

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

    def _legacy_root(self, base: Path) -> tuple[Path, bytes, bytes]:
        root = (base / "knowledge").resolve()
        health = root / "00-global" / "health"
        projects = root / "01-projects"
        health.mkdir(parents=True)
        projects.mkdir(parents=True)
        legacy = (
            "# Legacy Knowledge Health\r\n"
            "\r\n"
            "- Changes Since Last Regular Check: 77\r\n"
            "- Missing Sources: 13\r\n"
            "\r\n"
            "Legacy issue owned by nobody: café.\r\n"
        ).encode("utf-8")
        legacy_log = b"# Legacy log\r\n\r\nNever rewrite this log.\r\n"
        (health / "health-status.md").write_bytes(legacy)
        (health / "logs").mkdir()
        (health / "logs" / "2026-06.md").write_bytes(legacy_log)
        records = {
            "github.com/acme/alpha": {
                "identity": "github.com/acme/alpha",
                "slug": "alpha",
                "relative_path": "01-projects/alpha",
            },
            "github.com/acme/beta": {
                "identity": "github.com/acme/beta",
                "slug": "beta",
                "relative_path": "01-projects/beta",
            },
        }
        (root / "registry.json").write_text(
            json.dumps({"version": 1, "projects": records}, indent=2) + "\n",
            encoding="utf-8",
        )
        return root, legacy, legacy_log

    def test_scope_status_and_log_paths_are_exact(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            month = date(2026, 7, 18)

            self.assertEqual(
                root / "01-projects" / "widgets" / "health-status.md",
                health_path(root, "project", "widgets"),
            )
            self.assertEqual(
                root / "00-global" / "health" / "scopes" / "domain-status.md",
                health_path(root, "domain", "domain"),
            )
            self.assertEqual(
                root / "00-global" / "health" / "scopes" / "pattern-status.md",
                health_path(root, "pattern", "pattern"),
            )
            self.assertEqual(
                root / "01-projects" / "widgets" / "health-logs" / "2026-07.md",
                health_log_path(root, "project", "widgets", month),
            )
            self.assertEqual(
                root / "00-global" / "health" / "logs" / "domain" / "2026-07.md",
                health_log_path(root, "domain", "domain", month),
            )
            self.assertEqual(
                root / "00-global" / "health" / "logs" / "pattern" / "2026-07.md",
                health_log_path(root, "pattern", "pattern", month),
            )
            invalid_slugs = (
                "",
                "widgets/team",
                r"widgets\team",
                ".",
                "..",
                "/absolute",
                r"\absolute",
                "C:drive",
                "C:/drive",
                r"C:\drive",
                "Widgets",
                "-widgets",
                "widgets-",
                "widgets--api",
                "widgets_api",
            )
            for slug in invalid_slugs:
                with self.subTest(slug=slug):
                    with self.assertRaises(TracebookError):
                        health_path(root, "project", slug)
                    with self.assertRaises(TracebookError):
                        health_log_path(root, "project", slug, month)
            self.assertFalse((root / "01-projects").exists())

    def test_migration_archives_legacy_bytes_and_creates_a_hashed_v1_manifest(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root, legacy, legacy_log = self._legacy_root(Path(temp))

            ensure_health_layout(root)

            archive = (
                root
                / "00-global"
                / "health"
                / "archive"
                / "health-status-pre-v1.md"
            )
            manifest_path = root / ".tracebook-state" / "migrations" / "health-v1.json"
            self.assertEqual(legacy, archive.read_bytes())
            self.assertEqual(
                legacy_log,
                (root / "00-global" / "health" / "logs" / "2026-06.md").read_bytes(),
            )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {"version", "source", "archive", "created"},
                set(manifest),
            )
            self.assertEqual(1, manifest["version"])
            self.assertEqual(
                "00-global/health/health-status.md",
                manifest["source"],
            )
            self.assertEqual(
                "00-global/health/archive/health-status-pre-v1.md",
                manifest["archive"],
            )
            expected_created = [
                "00-global/health/archive/health-status-pre-v1.md",
                "00-global/health/scopes/domain-status.md",
                "00-global/health/scopes/pattern-status.md",
                "01-projects/alpha/health-status.md",
                "01-projects/beta/health-status.md",
            ]
            self.assertEqual(
                expected_created,
                [entry["path"] for entry in manifest["created"]],
            )
            for entry in manifest["created"]:
                self.assertEqual({"path", "initial_sha256"}, set(entry))
                created = root.joinpath(*entry["path"].split("/"))
                self.assertEqual(
                    hashlib.sha256(created.read_bytes()).hexdigest(),
                    entry["initial_sha256"],
                )

            for scope, identity, slug in (
                ("project", "github.com/acme/alpha", "alpha"),
                ("project", "github.com/acme/beta", "beta"),
                ("domain", "domain", "domain"),
                ("pattern", "pattern", "pattern"),
            ):
                state = load_health_state(health_path(root, scope, slug))
                self.assertEqual(scope, state.scope)
                self.assertEqual(identity, state.identity)
                self.assertEqual(0, state.changes_since_regular)
                self.assertEqual(0, state.missing_sources)
                self.assertEqual((), state.issues)

            aggregate = (root / "00-global" / "health" / "health-status.md").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("Legacy issue owned by nobody", aggregate)
            self.assertNotIn("77", aggregate)
            self.assertIn("github.com/acme/alpha", aggregate)
            self.assertIn("github.com/acme/beta", aggregate)

    def test_preexisting_matching_archive_is_not_owned_or_deleted(self) -> None:
        with TemporaryDirectory() as temp:
            root, legacy, _ = self._legacy_root(Path(temp))
            archive = root / "00-global" / "health" / "archive" / "health-status-pre-v1.md"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(legacy)

            ensure_health_layout(root)

            manifest_path = root / ".tracebook-state" / "migrations" / "health-v1.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn(
                "00-global/health/archive/health-status-pre-v1.md",
                [entry["path"] for entry in manifest["created"]],
            )

            rollback_health_migration(root)

            self.assertTrue(archive.exists())
            self.assertEqual(legacy, archive.read_bytes())
            self.assertEqual(
                legacy,
                (root / "00-global" / "health" / "health-status.md").read_bytes(),
            )
            self.assertFalse(manifest_path.exists())

    def test_aggregate_is_stably_rebuilt_from_scope_pages(self) -> None:
        with TemporaryDirectory() as temp:
            root, _, _ = self._legacy_root(Path(temp))
            ensure_health_layout(root)
            alpha_path = health_path(root, "project", "alpha")
            alpha = replace(
                load_health_state(alpha_path),
                last_light=date(2026, 7, 18),
                risk_level="High",
                issues=("alpha needs a source",),
            )
            alpha_path.write_text(render_health_state(alpha), encoding="utf-8")

            aggregate_path = rebuild_global_health(root)
            first = aggregate_path.read_bytes()
            aggregate_path.unlink()
            self.assertEqual(aggregate_path, rebuild_global_health(root))

            self.assertEqual(first, aggregate_path.read_bytes())
            aggregate = first.decode("utf-8")
            self.assertLess(aggregate.index("domain"), aggregate.index("pattern"))
            self.assertLess(aggregate.index("github.com/acme/alpha"), aggregate.index("github.com/acme/beta"))
            self.assertIn("alpha needs a source", aggregate)

    def test_project_high_state_survives_a_later_low_project_check(self) -> None:
        with TemporaryDirectory() as temp:
            root, _, _ = self._legacy_root(Path(temp))
            ensure_health_layout(root)
            alpha = self._record("github.com/acme/alpha", "alpha")
            beta = self._record("github.com/acme/beta", "beta")
            today = date(2026, 7, 18)

            persist_check(
                root,
                alpha,
                "project",
                self._report(
                    broken_links=[
                        "01-projects/alpha/architecture.md -> missing.md"
                    ]
                ),
                [root / "01-projects" / "alpha" / "architecture.md"],
                [root / "01-projects" / "alpha" / "architecture.md"],
                today,
            )
            alpha_before = load_health_state(health_path(root, "project", "alpha"))

            persist_check(
                root,
                beta,
                "project",
                self._report(),
                [root / "01-projects" / "beta" / "architecture.md"],
                [],
                today,
            )

            self.assertEqual(
                alpha_before,
                load_health_state(health_path(root, "project", "alpha")),
            )
            self.assertEqual("High", alpha_before.risk_level)
            self.assertEqual(1, alpha_before.changes_since_regular)
            self.assertEqual(1, alpha_before.new_pages_since_regular)
            self.assertEqual(
                "Low",
                load_health_state(
                    health_path(root, "project", "beta")
                ).risk_level,
            )

    def test_identical_reports_keep_project_and_namespace_owner_logs(self) -> None:
        with TemporaryDirectory() as temp:
            root, _, _ = self._legacy_root(Path(temp))
            ensure_health_layout(root)
            alpha = self._record("github.com/acme/alpha", "alpha")
            beta = self._record("github.com/acme/beta", "beta")
            today = date(2026, 7, 18)
            report = self._report(pending_confirmations=["same finding"])

            for record in (alpha, beta):
                persist_check(root, record, "project", report, [], [], today)
                persist_check(root, record, "domain", report, [], [], today)

            for record in (alpha, beta):
                project_log = health_log_path(
                    root, "project", record.slug, today
                ).read_text(encoding="utf-8")
                self.assertIn(f"Owner Project Identity: {record.identity}", project_log)
                self.assertIn(f"Scope Identity: {record.identity}", project_log)
                self.assertIn("same finding", project_log)

            namespace_log = health_log_path(
                root, "domain", "domain", today
            ).read_text(encoding="utf-8")
            self.assertIn("Owner Project Identity: github.com/acme/alpha", namespace_log)
            self.assertIn("Owner Project Identity: github.com/acme/beta", namespace_log)
            self.assertEqual(2, namespace_log.count(report.to_markdown()))

    def test_nonlegacy_layout_leaves_aggregate_writes_to_the_aggregate_lock(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "knowledge"
            (root / "00-global" / "health").mkdir(parents=True)
            (root / "01-projects").mkdir(parents=True)
            aggregate = root / "00-global" / "health" / "health-status.md"
            existing = (
                "# Existing aggregate\n\n"
                "<!-- tracebook:health-aggregate:start -->\n"
                "Human-managed snapshot until the aggregate lock rebuilds it.\n"
                "<!-- tracebook:health-aggregate:end -->\n"
            ).encode("utf-8")
            aggregate.write_bytes(existing)

            ensure_health_layout(root)

            self.assertEqual(existing, aggregate.read_bytes())
            self.assertTrue(health_path(root, "domain", "domain").is_file())
            self.assertTrue(health_path(root, "pattern", "pattern").is_file())

    def test_migration_and_rollback_lock_root_status_in_maintenance_order(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root, _, _ = self._legacy_root(Path(temp))
            actual_lock = health_state.file_lock
            events: list[str] = []

            @contextmanager
            def recording_lock(
                lock_root: Path,
                name: str,
                *,
                operation: str,
                **options: object,
            ):
                events.append(f"enter:{name}")
                with actual_lock(
                    lock_root,
                    name,
                    operation=operation,
                    **options,
                ):
                    try:
                        yield
                    finally:
                        events.append(f"exit:{name}")

            with patch.object(health_state, "file_lock", recording_lock):
                ensure_health_layout(root)
            self.assertEqual(
                [
                    "enter:maintenance",
                    "enter:health-aggregate",
                    "enter:registry",
                    "exit:registry",
                    "exit:health-aggregate",
                    "exit:maintenance",
                ],
                events,
            )

            events.clear()
            with patch.object(health_state, "file_lock", recording_lock):
                rollback_health_migration(root)
            self.assertEqual(
                [
                    "enter:maintenance",
                    "enter:health-aggregate",
                    "exit:health-aggregate",
                    "exit:maintenance",
                ],
                events,
            )

    def test_registered_project_reads_nest_registry_lock_inside_health_locks(
        self,
    ) -> None:
        actual_lock = health_state.file_lock

        for layout in ("legacy", "template"):
            with self.subTest(layout=layout), TemporaryDirectory() as temp:
                if layout == "legacy":
                    root, _, _ = self._legacy_root(Path(temp))
                else:
                    root = Path(temp) / "knowledge"
                    health = root / "00-global" / "health"
                    health.mkdir(parents=True)
                    (root / "01-projects").mkdir(parents=True)
                    (health / "health-status.md").write_text(
                        "# Existing aggregate\n\n"
                        "<!-- tracebook:health-aggregate:start -->\n"
                        "Existing generated rows.\n"
                        "<!-- tracebook:health-aggregate:end -->\n",
                        encoding="utf-8",
                    )
                    (root / "registry.json").write_text(
                        json.dumps({"version": 1, "projects": {}}) + "\n",
                        encoding="utf-8",
                    )

                events: list[str] = []

                @contextmanager
                def recording_lock(
                    lock_root: Path,
                    name: str,
                    *,
                    operation: str,
                    **options: object,
                ):
                    events.append(f"enter:{name}")
                    with actual_lock(
                        lock_root,
                        name,
                        operation=operation,
                        **options,
                    ):
                        try:
                            yield
                        finally:
                            events.append(f"exit:{name}")

                with patch.object(health_state, "file_lock", recording_lock):
                    ensure_health_layout(root)
                self.assertEqual(
                    [
                        "enter:maintenance",
                        "enter:health-aggregate",
                        "enter:registry",
                        "exit:registry",
                        "exit:health-aggregate",
                        "exit:maintenance",
                    ],
                    events,
                )

                events.clear()
                with patch.object(health_state, "file_lock", recording_lock):
                    rebuild_global_health(root)
                self.assertEqual(
                    [
                        "enter:health-aggregate",
                        "enter:registry",
                        "exit:registry",
                        "exit:health-aggregate",
                    ],
                    events,
                )

    def test_delayed_rebuild_after_rollback_preserves_exact_legacy_status(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root, legacy, _ = self._legacy_root(Path(temp))
            ensure_health_layout(root)
            rollback_health_migration(root)

            rebuilt = rebuild_global_health(root)

            self.assertEqual(
                root / "00-global" / "health" / "health-status.md",
                rebuilt,
            )
            self.assertEqual(legacy, rebuilt.read_bytes())

    def test_rollback_restores_source_and_removes_unchanged_created_pages(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root, legacy, legacy_log = self._legacy_root(Path(temp))
            ensure_health_layout(root)
            manifest_path = root / ".tracebook-state" / "migrations" / "health-v1.json"
            archive = root / "00-global" / "health" / "archive" / "health-status-pre-v1.md"
            created = tuple(
                root.joinpath(*entry["path"].split("/"))
                for entry in json.loads(manifest_path.read_text(encoding="utf-8"))["created"]
            )

            rollback_health_migration(root)

            self.assertEqual(
                legacy,
                (root / "00-global" / "health" / "health-status.md").read_bytes(),
            )
            self.assertTrue(all(not path.exists() for path in created))
            self.assertFalse(archive.exists())
            self.assertFalse(manifest_path.exists())
            self.assertEqual(
                legacy_log,
                (root / "00-global" / "health" / "logs" / "2026-06.md").read_bytes(),
            )

    def test_rollback_refuses_all_changes_when_one_created_page_was_modified(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root, _, _ = self._legacy_root(Path(temp))
            ensure_health_layout(root)
            manifest_path = root / ".tracebook-state" / "migrations" / "health-v1.json"
            archive = root / "00-global" / "health" / "archive" / "health-status-pre-v1.md"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            created = tuple(
                root.joinpath(*entry["path"].split("/"))
                for entry in manifest["created"]
            )
            modified = created[-1]
            modified.write_text("human changed this page\n", encoding="utf-8")
            before = {
                path: path.read_bytes()
                for path in (
                    root / "00-global" / "health" / "health-status.md",
                    archive,
                    manifest_path,
                    *created,
                )
            }

            with self.assertRaises(TracebookError) as raised:
                rollback_health_migration(root)

            self.assertEqual("HEALTH_MIGRATION_REVIEW_REQUIRED", raised.exception.code)
            self.assertIn(modified.as_posix(), raised.exception.message.replace("\\", "/"))
            for path, content in before.items():
                self.assertEqual(content, path.read_bytes())

    def test_rollback_refuses_modified_migration_owned_archive_without_changes(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root, _, _ = self._legacy_root(Path(temp))
            ensure_health_layout(root)
            source = root / "00-global" / "health" / "health-status.md"
            archive = root / "00-global" / "health" / "archive" / "health-status-pre-v1.md"
            manifest_path = root / ".tracebook-state" / "migrations" / "health-v1.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            created = tuple(
                root.joinpath(*entry["path"].split("/"))
                for entry in manifest["created"]
            )
            archive.write_bytes(b"human modified the migration archive\n")
            before = {
                path: path.read_bytes()
                for path in (source, archive, manifest_path, *created)
            }

            with self.assertRaises(TracebookError) as raised:
                rollback_health_migration(root)

            self.assertEqual("HEALTH_MIGRATION_REVIEW_REQUIRED", raised.exception.code)
            self.assertIn(archive.as_posix(), raised.exception.message.replace("\\", "/"))
            for path, content in before.items():
                self.assertEqual(content, path.read_bytes())

    def test_manifest_rejects_nonportable_project_created_paths_without_changes(
        self,
    ) -> None:
        invalid_paths = (
            r"01-projects/widgets\api/health-status.md",
            "01-projects/../health-status.md",
            "01-projects/widgets/../health-status.md",
            "01-projects/C:drive/health-status.md",
            "01-projects/Widgets/health-status.md",
            "01-projects/widgets_api/health-status.md",
            "01-projects/widgets--api/health-status.md",
            "/01-projects/widgets/health-status.md",
            "C:/01-projects/widgets/health-status.md",
        )
        for invalid_path in invalid_paths:
            with self.subTest(path=invalid_path), TemporaryDirectory() as temp:
                root, legacy, _ = self._legacy_root(Path(temp))
                source = root / "00-global" / "health" / "health-status.md"
                archive = root / "00-global" / "health" / "archive" / "health-status-pre-v1.md"
                manifest_path = root / ".tracebook-state" / "migrations" / "health-v1.json"
                domain = root / "00-global" / "health" / "scopes" / "domain-status.md"
                unrelated = root / "unrelated.md"
                source.write_bytes(b"aggregate before invalid rollback\n")
                archive.parent.mkdir(parents=True)
                archive.write_bytes(legacy)
                domain.parent.mkdir(parents=True)
                domain.write_bytes(b"created domain page\n")
                unrelated.write_bytes(b"unrelated bytes stay exact\n")

                invalid_content = b"invalid project-created target\n"
                relative = PurePosixPath(invalid_path)
                candidate = root.joinpath(*relative.parts).resolve()
                try:
                    candidate.relative_to(root.resolve())
                except ValueError:
                    candidate = None
                if candidate is not None:
                    candidate.parent.mkdir(parents=True, exist_ok=True)
                    candidate.write_bytes(invalid_content)

                created = [
                    {
                        "path": "00-global/health/archive/health-status-pre-v1.md",
                        "initial_sha256": hashlib.sha256(legacy).hexdigest(),
                    },
                    {
                        "path": "00-global/health/scopes/domain-status.md",
                        "initial_sha256": hashlib.sha256(domain.read_bytes()).hexdigest(),
                    },
                    {
                        "path": invalid_path,
                        "initial_sha256": hashlib.sha256(invalid_content).hexdigest(),
                    },
                ]
                manifest_path.parent.mkdir(parents=True)
                manifest_path.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "source": "00-global/health/health-status.md",
                            "archive": "00-global/health/archive/health-status-pre-v1.md",
                            "created": created,
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                protected = (source, archive, manifest_path, domain, unrelated)
                if candidate is not None:
                    protected += (candidate,)
                before = {path: path.read_bytes() for path in protected}

                with self.assertRaises(TracebookError) as raised:
                    rollback_health_migration(root)

                self.assertEqual(
                    "HEALTH_MIGRATION_REVIEW_REQUIRED",
                    raised.exception.code,
                )
                for path, content in before.items():
                    self.assertEqual(content, path.read_bytes())

    def test_migration_refuses_to_overwrite_inconsistent_archive_or_manifest(
        self,
    ) -> None:
        for conflict in ("archive", "manifest"):
            with self.subTest(conflict=conflict), TemporaryDirectory() as temp:
                root, legacy, _ = self._legacy_root(Path(temp))
                if conflict == "archive":
                    target = root / "00-global" / "health" / "archive" / "health-status-pre-v1.md"
                else:
                    target = root / ".tracebook-state" / "migrations" / "health-v1.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"inconsistent pre-existing target\n")

                with self.assertRaises(TracebookError) as raised:
                    ensure_health_layout(root)

                self.assertEqual("HEALTH_MIGRATION_REVIEW_REQUIRED", raised.exception.code)
                self.assertEqual(
                    legacy,
                    (root / "00-global" / "health" / "health-status.md").read_bytes(),
                )
                self.assertEqual(b"inconsistent pre-existing target\n", target.read_bytes())
                self.assertFalse(health_path(root, "project", "alpha").exists())


if __name__ == "__main__":
    unittest.main()
