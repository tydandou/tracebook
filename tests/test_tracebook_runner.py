import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts import health_state, tracebook_runner
from plugins.tracebook.skills.tracebook.scripts.health_state import HealthAggregateRebuildError
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import default_root, initialize, preflight, resolve


class TracebookRunnerTest(unittest.TestCase):
    def test_default_root_uses_optional_environment_override(self) -> None:
        with patch.dict(os.environ, {"TRACEBOOK_ROOT": "D:/custom-tracebook"}):
            self.assertEqual(Path("D:/custom-tracebook"), default_root())

        with patch.dict(os.environ, {"TRACEBOOK_ROOT": ""}):
            self.assertEqual(Path("~/.tracebook").expanduser(), default_root())

    def test_cli_reports_root_provenance_and_explicit_override(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            other = base / "other-knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            payloads: list[dict[str, object]] = []

            with patch.dict(os.environ, {"TRACEBOOK_ROOT": str(other)}), patch.object(
                tracebook_runner, "_write_payload", side_effect=payloads.append
            ):
                result = tracebook_runner.main(
                    ["resolve", "--root", str(root), "--cwd", str(repo)]
                )

            self.assertEqual(0, result)
            payload = payloads[-1]
            self.assertEqual("argument", payload["root_source"])
            self.assertFalse(payload["root_existed"])
            self.assertTrue(payload["root_created"])
            self.assertFalse(payload["root_initialized_before"])
            self.assertTrue(payload["root_initialized"])
            self.assertIn("overrides TRACEBOOK_ROOT", payload["root_warning"])

    def test_preflight_reports_environment_root_without_creating_it(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            target = base / "new-service"
            payloads: list[dict[str, object]] = []

            with patch.dict(os.environ, {"TRACEBOOK_ROOT": str(root)}), patch.object(
                tracebook_runner, "_write_payload", side_effect=payloads.append
            ):
                result = tracebook_runner.main(
                    ["preflight", "--cwd", str(target)]
                )

            self.assertEqual(0, result)
            payload = payloads[-1]
            self.assertEqual("environment", payload["root_source"])
            self.assertFalse(payload["root_existed"])
            self.assertFalse(payload["root_initialized"])
            self.assertFalse(root.exists())
    def test_initialize_repairs_missing_files_without_overwriting_existing_content(self) -> None:
        with TemporaryDirectory() as temp:
            root = (Path(temp) / "knowledge").resolve()
            root.mkdir()
            agents = root / "AGENTS.md"
            agents.write_text("# Custom Root\n", encoding="utf-8")

            result = initialize(root)

            self.assertEqual(agents.read_text(encoding="utf-8"), "# Custom Root\n")
            self.assertIn(root / "00-global" / "health" / "health-status.md", result.created_paths)
            self.assertTrue((root / "01-projects" / "index.md").is_file())

    def test_initialize_uses_the_manual_zh_root_configuration(self) -> None:
        with TemporaryDirectory() as temp:
            root = (Path(temp) / "knowledge").resolve()
            config = root / ".tracebook-state" / "config.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                '{"version": 1, "knowledge_language": "zh"}',
                encoding="utf-8",
            )

            initialize(root)

            self.assertIn("知识库", (root / "index.md").read_text(encoding="utf-8"))

    def test_resolve_creates_new_project_pages_in_the_configured_language(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            config = root / ".tracebook-state" / "config.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                '{"version": 1, "knowledge_language": "zh"}',
                encoding="utf-8",
            )

            context = resolve(root, repo)
            project = root / context.record.relative_path

            self.assertEqual("zh", context.knowledge_language)
            self.assertIn("项目概览", (project / "index.md").read_text(encoding="utf-8"))
            self.assertIn("项目状态", (project / "project-status.md").read_text(encoding="utf-8"))

    def test_initialize_delegates_to_knowledge_root_repair(self) -> None:
        root = Path.cwd() / "knowledge"
        template = Path.cwd() / "template"
        repaired = (root / "AGENTS.md",)

        with patch(
            "plugins.tracebook.skills.tracebook.scripts.tracebook_runner.repair_knowledge_root",
            return_value=repaired,
        ) as repair:
            result = initialize(root, template)

        repair.assert_called_once_with(root, template)
        self.assertEqual(root, result.root)
        self.assertEqual(repaired, result.created_paths)

    def test_resolve_returns_ordered_context_for_current_project(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)

            context = resolve(root, repo)

            self.assertEqual(
                context.read_paths,
                (
                    root / "AGENTS.md",
                    root / "00-global" / "health" / "health-status.md",
                    root / context.record.relative_path / "index.md",
                    root / context.record.relative_path / "project-status.md",
                    root / context.record.relative_path / "health-status.md",
                ),
            )
            self.assertEqual("en", context.knowledge_language)
            self.assertFalse((repo / "AGENTS.md").exists())
            self.assertFalse(
                (root / ".tracebook-state" / "migrations" / "health-v1.json").exists()
            )

    def test_preflight_does_not_initialize_or_register_a_new_target(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            target = base / "new-service"

            result = preflight(root, target)

            self.assertFalse(result["target_exists"])
            self.assertFalse(result["registered"])
            self.assertIsNone(result["project"])
            self.assertFalse(root.exists())

    def test_preflight_returns_an_existing_registered_project_without_writing(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "business"; repo.mkdir()
            resolved = resolve(root, repo)
            registry_before = (root / "registry.json").read_bytes()

            result = preflight(root, repo)

            self.assertTrue(result["registered"])
            self.assertEqual(resolved.record.project_id, result["project"]["project_id"])
            self.assertEqual(registry_before, (root / "registry.json").read_bytes())

    def test_resolve_ensures_project_health_while_holding_the_project_lock(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            active_locks: list[str] = []
            actual_ensure = tracebook_runner.ensure_health_layout

            @contextmanager
            def recording_lock(
                lock_root: Path,
                name: str,
                *,
                operation: str,
                **_: object,
            ):
                self.assertEqual(root.resolve(), lock_root.resolve())
                active_locks.append(name)
                try:
                    yield
                finally:
                    active_locks.remove(name)

            def checking_ensure(health_root: Path, project=None):
                if project is not None:
                    self.assertIn(tracebook_runner.project_lock_name(project), active_locks)
                return actual_ensure(health_root, project)

            with patch.object(tracebook_runner, "file_lock", recording_lock), patch.object(
                tracebook_runner,
                "ensure_health_layout",
                side_effect=checking_ensure,
            ):
                context = resolve(root, repo)

            self.assertTrue(
                (root / context.record.relative_path / "health-status.md").is_file()
            )

    def test_check_and_audit_use_health_preparation_without_seeding_snapshots(self) -> None:
        for command in ("check", "audit"):
            with self.subTest(command=command), TemporaryDirectory() as temp:
                base = Path(temp).resolve()
                root = base / "knowledge"
                repo = base / "business"
                (repo / ".git").mkdir(parents=True)
                context = resolve(root, repo)
                versions = (
                    root
                    / ".tracebook-state"
                    / "snapshots"
                    / context.record.project_id
                    / "versions"
                )
                before = sorted(path.name for path in versions.iterdir())

                payloads: list[dict[str, object]] = []
                with patch.object(
                    tracebook_runner,
                    "ensure_for_health",
                    wraps=tracebook_runner.ensure_for_health,
                ) as prepare, patch.object(
                    tracebook_runner,
                    "resolve",
                    side_effect=AssertionError("health commands must not call resolve"),
                ), patch.object(
                    tracebook_runner,
                    "registered_project",
                    side_effect=AssertionError(
                        "health preparation must not resolve project identity twice"
                    ),
                ), patch.object(
                    tracebook_runner,
                    "_write_payload",
                    side_effect=payloads.append,
                ):
                    result = tracebook_runner.main(
                        [
                            command,
                            "--root",
                            str(root),
                            "--cwd",
                            str(repo),
                            "--today",
                            "2026-08-17",
                        ]
                    )

                self.assertEqual(0, result)
                prepare.assert_called_once_with(root, repo)
                self.assertIn("findings", payloads[-1])
                self.assertEqual(
                    before,
                    sorted(path.name for path in versions.iterdir()),
                )

    def test_first_direct_health_command_registers_project_in_global_health(self) -> None:
        for command in ("check", "audit"):
            with self.subTest(command=command), TemporaryDirectory() as temp:
                base = Path(temp).resolve()
                root = base / "knowledge"
                first_repo = base / "first"
                second_repo = base / "second"
                (first_repo / ".git").mkdir(parents=True)
                (second_repo / ".git").mkdir(parents=True)
                resolve(root, first_repo)
                aggregate = root / "00-global" / "health" / "health-status.md"
                before = aggregate.read_text(encoding="utf-8")
                self.assertEqual(1, before.count("| project |"))
                payloads: list[dict[str, object]] = []

                with patch.object(tracebook_runner, "_write_payload", side_effect=payloads.append):
                    result = tracebook_runner.main(
                        [
                            command,
                            "--root",
                            str(root),
                            "--cwd",
                            str(second_repo),
                            "--today",
                            "2026-08-20",
                        ]
                    )

                self.assertEqual(0, result)
                after = aggregate.read_text(encoding="utf-8")
                self.assertEqual(2, after.count("| project |"))
                self.assertNotEqual(before, after)
                self.assertIn(str(aggregate), payloads[-1]["changed_paths"])
                record = tracebook_runner.registered_project(root, second_repo)
                self.assertIsNotNone(record)
                assert record is not None
                _, mode = tracebook_runner.project_knowledge_root(
                    root,
                    record,
                    operation="test",
                )
                self.assertEqual("snapshot", mode)

    def test_first_direct_local_check_aggregate_failure_preserves_original_error(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            first_repo = base / "first"
            second_repo = base / "second"
            (first_repo / ".git").mkdir(parents=True)
            (second_repo / ".git").mkdir(parents=True)
            resolve(root, first_repo)
            context = tracebook_runner.ensure_for_health(root, second_repo)
            failure = RuntimeError("aggregate rebuild failed")

            with patch.object(
                health_state,
                "rebuild_global_health",
                side_effect=failure,
            ), self.assertRaises(HealthAggregateRebuildError) as raised:
                tracebook_runner.check(context, [], date(2026, 8, 20))

            self.assertEqual((), raised.exception.committed_paths)
            self.assertIs(failure, raised.exception.aggregate_error)


if __name__ == "__main__":
    unittest.main()
