from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import CaptureRequest, capture, check, resolve


class GrowthControlsTest(unittest.TestCase):
    def _context(self, base: Path):
        repo = base / "business"
        (repo / ".git").mkdir(parents=True)
        return resolve(base / "knowledge", repo), repo

    def _request(self, **overrides: object) -> CaptureRequest:
        values: dict[str, object] = {
            "scope": "project",
            "kind": "business-rule",
            "category": "business-rules",
            "title": "Refund rule",
            "body": "REFUNDING is not a completed refund.",
            "evidence": ("src/order.py:L1-L3",),
            "status": "Current",
            "write_intent": "durable",
            "content_kind": "knowledge",
        }
        values.update(overrides)
        return CaptureRequest(**values)

    def test_capture_reports_new_pages_and_check_accumulates_them(self) -> None:
        with TemporaryDirectory() as temp:
            context, repo = self._context(Path(temp))

            captured = capture(context, self._request(), date(2026, 7, 13))
            result = check(
                context,
                list(captured.changed_paths),
                date(2026, 7, 13),
                source_root=repo,
                new_paths=list(captured.new_paths),
            )

            health = (context.root / "00-global" / "health" / "health-status.md").read_text(encoding="utf-8")
            document = context.root / context.record.relative_path / "business-rules.md"
            self.assertEqual(captured.new_paths, (document,))
            self.assertIn("New Pages Since Last Regular Check: 1", health)
            self.assertEqual(result.report.check_type, "Light")

    def test_large_project_document_requires_topic_and_writes_a_child_page(self) -> None:
        with TemporaryDirectory() as temp:
            context, _ = self._context(Path(temp))
            project = context.root / context.record.relative_path
            main = project / "business-rules.md"
            main.write_text("# Business Rules\n" + "rule\n" * 300, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "topic"):
                capture(context, self._request(), date(2026, 7, 13))

            result = capture(
                context,
                self._request(topic="refunds"),
                date(2026, 7, 13),
            )

            child = project / "business-rules" / "refunds.md"
            self.assertEqual(result.changed_paths[0], child)
            self.assertTrue(child.is_file())
            self.assertIn("business-rules/refunds.md", (project / "index.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
