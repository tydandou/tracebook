"""End-to-end lifecycle over the real CLI: create -> capture -> query -> review.

Drives tracebook_runner.main() through a subprocess so the whole command chain
(argument parsing, locking, snapshots, retrieval, health) is exercised as an
agent would. stdout is decoded as UTF-8 explicitly to keep CJK titles readable
regardless of the console's locale codepage.
"""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts import snapshots


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "plugins" / "tracebook" / "skills" / "tracebook" / "scripts" / "tracebook_runner.py"


class EndToEndWorkflowTest(unittest.TestCase):
    def _run(self, base: Path, *arguments: str, expect_ok: bool = True, stdin: bytes | None = None) -> dict:
        result = subprocess.run(
            [sys.executable, str(RUNNER), *arguments],
            cwd=base,
            capture_output=True,
            check=False,
            input=stdin,
        )
        payload = json.loads(result.stdout.decode("utf-8"))
        if expect_ok:
            self.assertEqual(0, result.returncode, payload)
        else:
            self.assertEqual(2, result.returncode, payload)
        return payload

    def _write_request(self, base: Path, name: str, **fields: object) -> Path:
        request = base / f"{name}.json"
        request.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")
        return request

    def test_response_bytes_are_utf8_regardless_of_console_codepage(self) -> None:
        """A CJK title must survive as UTF-8 bytes on a non-UTF-8 locale console.

        `print` would encode with the locale codepage (gbk on a Chinese Windows
        console), so the raw stdout bytes are decoded here without `text=True`.
        """
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "service"
            (repo / ".git").mkdir(parents=True)
            self._run(base, "initialize", "--root", str(root))
            self._run(base, "resolve", "--root", str(root), "--cwd", str(repo))
            title = "退款回调空指针根因"
            self._run(base, "capture", "--root", str(root), "--cwd", str(repo),
                      "--today", "2026-07-20", "--request", "-",
                      stdin=json.dumps({
                          "operation": "create", "scope": "project", "kind": "incident",
                          "knowledge_id": "refund-nullpointer", "title": title,
                          "body": "回调 payload 缺少字段导致空指针。",
                          "evidence": ["src/order/RefundController.java:L1"],
                          "status": "current", "write_intent": "durable",
                          "content_kind": "knowledge",
                      }, ensure_ascii=False).encode("utf-8"))
            result = subprocess.run(
                [sys.executable, str(RUNNER), "context-read-path", "--root", str(root),
                 "--cwd", str(repo), "--query", title],
                cwd=base, capture_output=True, check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout.decode("utf-8"))
            self.assertEqual([title], [item["title"] for item in payload["current_context"]])
            self.assertNotIn(b"\r\n", result.stdout)

    def test_full_knowledge_lifecycle(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "service"
            (repo / ".git").mkdir(parents=True)
            # A real source file so evidence resolves and review checks pass.
            controller = repo / "src" / "order" / "RefundController.java"
            controller.parent.mkdir(parents=True)
            controller.write_text("class RefundController {}\n", encoding="utf-8")

            # 1. Create the knowledge root.
            initialized = self._run(base, "initialize", "--root", str(root))
            self.assertEqual(str(root), initialized["root"])
            self.assertTrue(initialized["created_paths"])

            # 2. Activate the project.
            resolved = self._run(base, "resolve", "--root", str(root), "--cwd", str(repo))
            project_id = resolved["project"]["project_id"]
            self.assertTrue(project_id.startswith("prj-"))

            # 3. Capture two knowledge entities (one CJK, one referencing the file).
            self._run(base, "capture", "--root", str(root), "--cwd", str(repo),
                      "--today", "2026-07-20", "--request", str(self._write_request(
                          base, "refund",
                          operation="create", scope="project", kind="incident",
                          knowledge_id="refund-nullpointer",
                          title="退款回调空指针根因",
                          body="回调 payload 缺少字段导致空指针，需要判空。",
                          evidence=["src/order/RefundController.java:L1", "test:RefundControllerTest"],
                          status="current", write_intent="durable", content_kind="knowledge",
                      )))
            self._run(base, "capture", "--root", str(root), "--cwd", str(repo),
                      "--today", "2026-07-20", "--request", str(self._write_request(
                          base, "cancel",
                          operation="create", scope="project", kind="business-rule",
                          knowledge_id="order-cancellation-rules",
                          title="订单取消规则",
                          body="买家可在创建后 30 分钟内取消，全额退款。",
                          evidence=["src/order/CancelService.java:L10"],
                          status="current", write_intent="durable", content_kind="knowledge",
                      )))

            # 4. Query by CJK task sentence (B1): both entities recalled.
            found = self._run(base, "context-read-path", "--root", str(root),
                              "--cwd", str(repo), "--query", "排查退款空指针与订单取消规则")
            ids = {item["knowledge_id"] for item in found["current_context"]}
            self.assertIn("refund-nullpointer", ids)
            self.assertIn("order-cancellation-rules", ids)

            # 5. Exact knowledge_id query scores highest.
            exact = self._run(base, "context-read-path", "--root", str(root),
                              "--cwd", str(repo), "--query", "refund-nullpointer")
            self.assertEqual("refund-nullpointer", exact["current_context"][0]["knowledge_id"])

            # 6. Revise, then confirm the new version and numeric status log (A1).
            self._run(base, "capture", "--root", str(root), "--cwd", str(repo),
                      "--today", "2026-07-21", "--request", str(self._write_request(
                          base, "refund2",
                          operation="revise", scope="project", kind="incident",
                          knowledge_id="refund-nullpointer", expected_version=1,
                          title="退款回调空指针根因",
                          body="回调 payload 缺字段导致空指针，已在入口统一判空。",
                          evidence=["src/order/RefundController.java:L1"],
                          status="current", write_intent="durable", content_kind="knowledge",
                      )))
            revised = self._run(base, "context-read-path", "--root", str(root),
                                "--cwd", str(repo), "--query", "refund-nullpointer")
            self.assertEqual(2, revised["current_context"][0]["version"])
            status_page = (root / "01-projects").glob("*/project-status.md")
            status_text = next(status_page).read_text(encoding="utf-8")
            self.assertIn("`refund-nullpointer` v2", status_text)

            # 7. Evidence reverse query (E1): only the formal Current reference.
            by_evidence = self._run(base, "context-read-path", "--root", str(root),
                                    "--cwd", str(repo),
                                    "--evidence-path", "src/order/RefundController.java")
            self.assertEqual(
                ["refund-nullpointer"],
                [item["knowledge_id"] for item in by_evidence["current_context"]],
            )
            self.assertTrue(by_evidence["current_context"][0]["evidence_match"])

            # 8. Stopword-only query (A3) returns nothing.
            empty = self._run(base, "context-read-path", "--root", str(root),
                              "--cwd", str(repo), "--query", "the a is of to")
            self.assertEqual([], empty["current_context"])

            # 9. Health check with source-root: the cancel entity's evidence file
            #    is missing, so it becomes a strong review candidate (F1).
            checked = self._run(base, "check", "--root", str(root), "--cwd", str(repo),
                                "--today", "2026-07-22", "--source-root", str(repo),
                                "--review-after-days", "1")
            report = checked["report"]
            self.assertIn("### Review Candidates", report)
            self.assertIn("source_missing", report)
            self.assertIn("order-cancellation-rules", report)
            # The file-backed entity's evidence exists, so it is not flagged missing.
            self.assertNotIn("refund-nullpointer): source_missing", report)

            # 10. Invalid review window is rejected (F1 guard).
            self._run(base, "check", "--root", str(root), "--cwd", str(repo),
                      "--today", "2026-07-22", "--source-root", str(repo),
                      "--review-after-days", "0", expect_ok=False)

            # 11. Deep audit runs and returns a structured report.
            audited = self._run(base, "audit", "--root", str(root), "--cwd", str(repo),
                                "--today", "2026-07-22", "--source-root", str(repo))
            self.assertIn("Deep Knowledge Audit", audited["report"])

            # 12. Snapshot pruning bound holds after several captures (C1).
            versions = root / ".tracebook-state" / "snapshots" / project_id / "versions"
            self.assertLessEqual(
                len([d for d in versions.iterdir() if d.is_dir()]),
                snapshots.SNAPSHOT_RETENTION,
            )

    def test_per_item_gate_keeps_verified_facts_when_one_item_is_pending(self) -> None:
        # One incident yields three verified facts plus one unverified dependency
        # risk. The verified facts must all persist; the risk lands as pending
        # with no evidence — never all-or-nothing.
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "gateway"
            (repo / ".git").mkdir(parents=True)
            self._run(base, "initialize", "--root", str(root))
            self._run(base, "resolve", "--root", str(root), "--cwd", str(repo))

            current_items = [
                ("ops-no-token-rejected", "OPS 无 Token 调用被共享平台鉴权拦截",
                 "现网日志与网关源码确认：OPS 内部调用无 Token 被共享平台鉴权拒绝。"),
                ("shared-platform-excluded", "根因：共享平台被排除出内网兼容分支",
                 "Git 差异与源码确认：共享平台路径未进入内部兼容分支。"),
                ("restore-internal-compat", "最小修复：恢复内部兼容条件（待 SIT 验收）",
                 "代码已修改并通过静态检查；SIT 回归待执行。"),
            ]
            for index, (kid, title, body) in enumerate(current_items):
                self._run(base, "capture", "--root", str(root), "--cwd", str(repo),
                          "--today", "2026-07-20", "--request", str(self._write_request(
                              base, f"cur-{index}",
                              operation="create", scope="project", kind="incident",
                              knowledge_id=kid, title=title, body=body,
                              evidence=["src/gateway/AuthFilter.java:L1"],
                              status="current", write_intent="durable", content_kind="knowledge",
                          )))
            # The unverified dependency: no network-side evidence yet -> pending, empty evidence.
            self._run(base, "capture", "--root", str(root), "--cwd", str(repo),
                      "--today", "2026-07-20", "--request", str(self._write_request(
                          base, "pending-risk",
                          operation="create", scope="project", kind="incident",
                          knowledge_id="internal-host-spoofing-risk",
                          title="内部 Host 是否可被外部伪造（待验证）",
                          body="内部网关入口的网络隔离有效性尚无网络侧证据，待验证。",
                          evidence=[],
                          status="pending", write_intent="durable", content_kind="knowledge",
                      )))

            current = self._run(base, "context-read-path", "--root", str(root),
                                "--cwd", str(repo), "--query", "共享平台 OPS Token 兼容 修复")
            current_ids = {item["knowledge_id"] for item in current["current_context"]}
            for kid, _, _ in current_items:
                self.assertIn(kid, current_ids)
            self.assertNotIn("internal-host-spoofing-risk", current_ids)

            # The pending risk is retained and retrievable when explicitly requested.
            pending = self._run(base, "context-read-path", "--root", str(root),
                                "--cwd", str(repo), "--status", "pending",
                                "--query", "内部 Host 伪造 网络隔离")
            self.assertIn(
                "internal-host-spoofing-risk",
                {item["knowledge_id"] for item in pending["current_context"]},
            )


if __name__ == "__main__":
    unittest.main()
