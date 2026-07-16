from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.knowledge_root import ensure_knowledge_root


class KnowledgeRootTest(unittest.TestCase):
    def test_initialization_copies_full_governance_layout_once(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "tracebook"

            created = ensure_knowledge_root(root)

            self.assertIn(root / "AGENTS.md", created)
            self.assertIn(root / "index.md", created)
            self.assertTrue(
                (root / "00-global" / "rules" / "writing-rules.md").is_file()
            )
            self.assertTrue(
                (root / "00-global" / "health" / "health-status.md").is_file()
            )
            self.assertTrue((root / "03-patterns" / "index.md").is_file())
            self.assertEqual(ensure_knowledge_root(root), [])


if __name__ == "__main__":
    unittest.main()
