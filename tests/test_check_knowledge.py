from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts.check_knowledge import run_check


class KnowledgeCheckTest(unittest.TestCase):
    def _health_status(self, root: Path, **overrides: str) -> None:
        values = {
            "Last Light Check": "Not run",
            "Last Regular Check": "Not run",
            "Last Deep Check": "Not run",
            "Changes Since Last Regular Check": "0",
            "New Pages Since Last Regular Check": "0",
            "Pending Confirmations": "0",
            "Missing Sources": "0",
        }
        values.update(overrides)
        status = root / "00-global" / "health" / "health-status.md"
        status.parent.mkdir(parents=True, exist_ok=True)
        status.write_text(
            "# Knowledge Health Status\n\n"
            + "\n".join(f"- {key}: {value}" for key, value in values.items())
            + "\n",
            encoding="utf-8",
        )

    def test_new_unindexed_document_with_no_source_is_reported(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "01-projects" / "sample"
            project.mkdir(parents=True)
            self._health_status(root)
            (project / "index.md").write_text("# Sample\n", encoding="utf-8")
            page = project / "architecture.md"
            page.write_text(
                "# Architecture\nThe service has three replicas.\n",
                encoding="utf-8",
            )

            report = run_check(root, project, [page], date(2026, 7, 13))

            self.assertEqual(report.check_type, "Light")
            self.assertIn("01-projects/sample/architecture.md", report.orphan_pages)
            self.assertIn("01-projects/sample/architecture.md", report.missing_sources)

    def test_evidence_block_satisfies_current_source_requirement(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "01-projects" / "sample"
            project.mkdir(parents=True)
            self._health_status(root)
            page = project / "architecture.md"
            page.write_text(
                "# Architecture\nA verified topology.\n\nEvidence:\n- `src/main.py:L1-L4`\n",
                encoding="utf-8",
            )

            report = run_check(root, project, [page], date(2026, 7, 13))

            self.assertNotIn("01-projects/sample/architecture.md", report.missing_sources)
    def test_plain_source_word_does_not_satisfy_evidence_requirement(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "01-projects" / "sample"
            project.mkdir(parents=True)
            self._health_status(root)
            page = project / "architecture.md"
            page.write_text(
                "# Architecture\nThe source: cache is authoritative.\n",
                encoding="utf-8",
            )

            report = run_check(root, project, [page], date(2026, 7, 14))

            self.assertIn("01-projects/sample/architecture.md", report.missing_sources)

    def test_check_reads_each_project_page_once(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "01-projects" / "sample"
            project.mkdir(parents=True)
            self._health_status(root)
            page = project / "architecture.md"
            page.write_text(
                "# Architecture\nA verified topology.\n\nEvidence:\n- `src/main.py:L1-L4`\n",
                encoding="utf-8",
            )
            original_read_text = Path.read_text
            reads = 0

            def counted_read_text(path: Path, *args: object, **kwargs: object) -> str:
                nonlocal reads
                if path.resolve() == page.resolve():
                    reads += 1
                return original_read_text(path, *args, **kwargs)

            with patch("pathlib.Path.read_text", new=counted_read_text):
                run_check(root, project, [page], date(2026, 7, 14))

            self.assertEqual(reads, 1)
    def test_regular_check_reads_log_page_once(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "01-projects" / "sample"
            log = project / "logs" / "2026-07.md"
            log.parent.mkdir(parents=True)
            self._health_status(root, **{"Changes Since Last Regular Check": "10"})
            log.write_text("# July\n", encoding="utf-8")
            original_read_text = Path.read_text
            reads = 0

            def counted_read_text(path: Path, *args: object, **kwargs: object) -> str:
                nonlocal reads
                if path.resolve() == log.resolve():
                    reads += 1
                return original_read_text(path, *args, **kwargs)

            with patch("pathlib.Path.read_text", new=counted_read_text):
                report = run_check(root, project, [log], date(2026, 7, 14))

            self.assertEqual("Regular", report.check_type)
            self.assertEqual(1, reads)
    def test_reports_missing_wikilinks_and_embeds(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "01-projects" / "sample"
            page = project / "index.md"
            note = project / "notes" / "existing-note.md"
            guide = project / "notes" / "guide.md"
            asset = project / "assets" / "diagram.png"
            note.parent.mkdir(parents=True)
            asset.parent.mkdir(parents=True)
            self._health_status(root)
            note.write_text("# Existing\n", encoding="utf-8")
            guide.write_text("# Guide\n", encoding="utf-8")
            asset.write_text("image", encoding="utf-8")
            page.write_text(
                "\n".join(
                    [
                        "[[existing-note]]",
                        "[[notes/guide|Guide]]",
                        "[[notes/guide#Install]]",
                        "![[assets/diagram.png]]",
                        "[[missing]]",
                        "![[assets/missing.png]]",
                    ]
                ),
                encoding="utf-8",
            )

            report = run_check(root, project, [page], date(2026, 7, 14))

            self.assertIn("01-projects/sample/index.md -> [[missing]]", report.broken_links)
            self.assertIn(
                "01-projects/sample/index.md -> ![[assets/missing.png]]",
                report.broken_links,
            )
            self.assertFalse(
                any("existing-note" in item or "notes/guide" in item for item in report.broken_links)
            )

    def test_reports_ambiguous_bare_wikilinks_without_marking_them_broken(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "01-projects" / "sample"
            page = project / "index.md"
            first = project / "notes" / "duplicate.md"
            second = project / "decisions" / "duplicate.md"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            self._health_status(root)
            first.write_text("# First\n", encoding="utf-8")
            second.write_text("# Second\n", encoding="utf-8")
            page.write_text("[[duplicate]]\n", encoding="utf-8")

            report = run_check(root, project, [page], date(2026, 7, 14))

            self.assertIn(
                "01-projects/sample/index.md -> [[duplicate]] matches 2 pages",
                report.ambiguous_wikilinks,
            )
            self.assertFalse(any("[[duplicate]]" in item for item in report.broken_links))
    def test_reports_missing_relative_links_and_source_map_paths(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "01-projects" / "sample"
            source_root = root / "business"
            project.mkdir(parents=True)
            source_root.mkdir()
            self._health_status(root)
            index = project / "index.md"
            index.write_text(
                "[Missing guide](missing-guide.md)\n",
                encoding="utf-8",
            )
            source_map = project / "source-map.md"
            source_map.write_text("`src/missing.py:L1-L3`\n", encoding="utf-8")

            report = run_check(
                root,
                project,
                [index, source_map],
                date(2026, 7, 13),
                source_root=source_root,
            )

            self.assertIn(
                "01-projects/sample/index.md -> missing-guide.md",
                report.broken_links,
            )
            self.assertIn(
                "01-projects/sample/source-map.md -> src/missing.py",
                report.outdated_paths,
            )

    def test_regular_and_deep_triggers_take_priority_over_light(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "01-projects" / "sample"
            project.mkdir(parents=True)
            page = project / "business-rules.md"
            page.write_text("# Rules\n", encoding="utf-8")

            self._health_status(root, **{"Changes Since Last Regular Check": "10"})
            regular = run_check(root, project, [page], date(2026, 7, 13))
            self.assertEqual(regular.check_type, "Regular")
            self.assertIn(
                "Changes Since Last Regular Check >= 10",
                regular.trigger_reasons,
            )

            self._health_status(root)
            page.write_text("# Rules\n" + "rule\n" * 300, encoding="utf-8")
            deep = run_check(root, project, [page], date(2026, 7, 13))
            self.assertEqual(deep.check_type, "Deep")
            self.assertIn("business-rules.md exceeds 300 lines", deep.trigger_reasons)


if __name__ == "__main__":
    unittest.main()
