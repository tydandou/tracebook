import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import default_root, initialize, resolve


class TracebookRunnerTest(unittest.TestCase):
    def test_default_root_uses_optional_environment_override(self) -> None:
        with patch.dict(os.environ, {"TRACEBOOK_ROOT": "D:/custom-tracebook"}):
            self.assertEqual(Path("D:/custom-tracebook"), default_root())

        with patch.dict(os.environ, {"TRACEBOOK_ROOT": ""}):
            self.assertEqual(Path("~/.tracebook").expanduser(), default_root())
    def test_initialize_repairs_missing_files_without_overwriting_existing_content(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "knowledge"
            root.mkdir()
            agents = root / "AGENTS.md"
            agents.write_text("# Custom Root\n", encoding="utf-8")

            result = initialize(root)

            self.assertEqual(agents.read_text(encoding="utf-8"), "# Custom Root\n")
            self.assertIn(root / "00-global" / "health" / "health-status.md", result.created_paths)
            self.assertTrue((root / "01-projects" / "index.md").is_file())

    def test_resolve_returns_ordered_context_for_current_project(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
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
                ),
            )
            self.assertFalse((repo / "AGENTS.md").exists())


if __name__ == "__main__":
    unittest.main()
