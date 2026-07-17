from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts import capture as capture_module
from plugins.tracebook.skills.tracebook.scripts import transaction
from plugins.tracebook.skills.tracebook.scripts.locking import file_lock
from plugins.tracebook.skills.tracebook.scripts import tracebook_runner
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import CaptureRequest, capture, resolve


validate_capture = getattr(tracebook_runner, "validate_capture", None)
if validate_capture is None:
    validate_capture = tracebook_runner._validate_capture


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

    def test_project_capture_commits_document_index_status_and_log_once(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)

            with patch.object(
                capture_module,
                "file_lock",
                wraps=file_lock,
                create=True,
            ) as locked, patch.object(
                capture_module,
                "commit_updates",
                wraps=transaction.commit_updates,
                create=True,
            ) as committed:
                result = capture(context, self._request(), date(2026, 7, 13))

            expected_scope = f"project-{context.record.slug}"
            locked.assert_called_once()
            self.assertEqual(expected_scope, locked.call_args.args[1])
            committed.assert_called_once()
            root, scope, operation, updates = committed.call_args.args
            project = context.root / context.record.relative_path
            expected = {
                project / "business-rules.md",
                project / "index.md",
                project / "project-status.md",
                project / "logs" / "2026-07.md",
            }
            self.assertEqual(context.root, root)
            self.assertEqual(expected_scope, scope)
            self.assertEqual("capture", operation)
            self.assertEqual(expected, set(updates))
            self.assertEqual(expected, set(result.changed_paths))
            self.assertFalse(
                any(call.args[1] == "global-health" for call in locked.call_args_list)
            )

    def test_invalid_capture_is_rejected_before_waiting_for_scope_lock(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)

            with patch.object(
                capture_module,
                "file_lock",
                create=True,
            ) as locked:
                with self.assertRaisesRegex(ValueError, "title"):
                    capture(
                        context,
                        self._request(title=""),
                        date(2026, 7, 13),
                    )

            locked.assert_not_called()

    def test_unsafe_provided_topic_is_rejected_before_scope_lock(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)

            for topic in ("../escape", "nested/topic", "Refunds", ""):
                with self.subTest(topic=topic), patch.object(
                    capture_module,
                    "file_lock",
                    wraps=file_lock,
                ) as locked:
                    with self.assertRaisesRegex(ValueError, "topic"):
                        capture(
                            context,
                            self._request(topic=topic),
                            date(2026, 7, 13),
                        )

                    locked.assert_not_called()

    def test_capture_lock_name_matches_transaction_scope(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)

            self.assertEqual(
                f"project-{context.record.slug}",
                tracebook_runner.capture_lock_name(context.record, self._request()),
            )
            self.assertEqual(
                "domain",
                tracebook_runner.capture_lock_name(
                    context.record,
                    self._request(
                        scope="domain",
                        kind="domain",
                        category="settlement",
                    ),
                ),
            )
            self.assertEqual(
                "pattern",
                tracebook_runner.capture_lock_name(
                    context.record,
                    self._request(
                        scope="pattern",
                        kind="pattern",
                        category="idempotency",
                    ),
                ),
            )

    def test_same_title_with_different_body_creates_distinct_events(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)

            first = capture(context, self._request(), date(2026, 7, 13))
            second_body = "REFUNDING remains incomplete until settlement succeeds."
            second = capture(
                context,
                self._request(body=second_body),
                date(2026, 7, 14),
            )

            self.assertNotEqual(first.event_id, second.event_id)
            self.assertFalse(second.skipped)
            project = context.root / context.record.relative_path
            document_content = (project / "business-rules.md").read_text(
                encoding="utf-8"
            )
            log_content = (project / "logs" / "2026-07.md").read_text(
                encoding="utf-8"
            )
            status_content = (project / "project-status.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(self._request().body, document_content)
            self.assertIn(second_body, document_content)
            for event_id in (first.event_id, second.event_id):
                marker = f"<!-- tracebook:event:{event_id} -->"
                self.assertEqual(1, document_content.count(marker))
                self.assertEqual(1, log_content.count(marker))
            self.assertIn(
                f"<!-- tracebook:last-event:{second.event_id} -->",
                status_content,
            )

    def test_capture_public_interfaces_remain_available_from_runner(self) -> None:
        self.assertEqual(
            CaptureRequest.__module__,
            "plugins.tracebook.skills.tracebook.scripts.capture",
        )
        for name in (
            "CaptureResult",
            "validate_capture",
            "capture_lock_name",
            "capture_knowledge",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(tracebook_runner, name))

    def test_capture_requires_non_empty_title_and_body(self) -> None:
        for overrides, message in (
            ({"title": ""}, "title"),
            ({"title": "  \t"}, "title"),
            ({"body": ""}, "body"),
            ({"body": "\n  "}, "body"),
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(ValueError, message):
                    validate_capture(self._request(**overrides))

    def test_current_capture_rejects_blank_or_unclassified_evidence(self) -> None:
        for evidence in (
            ("  ",),
            ("observed during investigation",),
            ("test:  ",),
            ("command:\t",),
            ("human:",),
            ("README",),
            ("ftp://host/file",),
            ("HTTP://host/file",),
            ("ssh://host/file.py",),
            ("/absolute/source.py:L2",),
            (r"C:\absolute\source.py:L2",),
            ("C:relative/file.py",),
            ("src/../secret.py:L2",),
        ):
            with self.subTest(evidence=evidence):
                with self.assertRaisesRegex(ValueError, "evidence"):
                    validate_capture(self._request(evidence=evidence))

    def test_capture_accepts_every_approved_evidence_form_without_io(self) -> None:
        approved = (
            "http://example.test/incidents/42",
            "https://example.test/incidents/42",
            "test: python -m unittest tests.test_capture",
            "command: git show --stat HEAD",
            "human: confirmed by the service owner",
            "src/order/status.ts:L20-L38",
            r"src\order\status.ts:L20",
            "README.md",
            "generated/schema",
        )

        for evidence in approved:
            with self.subTest(evidence=evidence):
                validate_capture(self._request(evidence=(evidence,)))

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
            self.assertEqual(domain.health_scope, "domain")
            self.assertEqual(pattern.health_scope, "pattern")
            self.assertEqual(decision.health_scope, "project")
            self.assertEqual(synthesis.health_scope, "project")

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
