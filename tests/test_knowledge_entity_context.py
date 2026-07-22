from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.capture import CaptureRequest
from plugins.tracebook.skills.tracebook.scripts.errors import TracebookError
from plugins.tracebook.skills.tracebook.scripts.knowledge_root import repair_knowledge_root
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import capture, retrieve_context, resolve


class KnowledgeEntityContextTest(unittest.TestCase):
    def _request(self, **overrides: object) -> CaptureRequest:
        values: dict[str, object] = {
            "operation": "create", "scope": "project", "kind": "business-rule",
            "category": "business-rules", "knowledge_id": "order-retry-idempotency",
            "title": "订单重试幂等机制", "body": "订单重试通过 request_id 防止重复扣款。",
            "evidence": ("src/order/retry.py:L42-L88",), "status": "current",
            "write_intent": "durable", "content_kind": "knowledge",
        }
        values.update(overrides)
        return CaptureRequest(**values)

    def _context(self, base: Path):
        repo = base / "repo"; repo.mkdir(); (repo / ".git").mkdir()
        return resolve(base / "knowledge", repo)

    def test_schema_v2_create_revise_and_context_history(self) -> None:
        with TemporaryDirectory() as temp:
            resolved = self._context(Path(temp))
            first = capture(resolved, self._request(), date(2026, 7, 22))
            self.assertFalse(first.skipped)
            page = first.new_paths[0]
            self.assertIn("schema_version: 2", page.read_text(encoding="utf-8"))
            revised = capture(resolved, self._request(
                operation="revise", expected_version=1,
                body="订单重试使用 request_id 和唯一键防止重复扣款。",
            ), date(2026, 7, 23))
            self.assertFalse(revised.skipped)
            text = page.read_text(encoding="utf-8")
            self.assertIn("version: 2", text)
            self.assertIn("### Version 1 — 2026-07-22", text)
            found = retrieve_context(resolved, "重复扣款", include_history=True)
            self.assertEqual("order-retry-idempotency", found["current_context"][0]["knowledge_id"])
            self.assertEqual(2, found["current_context"][0]["version"])
            self.assertEqual(1, found["historical_context"][0]["version"])
            historical = retrieve_context(resolved, "重复扣款", as_of=date(2026, 7, 22))
            self.assertEqual(1, historical["current_context"][0]["version"])

    def test_entity_create_is_idempotent_and_version_conflicts_are_explicit(self) -> None:
        with TemporaryDirectory() as temp:
            resolved = self._context(Path(temp))
            first = capture(resolved, self._request(), date(2026, 7, 22))
            replay = capture(resolved, self._request(), date(2026, 7, 22))
            self.assertTrue(replay.skipped)
            self.assertEqual(first.event_id, replay.event_id)
            with self.assertRaisesRegex(ValueError, "expected_version conflicts"):
                capture(resolved, self._request(operation="revise", expected_version=2), date(2026, 7, 23))
            with self.assertRaisesRegex(ValueError, "already exists"):
                capture(resolved, self._request(title="不同标题"), date(2026, 7, 23))

    def test_legacy_root_is_rejected_without_schema_migration(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "legacy"; (root / "01-projects").mkdir(parents=True)
            with self.assertRaisesRegex(TracebookError, "Existing knowledge root has no schema-v2 config"):
                repair_knowledge_root(root)

    def test_context_is_deterministic_and_bounded(self) -> None:
        with TemporaryDirectory() as temp:
            resolved = self._context(Path(temp))
            capture(resolved, self._request(), date(2026, 7, 22))
            first = retrieve_context(resolved, "order-retry-idempotency", max_results=1, max_chars=1000)
            second = retrieve_context(resolved, "order-retry-idempotency", max_results=1, max_chars=1000)
            self.assertEqual(json.dumps(first, ensure_ascii=False), json.dumps(second, ensure_ascii=False))
            self.assertGreaterEqual(first["current_context"][0]["score"], 100)


if __name__ == "__main__":
    unittest.main()
