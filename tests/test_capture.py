from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import CaptureRequest, capture, resolve


class CaptureTest(unittest.TestCase):
    def _request(self, **overrides: object) -> CaptureRequest:
        values: dict[str, object] = {
            "scope": "project",
            "kind": "business-rule",
            "category": "business-rules",
            "title": "Refund status rule",
            "body": "REFUNDING cannot be treated as a completed refund.",
            "evidence": ("src/order/status.ts:L20-L38",),
            "status": "Current",
            "write_intent": "durable",
            "content_kind": "knowledge",
        }
        values.update(overrides)
        return CaptureRequest(**values)

    def test_project_capture_updates_document_index_status_and_monthly_log(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)

            result = capture(context, self._request(), date(2026, 7, 13))

            document = context.root / context.record.relative_path / "business-rules.md"
            self.assertEqual(result.changed_paths[0], document)
            self.assertIn("Evidence:", document.read_text(encoding="utf-8"))
            self.assertIn("business-rules.md", (document.parent / "index.md").read_text(encoding="utf-8"))
            self.assertIn("Refund status rule", (document.parent / "project-status.md").read_text(encoding="utf-8"))
            self.assertTrue((document.parent / "logs" / "2026-07.md").is_file())

    def test_pending_capture_can_be_saved_without_evidence(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)

            result = capture(
                context,
                self._request(
                    title="Pending service topology",
                    evidence=(),
                    status="Pending",
                ),
                date(2026, 7, 13),
            )

            self.assertTrue(result.changed_paths)
            document = context.root / context.record.relative_path / "business-rules.md"
            self.assertIn("Status: Pending", document.read_text(encoding="utf-8"))

    def test_domain_pattern_decision_and_synthesis_captures_use_governed_routes(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)

            domain = capture(
                context,
                self._request(
                    scope="domain",
                    kind="domain",
                    category="terminology",
                    title="Settlement term",
                ),
                date(2026, 7, 13),
            )
            pattern = capture(
                context,
                self._request(
                    scope="pattern",
                    kind="pattern",
                    category="backend",
                    title="Idempotent consumer",
                ),
                date(2026, 7, 13),
            )
            decision = capture(
                context,
                self._request(
                    kind="decision",
                    category="adr-0001",
                    title="Persist idempotency keys first",
                ),
                date(2026, 7, 13),
            )
            synthesis = capture(
                context,
                self._request(
                    kind="synthesis",
                    category="refund-flow",
                    title="Refund processing flow",
                ),
                date(2026, 7, 13),
            )

            self.assertTrue((context.root / "02-domain" / "terminology.md").is_file())
            self.assertTrue((context.root / "03-patterns" / "backend.md").is_file())
            project = context.root / context.record.relative_path
            self.assertTrue((project / "decisions" / "adr-0001.md").is_file())
            self.assertTrue((project / "synthesis" / "refund-flow.md").is_file())
            self.assertTrue(domain.changed_paths)
            self.assertTrue(pattern.changed_paths)
            self.assertTrue(decision.changed_paths)
            self.assertTrue(synthesis.changed_paths)

    def test_capture_rejects_non_durable_or_unsafe_requests(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)

            for overrides, message in (
                ({"content_kind": "raw"}, "content kind"),
                ({"content_kind": "temporary"}, "content kind"),
                ({"write_intent": "answer"}, "write intent"),
                ({"category": "../escape"}, "category"),
                ({"evidence": (), "status": "Current"}, "evidence"),
            ):
                with self.subTest(overrides=overrides):
                    with self.assertRaisesRegex(ValueError, message):
                        capture(context, self._request(**overrides), date(2026, 7, 13))

            skipped = capture(
                context,
                self._request(user_prohibits_write=True),
                date(2026, 7, 13),
            )
            self.assertEqual(skipped.changed_paths, ())
            self.assertTrue(skipped.skipped)


if __name__ == "__main__":
    unittest.main()