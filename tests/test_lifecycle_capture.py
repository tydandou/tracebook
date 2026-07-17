from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import CaptureRequest, capture, resolve


class LifecycleCaptureTest(unittest.TestCase):
    def _request(self, **overrides: object) -> CaptureRequest:
        values: dict[str, object] = {
            "scope": "project",
            "kind": "decision",
            "category": "adr-0001",
            "title": "Persist idempotency keys first",
            "body": "Persist the message key before applying side effects.",
            "evidence": ("src/consumer.py:L20-L34",),
            "status": "Current",
            "write_intent": "durable",
            "content_kind": "knowledge",
        }
        values.update(overrides)
        return CaptureRequest(**values)

    def _context(self, base: Path):
        repo = base / "business"
        (repo / ".git").mkdir(parents=True)
        return resolve(base / "knowledge", repo)

    def test_high_value_documents_start_with_frontmatter(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))

            capture(context, self._request(), date(2026, 7, 13))
            capture(
                context,
                self._request(
                    scope="domain",
                    kind="domain",
                    category="settlement",
                    title="Settlement term",
                ),
                date(2026, 7, 13),
            )
            capture(
                context,
                self._request(
                    scope="pattern",
                    kind="pattern",
                    category="idempotency",
                    title="Idempotent consumer",
                ),
                date(2026, 7, 13),
            )

            project = context.root / context.record.relative_path
            decision = project / "decisions" / "adr-0001.md"
            domain = context.root / "02-domain" / "settlement.md"
            pattern = context.root / "03-patterns" / "idempotency.md"
            self.assertIn("type: decision", decision.read_text(encoding="utf-8"))
            self.assertIn("status: current", decision.read_text(encoding="utf-8"))
            self.assertIn("type: knowledge", domain.read_text(encoding="utf-8"))
            self.assertIn("scope: domain", domain.read_text(encoding="utf-8"))
            self.assertIn("type: pattern", pattern.read_text(encoding="utf-8"))

    def test_deprecated_knowledge_moves_to_archive_and_updates_index_link(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))

            result = capture(
                context,
                self._request(
                    kind="architecture",
                    category="architecture",
                    title="Retired topology",
                    status="Deprecated",
                ),
                date(2026, 7, 13),
            )

            project = context.root / context.record.relative_path
            archived = project / "archive" / "architecture.md"
            self.assertEqual(result.changed_paths[0], archived)
            self.assertTrue(archived.is_file())
            self.assertIn("Status: Deprecated", archived.read_text(encoding="utf-8"))
            self.assertIn("archive/architecture.md", (project / "index.md").read_text(encoding="utf-8"))

    def test_superseded_knowledge_requires_and_records_a_replacement(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))

            with self.assertRaisesRegex(ValueError, "replacement"):
                capture(
                    context,
                    self._request(status="Superseded"),
                    date(2026, 7, 13),
                )

            capture(
                context,
                self._request(
                    status="Superseded",
                    replacement="decisions/adr-0002.md",
                ),
                date(2026, 7, 13),
            )
            decision = context.root / context.record.relative_path / "decisions" / "adr-0001.md"
            self.assertIn("Replacement: `decisions/adr-0002.md`", decision.read_text(encoding="utf-8"))

    def test_superseded_replacement_must_remain_inside_the_knowledge_root(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))

            for replacement in (
                "../escape.md",
                "decisions/../../escape.md",
                "/absolute/escape.md",
                r"C:\absolute\escape.md",
                "C:escape.md",
                "ftp://host/replacement.md",
            ):
                with self.subTest(replacement=replacement):
                    with self.assertRaisesRegex(ValueError, "replacement"):
                        capture(
                            context,
                            self._request(
                                status="Superseded",
                                replacement=replacement,
                            ),
                            date(2026, 7, 13),
                        )

    def test_project_log_keeps_one_knowledge_heading(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))

            capture(context, self._request(), date(2026, 7, 13))
            capture(
                context,
                self._request(
                    kind="architecture",
                    category="architecture",
                    title="Service topology",
                ),
                date(2026, 7, 13),
            )

            log = context.root / context.record.relative_path / "logs" / "2026-07.md"
            self.assertEqual(log.read_text(encoding="utf-8").count("## Knowledge"), 1)


if __name__ == "__main__":
    unittest.main()
