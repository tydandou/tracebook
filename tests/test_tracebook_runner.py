import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts import tracebook_runner
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import default_root, initialize, resolve


class TracebookRunnerTest(unittest.TestCase):
    def test_default_root_uses_optional_environment_override(self) -> None:
        with patch.dict(os.environ, {"TRACEBOOK_ROOT": "D:/custom-tracebook"}):
            self.assertEqual(Path("D:/custom-tracebook"), default_root())

        with patch.dict(os.environ, {"TRACEBOOK_ROOT": ""}):
            self.assertEqual(Path("~/.tracebook").expanduser(), default_root())
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
                    self.assertIn(f"project-{project.slug}", active_locks)
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


if __name__ == "__main__":
    unittest.main()
