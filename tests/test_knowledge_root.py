from pathlib import Path
import json
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts import knowledge_root
from plugins.tracebook.skills.tracebook.scripts.errors import TracebookError


class KnowledgeRootTest(unittest.TestCase):
    def test_language_config_defaults_to_english_and_accepts_manual_zh_selection(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "tracebook"

            self.assertEqual("en", knowledge_root.language_for_root(root))

            config = root / ".tracebook-state" / "config.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                json.dumps({"version": 1, "knowledge_language": "zh"}),
                encoding="utf-8",
            )

            self.assertEqual("zh", knowledge_root.language_for_root(root))

            created = knowledge_root.repair_knowledge_root(root)
            expected = {
                source.relative_to(knowledge_root.DEFAULT_TEMPLATE)
                for source in knowledge_root.DEFAULT_TEMPLATE.rglob("*")
                if source.is_file()
            }
            self.assertTrue(all((root / relative).is_file() for relative in expected))
            self.assertIn("写入规则", (root / "00-global" / "rules" / "writing-rules.md").read_text(encoding="utf-8"))

    def test_invalid_manual_language_config_fails_before_root_repair(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "tracebook"
            config = root / ".tracebook-state" / "config.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                '{"version": 1, "knowledge_language": "fr"}',
                encoding="utf-8",
            )

            with self.assertRaises(TracebookError) as raised:
                knowledge_root.repair_knowledge_root(root)

            self.assertEqual("INVALID_LANGUAGE_CONFIG", raised.exception.code)
            self.assertFalse((root / "AGENTS.md").exists())

    def test_default_english_repair_does_not_create_a_language_config(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "tracebook"

            knowledge_root.repair_knowledge_root(root)

            self.assertFalse((root / ".tracebook-state" / "config.json").exists())

    def test_initialization_copies_full_governance_layout_once(self) -> None:
        with TemporaryDirectory() as temp:
            root = (Path(temp) / "tracebook").resolve()

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
            root = (Path(temp) / "tracebook").resolve()
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
