from datetime import date
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.health_state import health_path
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

            health = health_path(
                context.root, "project", context.record.slug
            ).read_text(encoding="utf-8")
            document = context.root / context.record.relative_path / "business-rules.md"
            self.assertEqual(captured.new_paths, (document,))
            self.assertIn(
                f"Changes Since Last Regular Check: {len(set(captured.changed_paths))}",
                health,
            )
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

    def test_capture_event_is_stable_across_dates_and_repeated_content_is_a_no_op(self) -> None:
        with TemporaryDirectory() as temp:
            context, _ = self._context(Path(temp))
            request = self._request()
            destination = (
                Path(context.record.relative_path) / "business-rules.md"
            ).as_posix()
            canonical = {
                "project": context.record.identity,
                "destination": destination,
                "title": request.title,
                "body": request.body,
                "evidence": list(request.evidence),
                "status": request.status,
                "replacement": request.replacement,
            }
            expected_event_id = hashlib.sha256(
                json.dumps(
                    canonical,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:16]

            first = capture(context, request, date(2026, 7, 13))
            second = capture(context, request, date(2026, 8, 2))

            self.assertEqual(first.event_id, expected_event_id)
            self.assertEqual(second.event_id, expected_event_id)
            self.assertEqual(first.health_scope, "project")
            self.assertTrue(second.skipped)
            self.assertEqual(second.changed_paths, ())
            self.assertEqual(second.new_paths, ())
            document = context.root / destination
            marker = f"<!-- tracebook:event:{expected_event_id} -->"
            self.assertEqual(document.read_text(encoding="utf-8").count(marker), 1)
            july_log = document.parent / "logs" / "2026-07.md"
            self.assertIn(marker, july_log.read_text(encoding="utf-8"))
            self.assertFalse((document.parent / "logs" / "2026-08.md").exists())

    def test_retry_without_topic_remains_idempotent_after_crossing_split_threshold(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            context, _ = self._context(Path(temp))
            project = context.root / context.record.relative_path
            main = project / "business-rules.md"
            main.write_text(
                "# Business Rules\n" + "rule\n" * 299,
                encoding="utf-8",
            )
            self.assertEqual(300, len(main.read_text(encoding="utf-8").splitlines()))
            request = self._request(title="Threshold crossing rule")

            first = capture(context, request, date(2026, 7, 13))
            self.assertGreater(
                len(main.read_text(encoding="utf-8").splitlines()),
                300,
            )
            try:
                second = capture(context, request, date(2026, 8, 2))
            except ValueError as error:
                self.fail(f"idempotent retry unexpectedly required topic: {error}")

            self.assertTrue(second.skipped)
            self.assertEqual(first.event_id, second.event_id)
            self.assertEqual((), second.changed_paths)
            self.assertFalse((project / "logs" / "2026-08.md").exists())

    def test_retry_with_topic_uses_original_base_event_after_threshold_change(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            context, _ = self._context(Path(temp))
            project = context.root / context.record.relative_path
            main = project / "business-rules.md"
            main.write_text(
                "# Business Rules\n" + "rule\n" * 299,
                encoding="utf-8",
            )
            request = self._request(
                title="Preclassified threshold rule",
                topic="refunds",
            )

            first = capture(context, request, date(2026, 7, 13))
            self.assertEqual(main, first.changed_paths[0])
            self.assertGreater(
                len(main.read_text(encoding="utf-8").splitlines()),
                300,
            )
            second = capture(context, request, date(2026, 8, 2))

            self.assertTrue(second.skipped)
            self.assertEqual(first.event_id, second.event_id)
            self.assertEqual((), second.changed_paths)
            self.assertFalse((project / "business-rules" / "refunds.md").exists())
            self.assertFalse((project / "logs" / "2026-08.md").exists())

    def test_retry_uses_original_child_event_after_aggregate_is_compressed(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            context, _ = self._context(Path(temp))
            project = context.root / context.record.relative_path
            aggregate = project / "business-rules.md"
            aggregate.write_text(
                "# Business Rules\n" + "rule\n" * 300,
                encoding="utf-8",
            )
            request = self._request(
                title="Child-routed threshold rule",
                topic="refunds",
            )

            first = capture(context, request, date(2026, 7, 13))
            child = project / "business-rules" / "refunds.md"
            first_child = child.read_text(encoding="utf-8")
            july_log = (project / "logs" / "2026-07.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(child, first.changed_paths[0])

            aggregate.write_text("# Business Rules\n", encoding="utf-8")
            second = capture(context, request, date(2026, 8, 2))

            self.assertTrue(second.skipped)
            self.assertEqual(first.event_id, second.event_id)
            self.assertEqual((), second.changed_paths)
            self.assertEqual(first_child, child.read_text(encoding="utf-8"))
            self.assertNotIn(request.body, aggregate.read_text(encoding="utf-8"))
            self.assertEqual(
                july_log,
                (project / "logs" / "2026-07.md").read_text(encoding="utf-8"),
            )
            self.assertFalse((project / "logs" / "2026-08.md").exists())


if __name__ == "__main__":
    unittest.main()
