from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
import json
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts import knowledge_root
from plugins.tracebook.skills.tracebook.scripts.errors import TracebookError
from plugins.tracebook.skills.tracebook.scripts.locking import file_lock


class KnowledgeRootTest(unittest.TestCase):
    def test_concurrent_initializer_waits_for_schema_publication(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "knowledge"
            writing, resume, attempted = Event(), Event(), Event()
            original_write = knowledge_root.atomic_write_text

            def pause_first_write(*args, **kwargs):
                if not writing.is_set():
                    writing.set()
                    if not resume.wait(10):
                        raise TimeoutError("Initializer barrier timed out")
                return original_write(*args, **kwargs)

            @contextmanager
            def observe_lock(*args, **kwargs):
                if writing.is_set():
                    attempted.set()
                with file_lock(*args, **kwargs):
                    yield

            with patch.object(knowledge_root, "atomic_write_text", side_effect=pause_first_write), \
                    patch.object(knowledge_root, "file_lock", observe_lock), \
                    ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(knowledge_root.repair_knowledge_root, root)
                try:
                    self.assertTrue(writing.wait(5))
                    self.assertTrue((root / "00-global").is_dir())
                    self.assertFalse((root / ".tracebook-state/schema.json").exists())
                    second = executor.submit(knowledge_root.repair_knowledge_root, root)
                    second.add_done_callback(lambda future: attempted.set())
                    self.assertTrue(attempted.wait(5))
                    self.assertFalse(second.done(), "Initializer must wait for the active writer")
                finally:
                    resume.set()
                self.assertTrue(first.result(timeout=10))
                self.assertEqual((), second.result(timeout=10))
            self.assertEqual(2, knowledge_root.schema_for_root(root))

    def test_schema_is_checked_after_waiting_for_maintenance(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "knowledge"
            attempted = Event()

            @contextmanager
            def observe_lock(*args, **kwargs):
                attempted.set()
                with file_lock(*args, **kwargs):
                    yield

            with patch.object(knowledge_root, "file_lock", observe_lock), \
                    ThreadPoolExecutor(max_workers=1) as executor:
                with file_lock(root, "maintenance"):
                    future = executor.submit(knowledge_root.repair_knowledge_root, root)
                    self.assertTrue(attempted.wait(5))
                    (root / ".tracebook-state/schema.json").write_text('{"version": 1}', encoding="utf-8")
                with self.assertRaises(TracebookError) as raised:
                    future.result(timeout=10)
            self.assertEqual("UNSUPPORTED_SCHEMA", raised.exception.code)
            self.assertFalse((root / "00-global").exists())

    def test_legacy_and_invalid_schema_are_not_repaired_or_migrated(self) -> None:
        for config, expected in ((None, "UNSUPPORTED_SCHEMA"), ('{"version": 1}', "UNSUPPORTED_SCHEMA"),
                                 ('invalid', "INVALID_SCHEMA_CONFIG")):
            with self.subTest(config=config), TemporaryDirectory() as temp:
                root = Path(temp) / "knowledge"
                page = root / "01-projects/retained.md"
                page.parent.mkdir(parents=True)
                page.write_bytes(b"Existing knowledge\r\n")
                schema = root / ".tracebook-state/schema.json"
                if config is not None:
                    schema.parent.mkdir()
                    schema.write_text(config, encoding="utf-8")
                with self.assertRaises(TracebookError) as raised:
                    knowledge_root.repair_knowledge_root(root)
                self.assertEqual(expected, raised.exception.code)
                self.assertEqual(b"Existing knowledge\r\n", page.read_bytes())
                self.assertFalse((root / "AGENTS.md").exists())
                self.assertEqual(config, schema.read_text(encoding="utf-8") if schema.exists() else None)

    def test_contended_initialization_retains_explicit_lock_timeout(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "knowledge"
            knowledge_root.repair_knowledge_root(root)
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            with file_lock(root, "maintenance"), \
                    patch.object(knowledge_root, "file_lock", partial(file_lock, timeout=0.05)), \
                    ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(knowledge_root.repair_knowledge_root, root)
                with self.assertRaises(TracebookError) as raised:
                    future.result(timeout=5)
            self.assertEqual("LOCK_TIMEOUT", raised.exception.code)
            self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()})

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

            created = list(knowledge_root.repair_knowledge_root(root))

            self.assertIn(root / "AGENTS.md", created)
            self.assertIn(root / "index.md", created)
            self.assertTrue(
                (root / "00-global" / "rules" / "writing-rules.md").is_file()
            )
            self.assertTrue(
                (root / "00-global" / "health" / "health-status.md").is_file()
            )
            self.assertTrue((root / "03-patterns" / "index.md").is_file())
            self.assertEqual(list(knowledge_root.repair_knowledge_root(root)), [])

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
