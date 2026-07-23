"""End-to-end test: preflight → resolve → capture → context-read-path.

Covers the complete Tracebook workflow from an unregistered target through
durable knowledge write and read-back, verifying the v3.3.1 blocked/required_action
protocol at the preflight stage.
"""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

RUNNER = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "tracebook"
    / "skills"
    / "tracebook"
    / "scripts"
    / "tracebook_runner.py"
)


def _run(*args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(RUNNER), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def _capture(
    root: Path, repo: Path, request: dict, *, expect_success: bool = True
) -> dict:
    """Write request to a temp file and run the capture command."""
    req_file = repo / ".capture-request.json"
    req_file.write_text(json.dumps(request), encoding="utf-8")
    result = _run(
        "capture",
        "--root", str(root),
        "--cwd", str(repo),
        "--request", str(req_file),
    )
    if expect_success:
        assert result.returncode == 0, f"capture failed: {result.stderr}\nstdout: {result.stdout}"
    return json.loads(result.stdout)


class E2EFullWorkflowTest(unittest.TestCase):
    """Complete lifecycle: init → capture → read."""

    def test_full_workflow_preflight_resolve_capture_read(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            knowledge_root = base / "knowledge"
            repo = base / "business-repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            src = repo / "src"
            src.mkdir()
            (src / "orders.py").write_text(
                "def submit(order): pass  # idempotency key here\n",
                encoding="utf-8",
            )

            # ── Phase 1: preflight (unregistered) ──────────────────────
            pf1 = _run(
                "preflight",
                "--root", str(knowledge_root),
                "--cwd", str(repo),
            )
            self.assertEqual(0, pf1.returncode)
            p1 = json.loads(pf1.stdout)
            self.assertFalse(p1["registered"])
            self.assertTrue(p1["blocked"])
            self.assertEqual("resolve_required", p1["blocked_reason"])
            self.assertEqual("resolve", p1["required_action"]["name"])
            self.assertEqual("context-read-path", p1["required_action"]["then"])
            self.assertFalse(knowledge_root.exists())

            # ── Phase 2: execute required_action.argv ──────────────────
            action_argv = p1["required_action"]["argv"]
            res = subprocess.run(action_argv, capture_output=True, text=True)
            self.assertEqual(0, res.returncode, f"resolve failed: {res.stderr}")
            resolved = json.loads(res.stdout)
            self.assertIn("project", resolved)
            self.assertIn("knowledge_language", resolved)
            pid = resolved["project"]["project_id"]

            # ── Phase 3: preflight (registered) ────────────────────────
            pf2 = _run(
                "preflight",
                "--root", str(knowledge_root),
                "--cwd", str(repo),
            )
            self.assertEqual(0, pf2.returncode)
            p2 = json.loads(pf2.stdout)
            self.assertTrue(p2["registered"])
            self.assertFalse(p2["blocked"])
            self.assertNotIn("blocked_reason", p2)
            self.assertNotIn("required_action", p2)
            self.assertEqual(pid, p2["project"]["project_id"])

            # ── Phase 4: capture knowledge (entity path #1) ────────────
            c1 = _capture(knowledge_root, repo, {
                "scope": "project",
                "kind": "business-rule",
                "title": "Order idempotency",
                "body": "All order submissions must use an idempotency key to prevent duplicate charges.",
                "evidence": ["src/orders.py:L1-L1"],
                "status": "current",
                "operation": "create",
                "knowledge_id": "order-idempotency",
            })
            self.assertFalse(c1.get("skipped"))
            self.assertEqual("project", c1["health_scope"])
            self.assertIn("changed_paths", c1)
            self.assertTrue(len(c1["changed_paths"]) > 0)

            # ── Phase 5: capture knowledge (schema-v2 / entity path) ───
            c2 = _capture(knowledge_root, repo, {
                "scope": "project",
                "kind": "architecture",
                "title": "Retry strategy",
                "body": "Payment retries use exponential backoff with a max of 5 attempts.",
                "evidence": ["src/orders.py:L1-L1"],
                "status": "current",
                "operation": "create",
                "knowledge_id": "retry-strategy",
            })
            self.assertFalse(c2.get("skipped"))
            self.assertEqual("project", c2["health_scope"])

            # ── Phase 6: context-read-path ─────────────────────────────
            ctx1 = _run(
                "context-read-path",
                "--root", str(knowledge_root),
                "--cwd", str(repo),
                "--query", "idempotency key duplicate charges",
            )
            self.assertEqual(0, ctx1.returncode)
            ct1 = json.loads(ctx1.stdout)
            self.assertIn("current_context", ct1)
            ids1 = [item["knowledge_id"] for item in ct1["current_context"]]
            self.assertTrue(
                any("idempotency" in k.lower() or "order" in k.lower() for k in ids1),
                f"order-idempotency knowledge not found in {ids1}",
            )

            ctx2 = _run(
                "context-read-path",
                "--root", str(knowledge_root),
                "--cwd", str(repo),
                "--query", "retry backoff payment",
            )
            self.assertEqual(0, ctx2.returncode)
            ct2 = json.loads(ctx2.stdout)
            ids2 = [item["knowledge_id"] for item in ct2["current_context"]]
            self.assertIn("retry-strategy", ids2)

            # ── Phase 7: check ─────────────────────────────────────────
            changed_args: list[str] = []
            for p in c1["changed_paths"] + c2["changed_paths"]:
                changed_args.extend(["--changed", p])
            new_args: list[str] = []
            for p in c1.get("new_paths", []) + c2.get("new_paths", []):
                new_args.extend(["--new-path", p])
            chk = _run(
                "check",
                "--root", str(knowledge_root),
                "--cwd", str(repo),
                "--scope", "project",
                *changed_args,
                *new_args,
            )
            self.assertEqual(0, chk.returncode)
            ch = json.loads(chk.stdout)
            self.assertIn("check_type", ch)

    def test_capture_rejected_without_evidence_on_v2_path(self) -> None:
        """Schema-v2 current capture without evidence must be rejected."""
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            knowledge_root = base / "knowledge"
            repo = base / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()

            res = _run("resolve", "--root", str(knowledge_root), "--cwd", str(repo))
            self.assertEqual(0, res.returncode)

            result = _capture(
                knowledge_root, repo,
                {
                    "scope": "project",
                    "kind": "architecture",
                    "title": "Missing evidence",
                    "body": "This should be rejected.",
                    "evidence": [],
                    "status": "current",
                    "operation": "create",
                    "knowledge_id": "missing-evidence",
                },
                expect_success=False,
            )
            self.assertIn("error", result)
            self.assertIn("evidence", result["error"])

    def test_unknown_field_in_capture_is_rejected(self) -> None:
        """Typos in capture field names must be rejected, not silently ignored."""
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            knowledge_root = base / "knowledge"
            repo = base / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()

            res = _run("resolve", "--root", str(knowledge_root), "--cwd", str(repo))
            self.assertEqual(0, res.returncode)

            result = _capture(
                knowledge_root, repo,
                {
                    "scope": "project",
                    "kind": "architecture",
                    "title": "Typo test",
                    "body": "Testing field validation.",
                    "evidence": ["src/x.py:L1-L2"],
                    "status": "current",
                    "operation": "create",
                    "knowledge_id": "typo-test",
                    "evidnce": ["this is misspelled and should cause rejection"],
                },
                expect_success=False,
            )
            self.assertIn("error", result)
            self.assertIn("unknown fields", result["error"].lower())


if __name__ == "__main__":
    unittest.main()
