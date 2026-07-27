from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts import knowledge_entity
from plugins.tracebook.skills.tracebook.scripts import transaction
from plugins.tracebook.skills.tracebook.scripts.locking import file_lock
from plugins.tracebook.skills.tracebook.scripts.knowledge_entity import validate_request
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
    CaptureRequest,
    capture,
    resolve,
)


class CaptureTest(unittest.TestCase):
    def _request(self, **overrides: object) -> CaptureRequest:
        values: dict[str, object] = {
            "operation": "create",
            "scope": "project",
            "kind": "business-rule",
            "knowledge_id": "refund-status-rule",
            "title": "Refund status rule",
            "body": "REFUNDING cannot be treated as a completed refund.",
            "evidence": ("src/order/status.ts:L20-L38",),
            "status": "current",
            "write_intent": "durable",
            "content_kind": "knowledge",
        }
        values.update(overrides)
        return CaptureRequest(**values)

    def test_project_capture_commits_authority_index_status_and_log_once(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)

            with patch.object(
                knowledge_entity,
                "file_lock",
                wraps=file_lock,
            ) as locked, patch.object(
                knowledge_entity,
                "commit_updates",
                wraps=transaction.commit_updates,
            ) as committed:
                result = capture(context, self._request(), date(2026, 7, 13))

            expected_scope = knowledge_entity.project_lock_name(context.record)
            locked.assert_called_once()
            self.assertEqual(expected_scope, locked.call_args.args[1])
            committed.assert_called_once()
            root, scope, operation, updates = committed.call_args.args
            project = context.root / context.record.relative_path
            authority = project / "knowledge" / "business-rule" / "refund-status-rule.md"
            expected = {
                authority,
                project / "index.md",
                project / "project-status.md",
                project / "logs" / "2026-07.md",
            }
            self.assertEqual(context.root, root)
            self.assertEqual(expected_scope, scope)
            self.assertEqual("capture", operation)
            pointer = (
                context.root
                / ".tracebook-state"
                / "snapshots"
                / context.record.project_id
                / "current.json"
            )
            self.assertTrue(expected.issubset(set(updates)))
            self.assertIn(pointer, set(updates))
            self.assertEqual(expected, set(result.changed_paths))
            self.assertEqual((pointer,), committed.call_args.kwargs["final_targets"])
            self.assertFalse(
                any(call.args[1] == "global-health" for call in locked.call_args_list)
            )

    def test_invalid_capture_is_rejected_before_waiting_for_scope_lock(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            context = resolve(base / "knowledge", repo)

            with patch.object(knowledge_entity, "file_lock") as locked:
                with self.assertRaisesRegex(ValueError, "title"):
                    capture(context, self._request(title=""), date(2026, 7, 13))

            locked.assert_not_called()

    def test_capture_requires_non_empty_title_and_body(self) -> None:
        for overrides, message in (
            ({"title": ""}, "title"),
            ({"title": "  \t"}, "title"),
            ({"body": ""}, "body"),
            ({"body": "\n  "}, "body"),
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(ValueError, message):
                    validate_request(self._request(**overrides))


if __name__ == "__main__":
    unittest.main()
