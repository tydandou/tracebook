"""Complete CLI workflows for building, writing, reading, and checking knowledge."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = (
    ROOT
    / "plugins"
    / "tracebook"
    / "skills"
    / "tracebook"
    / "scripts"
    / "tracebook_runner.py"
)


class CompleteKnowledgeWorkflowTest(unittest.TestCase):
    maxDiff = None

    def _run(
        self,
        base: Path,
        *arguments: str,
        request: dict[str, object] | None = None,
        expected_code: int = 0,
    ) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(RUNNER), *arguments],
            cwd=base,
            input=(
                json.dumps(request, ensure_ascii=False).encode("utf-8")
                if request is not None
                else None
            ),
            capture_output=True,
            check=False,
        )
        self.assertTrue(result.stdout, result.stderr.decode("utf-8", errors="replace"))
        payload = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(expected_code, result.returncode, payload)
        return payload

    def _capture(
        self,
        base: Path,
        root: Path,
        repo: Path,
        request: dict[str, object],
        *,
        expected_code: int = 0,
    ) -> dict[str, object]:
        return self._run(
            base,
            "capture",
            "--root",
            str(root),
            "--cwd",
            str(repo),
            "--today",
            "2026-08-17",
            "--request",
            "-",
            request=request,
            expected_code=expected_code,
        )

    @staticmethod
    def _request(
        knowledge_id: str,
        *,
        scope: str = "project",
        kind: str = "decision",
        title: str | None = None,
        body: str | None = None,
        evidence: list[str] | None = None,
        status: str = "current",
        operation: str = "create",
        expected_version: int | None = None,
        replacement_knowledge_id: str | None = None,
    ) -> dict[str, object]:
        request: dict[str, object] = {
            "operation": operation,
            "scope": scope,
            "kind": kind,
            "knowledge_id": knowledge_id,
            "title": title or knowledge_id.replace("-", " ").title(),
            "body": body or f"Verified durable conclusion for {knowledge_id}.",
            "evidence": evidence if evidence is not None else ["src/orders.py:L1-L2"],
            "status": status,
            "write_intent": "durable",
            "content_kind": "knowledge",
        }
        if expected_version is not None:
            request["expected_version"] = expected_version
        if replacement_knowledge_id is not None:
            request["replacement_knowledge_id"] = replacement_knowledge_id
        return request

    def _check_capture(
        self,
        base: Path,
        root: Path,
        repo: Path,
        scope: str,
        *captures: dict[str, object],
    ) -> dict[str, object]:
        arguments = [
            "check",
            "--root",
            str(root),
            "--cwd",
            str(repo),
            "--scope",
            scope,
            "--source-root",
            str(repo),
            "--today",
            "2026-08-17",
        ]
        for capture in captures:
            for path in capture["changed_paths"]:
                arguments.extend(("--changed", str(path)))
            for path in capture["new_paths"]:
                arguments.extend(("--new-path", str(path)))
        return self._run(base, *arguments)

    def test_build_add_read_and_review_across_all_scopes(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "plain-project"
            repo.mkdir()
            (repo / "src").mkdir()
            (repo / "docs").mkdir()
            (repo / "src" / "orders.py").write_text(
                "def submit(order):\n    return order.idempotency_key\n",
                encoding="utf-8",
            )
            (repo / "docs" / "domain.md").write_text(
                "Settlement means the final transfer of funds.\n",
                encoding="utf-8",
            )
            (repo / "docs" / "pattern.md").write_text(
                "An outbox publishes committed events.\n",
                encoding="utf-8",
            )

            preflight = self._run(
                base,
                "preflight",
                "--root",
                str(root),
                "--cwd",
                str(repo),
            )
            self.assertFalse(preflight["registered"])
            self.assertTrue(preflight["blocked"])
            self.assertEqual("argument", preflight["root_source"])
            self.assertFalse(preflight["root_existed"])
            self.assertFalse(preflight["root_initialized"])
            self.assertFalse(root.exists())

            resolved = self._run(
                base,
                "resolve",
                "--root",
                str(root),
                "--cwd",
                str(repo),
            )
            project_id = str(resolved["project"]["project_id"])
            project_dir = root / str(resolved["project"]["relative_path"])
            self.assertTrue(project_id.startswith("prj-"))
            self.assertTrue(resolved["root_created"])
            self.assertFalse(resolved["root_initialized_before"])
            self.assertTrue(resolved["root_initialized"])
            for required in (
                root / "AGENTS.md",
                root / "index.md",
                root / ".tracebook-state" / "schema.json",
                root / "registry.json",
                project_dir / "index.md",
                project_dir / "project-status.md",
                project_dir / "health-status.md",
            ):
                self.assertTrue(required.is_file(), required)

            project_request = self._request(
                "order-idempotency-policy",
                kind="business-rule",
                title="Order idempotency policy",
                body="Every order submission carries a stable idempotency key.",
            )
            project_capture = self._capture(base, root, repo, project_request)
            self.assertFalse(project_capture["skipped"])
            self.assertEqual("project", project_capture["health_scope"])
            self.assertEqual([], project_capture["warnings"])
            self.assertTrue(project_capture["changed_paths"])
            self.assertTrue(project_capture["new_paths"])

            repeated = self._capture(base, root, repo, project_request)
            self.assertTrue(repeated["skipped"])
            self.assertEqual(project_capture["event_id"], repeated["event_id"])
            self.assertEqual([], repeated["changed_paths"])
            self.assertEqual([], repeated["new_paths"])

            pending_capture = self._capture(
                base,
                root,
                repo,
                self._request(
                    "gateway-isolation-unverified",
                    kind="incident",
                    title="Gateway isolation remains unverified",
                    body="Network-side isolation evidence is still pending.",
                    evidence=[],
                    status="pending",
                ),
            )
            domain_capture = self._capture(
                base,
                root,
                repo,
                self._request(
                    "settlement-term",
                    scope="domain",
                    kind="terminology",
                    title="Settlement term",
                    body="Settlement is the final transfer of committed funds.",
                    evidence=["docs/domain.md:L1"],
                ),
            )
            pattern_capture = self._capture(
                base,
                root,
                repo,
                self._request(
                    "transactional-outbox-pattern",
                    scope="pattern",
                    kind="backend",
                    title="Transactional outbox pattern",
                    body="Publish events from an outbox written with the business transaction.",
                    evidence=["docs/pattern.md:L1"],
                ),
            )

            project_check = self._check_capture(
                base,
                root,
                repo,
                "project",
                project_capture,
                pending_capture,
            )
            domain_check = self._check_capture(
                base, root, repo, "domain", domain_capture
            )
            pattern_check = self._check_capture(
                base, root, repo, "pattern", pattern_capture
            )
            for scope, checked in (
                ("project", project_check),
                ("domain", domain_check),
                ("pattern", pattern_check),
            ):
                with self.subTest(scope=scope):
                    self.assertEqual("Light", checked["check_type"])
                    self.assertEqual("Light", checked["findings"]["check_type"])
                    self.assertEqual([], checked["findings"]["entity_issues"])
                    self.assertEqual([], checked["findings"]["missing_sources"])
                    self.assertIn("## Knowledge Health Check", checked["report"])
            self.assertTrue(project_check["findings"]["pending_confirmations"])

            project_read = self._run(
                base,
                "context-read-path",
                "--root",
                str(root),
                "--cwd",
                str(repo),
                "--query",
                "stable idempotency key",
            )
            self.assertEqual(
                ["order-idempotency-policy"],
                [item["knowledge_id"] for item in project_read["current_context"]],
            )
            self.assertNotIn(
                "gateway-isolation-unverified",
                {item["knowledge_id"] for item in project_read["current_context"]},
            )

            pending_read = self._run(
                base,
                "context-read-path",
                "--root",
                str(root),
                "--cwd",
                str(repo),
                "--status",
                "pending",
                "--query",
                "network isolation pending",
            )
            self.assertEqual(
                ["gateway-isolation-unverified"],
                [item["knowledge_id"] for item in pending_read["current_context"]],
            )

            for scope, query, expected in (
                ("domain", "final transfer committed funds", "settlement-term"),
                ("pattern", "outbox business transaction", "transactional-outbox-pattern"),
            ):
                scoped = self._run(
                    base,
                    "context-read-path",
                    "--root",
                    str(root),
                    "--cwd",
                    str(repo),
                    "--scope",
                    scope,
                    "--query",
                    query,
                )
                self.assertEqual(
                    [expected],
                    [item["knowledge_id"] for item in scoped["current_context"]],
                )

            revised_capture = self._capture(
                base,
                root,
                repo,
                self._request(
                    "order-idempotency-policy",
                    kind="business-rule",
                    title="Order idempotency policy",
                    body="Every order submission persists one stable idempotency key before charging.",
                    operation="revise",
                    expected_version=1,
                ),
            )
            history_read = self._run(
                base,
                "context-read-path",
                "--root",
                str(root),
                "--cwd",
                str(repo),
                "--include-history",
                "--query",
                "order-idempotency-policy",
            )
            self.assertEqual(2, history_read["current_context"][0]["version"])
            self.assertEqual(
                [1],
                [item["version"] for item in history_read["historical_context"]],
            )

            successor_capture = self._capture(
                base,
                root,
                repo,
                self._request(
                    "persisted-idempotency-key-policy",
                    kind="business-rule",
                    title="Persisted idempotency key policy",
                    body="Persist the idempotency key before the first charge attempt.",
                ),
            )
            superseded_capture = self._capture(
                base,
                root,
                repo,
                self._request(
                    "order-idempotency-policy",
                    kind="business-rule",
                    title="Order idempotency policy",
                    body="Replaced by the persisted idempotency key policy.",
                    status="superseded",
                    operation="change-status",
                    expected_version=2,
                    replacement_knowledge_id="persisted-idempotency-key-policy",
                ),
            )
            lifecycle_check = self._check_capture(
                base,
                root,
                repo,
                "project",
                revised_capture,
                successor_capture,
                superseded_capture,
            )
            self.assertEqual([], lifecycle_check["findings"]["entity_issues"])

            current_after_replacement = self._run(
                base,
                "context-read-path",
                "--root",
                str(root),
                "--cwd",
                str(repo),
                "--query",
                "persist idempotency key charge",
            )
            self.assertIn(
                "persisted-idempotency-key-policy",
                {
                    item["knowledge_id"]
                    for item in current_after_replacement["current_context"]
                },
            )
            superseded_read = self._run(
                base,
                "context-read-path",
                "--root",
                str(root),
                "--cwd",
                str(repo),
                "--status",
                "superseded",
                "--query",
                "order-idempotency-policy",
            )
            self.assertEqual(
                ["order-idempotency-policy"],
                [item["knowledge_id"] for item in superseded_read["current_context"]],
            )
            self.assertEqual(3, superseded_read["current_context"][0]["version"])

            for scope in ("project", "domain", "pattern"):
                audited = self._run(
                    base,
                    "audit",
                    "--root",
                    str(root),
                    "--cwd",
                    str(repo),
                    "--scope",
                    scope,
                    "--source-root",
                    str(repo),
                    "--today",
                    "2026-08-17",
                )
                self.assertIn("## Deep Knowledge Audit", audited["report"])
                self.assertEqual(
                    {
                        "fact_candidates",
                        "missing_source_paths",
                        "root_cause_candidates",
                        "status_log_drift",
                    },
                    set(audited["findings"]),
                )

            final_preflight = self._run(
                base,
                "preflight",
                "--root",
                str(root),
                "--cwd",
                str(repo),
            )
            self.assertTrue(final_preflight["registered"])
            self.assertEqual(project_id, final_preflight["project"]["project_id"])
            self.assertTrue(final_preflight["root_initialized"])
            self.assertTrue((project_dir / "index.md").is_file())
            self.assertTrue(
                (
                    root
                    / ".tracebook-state"
                    / "snapshots"
                    / project_id
                    / "current.json"
                ).is_file()
            )
            aggregate = (root / "00-global" / "health" / "health-status.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(f"| project | {project_id} |", aggregate)
            self.assertIn("| domain | domain |", aggregate)
            self.assertIn("| pattern | pattern |", aggregate)

    def test_rejected_writes_leave_authority_index_and_snapshot_unchanged(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "plain-project"
            (repo / "src").mkdir(parents=True)
            (repo / "src" / "orders.py").write_text("RULE = True\n", encoding="utf-8")

            resolved = self._run(
                base,
                "resolve",
                "--root",
                str(root),
                "--cwd",
                str(repo),
            )
            project_dir = root / str(resolved["project"]["relative_path"])
            request = self._request(
                "immutable-write-baseline",
                kind="business-rule",
                title="Immutable write baseline",
                body="A rejected write must not change the committed authority.",
            )
            self._capture(base, root, repo, request)

            authority = (
                project_dir
                / "knowledge"
                / "business-rule"
                / "immutable-write-baseline.md"
            )
            index = project_dir / "index.md"
            pointer = (
                root
                / ".tracebook-state"
                / "snapshots"
                / str(resolved["project"]["project_id"])
                / "current.json"
            )
            before = {
                authority: authority.read_bytes(),
                index: index.read_bytes(),
                pointer: pointer.read_bytes(),
            }

            no_evidence = self._capture(
                base,
                root,
                repo,
                self._request(
                    "missing-evidence-write",
                    evidence=[],
                ),
                expected_code=2,
            )
            self.assertIn("evidence", str(no_evidence["error"]))

            conflict = self._capture(
                base,
                root,
                repo,
                self._request(
                    "immutable-write-baseline",
                    kind="business-rule",
                    operation="revise",
                    expected_version=9,
                ),
                expected_code=2,
            )
            self.assertIn("expected_version conflicts", str(conflict["error"]))

            duplicate = self._capture(
                base,
                root,
                repo,
                self._request(
                    "immutable-write-baseline",
                    kind="business-rule",
                    body="A different create event must be rejected.",
                ),
                expected_code=2,
            )
            self.assertIn("already exists", str(duplicate["error"]))

            for path, content in before.items():
                self.assertEqual(content, path.read_bytes(), path)
            self.assertFalse(
                (
                    project_dir
                    / "knowledge"
                    / "decision"
                    / "missing-evidence-write.md"
                ).exists()
            )

            recalled = self._run(
                base,
                "context-read-path",
                "--root",
                str(root),
                "--cwd",
                str(repo),
                "--query",
                "immutable-write-baseline",
            )
            self.assertEqual(1, recalled["current_context"][0]["version"])
            transactions = self._run(base, "transactions", "--root", str(root))
            self.assertEqual([], transactions["transactions"])


if __name__ == "__main__":
    unittest.main()
