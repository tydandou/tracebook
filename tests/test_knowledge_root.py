from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts import knowledge_root


class KnowledgeRootTest(unittest.TestCase):
    def test_initialization_copies_full_governance_layout_once(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "tracebook"

            created = knowledge_root.ensure_knowledge_root(root)

            self.assertIn(root / "AGENTS.md", created)
            self.assertIn(root / "index.md", created)
            self.assertTrue(
                (root / "00-global" / "rules" / "writing-rules.md").is_file()
            )
            self.assertTrue(
                (root / "00-global" / "health" / "health-status.md").is_file()
            )
            self.assertTrue((root / "03-patterns" / "index.md").is_file())
            self.assertEqual(knowledge_root.ensure_knowledge_root(root), [])

    def test_repair_restores_missing_templates_without_overwriting_content(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "tracebook"
            root.mkdir()
            agents = root / "AGENTS.md"
            agents.write_bytes(b"# Custom Root\r\n")

            created = knowledge_root.repair_knowledge_root(root)

            self.assertIsInstance(created, tuple)
            self.assertEqual(b"# Custom Root\r\n", agents.read_bytes())
            self.assertIn(
                root / "00-global" / "health" / "health-status.md",
                created,
            )
            self.assertTrue(
                (root / ".tracebook-state" / "locks" / "maintenance.lock").is_file()
            )


if __name__ == "__main__":
    unittest.main()
