from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.check_knowledge import run_check
from plugins.tracebook.skills.tracebook.scripts.knowledge_root import repair_knowledge_root
from plugins.tracebook.skills.tracebook.scripts.project_registry import ensure_project


class IsolatedWorkflowTest(unittest.TestCase):
    def test_external_workflow_never_creates_business_repository_files(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            business = base / "business"
            business.mkdir()
            (business / ".git").mkdir()
            root = base / "external"

            repair_knowledge_root(root)
            record = ensure_project(root, business)
            project = root / record.relative_path
            report = run_check(root, project, [], date(2026, 7, 13))

            self.assertTrue((project / "index.md").is_file())
            self.assertTrue((project / "project-status.md").is_file())
            self.assertFalse((business / "AGENTS.md").exists())
            self.assertFalse((business / ".tracebook").exists())
            self.assertEqual(report.broken_links, [])
            self.assertEqual(report.check_type, "Local")


if __name__ == "__main__":
    unittest.main()
