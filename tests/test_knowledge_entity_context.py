from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.capture import CaptureRequest
from plugins.tracebook.skills.tracebook.scripts.errors import TracebookError
from plugins.tracebook.skills.tracebook.scripts.knowledge_root import repair_knowledge_root
from plugins.tracebook.skills.tracebook.scripts.system_registry import bind_project, create_system
from plugins.tracebook.skills.tracebook.scripts.snapshots import project_knowledge_root
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
    capture,
    read_context,
    read_context_for_path,
    retrieve_context,
    resolve,
)


class KnowledgeEntityContextTest(unittest.TestCase):
    def _request(self, **overrides: object) -> CaptureRequest:
        values: dict[str, object] = {
            "operation": "create", "scope": "project", "kind": "business-rule",
            "knowledge_id": "order-retry-idempotency",
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

    def test_project_status_records_numeric_version(self) -> None:
        with TemporaryDirectory() as temp:
            resolved = self._context(Path(temp))
            capture(resolved, self._request(), date(2026, 7, 22))
            capture(resolved, self._request(
                operation="revise", expected_version=1,
                body="订单重试使用 request_id 和唯一键防止重复扣款。",
            ), date(2026, 7, 23))
            status = (resolved.root / resolved.record.relative_path / "project-status.md").read_text(encoding="utf-8")
            self.assertIn("`order-retry-idempotency` v1", status)
            self.assertIn("`order-retry-idempotency` v2", status)
            self.assertNotIn("v订单重试幂等机制", status)

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

    def _evidence_corpus(self, base: Path):
        repo = base / "svc"; repo.mkdir(); (repo / ".git").mkdir()
        resolved = resolve(base / "knowledge", repo)
        capture(resolved, self._request(
            kind="incident", knowledge_id="refund-nullpointer",
            title="退款回调空指针根因", body="回调 payload 缺字段导致 NPE。",
            evidence=("src/order/RefundController.java:L87", "test:RefundControllerTest"),
        ), date(2026, 7, 22))
        capture(resolved, self._request(
            kind="business-rule", knowledge_id="refund-idempotency",
            title="退款幂等规则", body="同一 refund_id 只生效一次，见 RefundController.java 入口。",
            evidence=("src/order/RefundService.java:L44",),
        ), date(2026, 7, 22))
        return resolved, repo

    def test_evidence_path_returns_only_formal_current_references(self) -> None:
        with TemporaryDirectory() as temp:
            resolved, repo = self._evidence_corpus(Path(temp))
            found = read_context_for_path(
                resolved.root, repo, "",
                evidence_paths=("src/order/RefundController.java",),
            )
            ids = [item["knowledge_id"] for item in found["current_context"]]
            self.assertEqual(["refund-nullpointer"], ids)
            self.assertTrue(found["current_context"][0]["evidence_match"])

    def test_evidence_path_accepts_project_absolute_path(self) -> None:
        with TemporaryDirectory() as temp:
            resolved, repo = self._evidence_corpus(Path(temp))
            absolute = str(repo / "src" / "order" / "RefundController.java")
            found = read_context_for_path(resolved.root, repo, "", evidence_paths=(absolute,))
            self.assertEqual(
                ["refund-nullpointer"],
                [item["knowledge_id"] for item in found["current_context"]],
            )

    def test_context_read_accepts_absolute_path_from_registered_location(self) -> None:
        with TemporaryDirectory() as temp:
            resolved, repo = self._evidence_corpus(Path(temp))
            absolute = str(repo / "src" / "order" / "RefundController.java")
            found = read_context(
                resolved.root,
                (resolved.record.project_id,),
                "",
                evidence_paths=(absolute,),
            )
            self.assertEqual(
                ["refund-nullpointer"],
                [item["knowledge_id"] for item in found["current_context"]],
            )

    def test_evidence_path_outside_project_warns_without_match(self) -> None:
        with TemporaryDirectory() as temp:
            resolved, repo = self._evidence_corpus(Path(temp))
            outside = str(Path(temp) / "elsewhere" / "Other.java")
            found = read_context_for_path(resolved.root, repo, "", evidence_paths=(outside,))
            self.assertEqual([], found["current_context"])
            self.assertTrue(any("outside the project" in w for w in found["warnings"]))

    def test_evidence_path_rejects_non_project_scope(self) -> None:
        with TemporaryDirectory() as temp:
            resolved, repo = self._evidence_corpus(Path(temp))
            with self.assertRaisesRegex(ValueError, "evidence-path supports only project scope"):
                read_context_for_path(
                    resolved.root, repo, "", scope="all",
                    evidence_paths=("src/order/RefundController.java",),
                )

    def test_missing_query_and_evidence_is_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            resolved, repo = self._evidence_corpus(Path(temp))
            with self.assertRaisesRegex(ValueError, "query or evidence-path is required"):
                read_context_for_path(resolved.root, repo, "")

    def test_blank_evidence_path_does_not_satisfy_required_input(self) -> None:
        with TemporaryDirectory() as temp:
            resolved, repo = self._evidence_corpus(Path(temp))
            with self.assertRaisesRegex(ValueError, "query or evidence-path is required"):
                read_context_for_path(
                    resolved.root,
                    repo,
                    "",
                    evidence_paths=("   ",),
                )

    def test_evidence_path_rejects_multiple_projects(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            first_base = base / "first"
            first_base.mkdir()
            first, _ = self._evidence_corpus(first_base)
            second_repo = base / "second" / "repo"
            second_repo.mkdir(parents=True)
            (second_repo / ".git").mkdir()
            second = resolve(first.root, second_repo)
            with self.assertRaisesRegex(ValueError, "exactly one project_id"):
                read_context(
                    first.root,
                    (first.record.project_id, second.record.project_id),
                    "",
                    evidence_paths=("src/order/RefundController.java",),
                )

    def test_chinese_task_sentence_recalls_relevant_entities(self) -> None:
        with TemporaryDirectory() as temp:
            resolved = self._context(Path(temp))
            capture(resolved, self._request(
                kind="incident", knowledge_id="inventory-oversell-incident",
                title="库存超卖事故", body="并发下库存扣减存在竞态，导致超卖。",
                evidence=("src/inv/stock.py:L60",),
            ), date(2026, 7, 22))
            capture(resolved, self._request(
                kind="business-rule", knowledge_id="order-cancellation-rules",
                title="订单取消规则", body="买家可在创建后 30 分钟内取消，全额退款。",
                evidence=("src/order/cancel.py:L44",),
            ), date(2026, 7, 22))
            found = retrieve_context(resolved, "排查库存超卖问题，确认库存扣减与订单取消规则")
            ids = {item["knowledge_id"] for item in found["current_context"][:3]}
            self.assertIn("inventory-oversell-incident", ids)
            self.assertIn("order-cancellation-rules", ids)

    def test_stopword_only_query_returns_no_results(self) -> None:
        with TemporaryDirectory() as temp:
            resolved = self._context(Path(temp))
            capture(resolved, self._request(), date(2026, 7, 22))
            self.assertEqual([], retrieve_context(resolved, "the a is of to")["current_context"])
            self.assertTrue(retrieve_context(resolved, "order-retry-idempotency")["current_context"])

    def test_crlf_authority_page_stays_retrievable(self) -> None:
        with TemporaryDirectory() as temp:
            resolved = self._context(Path(temp))
            capture(resolved, self._request(), date(2026, 7, 22))
            snapshot_root, mode = project_knowledge_root(resolved.root, resolved.record, operation="test")
            self.assertEqual("snapshot", mode)
            page = snapshot_root / "business-rule" / "order-retry-idempotency.md"
            page.write_bytes(page.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
            found = retrieve_context(resolved, "重复扣款")
            self.assertEqual("order-retry-idempotency", found["current_context"][0]["knowledge_id"])
            self.assertEqual([], found["warnings"])

    def test_context_reads_only_explicitly_selected_other_projects(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            first_repo = base / "payment"; first_repo.mkdir()
            second_repo = base / "order"; second_repo.mkdir()
            root = base / "knowledge"
            first = resolve(root, first_repo)
            second = resolve(root, second_repo)
            capture(
                second,
                self._request(
                    kind="architecture",
                    knowledge_id="order-event-contract",
                    title="Order event contract",
                    body="Order service publishes OrderPaid events.",
                ),
                date(2026, 7, 22),
            )

            local = retrieve_context(first, "OrderPaid", scope="project")
            expanded = retrieve_context(
                first,
                "OrderPaid",
                project_ids=(second.record.project_id,),
                scope="project",
            )
            reference = retrieve_context(
                first,
                "OrderPaid",
                project_ids=(second.record.project_id,),
                profile="reference",
                scope="project",
            )

            self.assertEqual([], local["current_context"])
            self.assertEqual(second.record.project_id, expanded["current_context"][0]["source_project"]["project_id"])
            self.assertEqual("order-event-contract", reference["current_context"][0]["knowledge_id"])

    def test_context_can_select_registered_system_members(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            first_repo = base / "payment"; first_repo.mkdir()
            second_repo = base / "order"; second_repo.mkdir()
            root = base / "knowledge"
            first = resolve(root, first_repo)
            second = resolve(root, second_repo)
            capture(
                second,
                self._request(
                    kind="architecture",
                    knowledge_id="order-event-contract",
                    title="Order event contract",
                    body="Order service publishes OrderPaid events.",
                ),
                date(2026, 7, 22),
            )
            system = create_system(root, "Commerce")
            system = bind_project(root, system.system_id, first.record.project_id)
            system = bind_project(root, system.system_id, second.record.project_id)

            result = retrieve_context(
                first,
                "OrderPaid",
                system_ids=(system.system_id,),
                scope="project",
            )

            self.assertEqual(second.record.project_id, result["current_context"][0]["source_project"]["project_id"])


if __name__ == "__main__":
    unittest.main()
