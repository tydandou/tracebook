import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts import transaction


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "plugins" / "tracebook" / "skills" / "tracebook"
RUNNER = SKILL_ROOT / "scripts" / "tracebook_runner.py"


class RunnerIntegrationTest(unittest.TestCase):
    def _run_runner(self, base: Path, *arguments: str) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(RUNNER), *arguments],
            cwd=base,
            capture_output=True,
            check=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_installed_runner_resolves_project_from_an_arbitrary_working_directory(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "resolve",
                    "--root",
                    str(root),
                    "--cwd",
                    str(repo),
                ],
                cwd=base,
                capture_output=True,
                check=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["root"], str(root))
            self.assertEqual("en", payload["knowledge_language"])
            self.assertEqual(len(payload["read_paths"]), 5)
            self.assertFalse((repo / "AGENTS.md").exists())

    def test_runner_updates_locations_and_binds_a_remote_by_project_id(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            first = base / "first"
            first.mkdir()
            resolved = self._run_runner(
                base, "resolve", "--root", str(root), "--cwd", str(first)
            )
            project_id = str(resolved["project"]["project_id"])
            self.assertTrue(str(resolved["project"]["slug"]).startswith("first--"))
            moved = base / "moved"
            updated = self._run_runner(
                base,
                "project-update",
                "--root",
                str(root),
                "--project-id",
                project_id,
                "--location",
                str(moved),
            )
            self.assertEqual([str(moved.resolve())], updated["project"]["locations"])
            bound = self._run_runner(
                base,
                "project-bind-remote",
                "--root",
                str(root),
                "--project-id",
                project_id,
                "--remote",
                "git@github.com:acme/widgets.git",
            )
            self.assertEqual(["github.com/acme/widgets"], bound["project"]["remotes"])

            clone = base / "clone"
            clone.mkdir()
            subprocess.run(["git", "-C", str(clone), "init", "--quiet"], check=True)
            subprocess.run(
                ["git", "-C", str(clone), "remote", "add", "origin", "https://github.com/acme/widgets.git"],
                check=True,
            )
            clone_resolved = self._run_runner(
                base, "resolve", "--root", str(root), "--cwd", str(clone)
            )
            self.assertEqual(project_id, clone_resolved["project"]["project_id"])

    def test_runner_preflights_and_selects_explicit_system_members(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            target = base / "new-service"
            preflight = self._run_runner(
                base, "preflight", "--root", str(root), "--cwd", str(target)
            )
            self.assertFalse(preflight["registered"])
            self.assertFalse(root.exists())

            first_path = base / "payment"; first_path.mkdir()
            second_path = base / "order"; second_path.mkdir()
            first = self._run_runner(base, "resolve", "--root", str(root), "--cwd", str(first_path))
            second = self._run_runner(base, "resolve", "--root", str(root), "--cwd", str(second_path))
            search = self._run_runner(base, "project-search", "--root", str(root), "--query", "order")
            self.assertEqual(second["project"]["project_id"], search["projects"][0]["project_id"])

            system = self._run_runner(base, "system-create", "--root", str(root), "--name", "Commerce")["system"]
            system_id = str(system["system_id"])
            self._run_runner(base, "system-bind-project", "--root", str(root), "--system-id", system_id, "--project-id", str(first["project"]["project_id"]))
            self._run_runner(base, "system-bind-project", "--root", str(root), "--system-id", system_id, "--project-id", str(second["project"]["project_id"]))
            self._run_runner(base, "system-relate", "--root", str(root), "--system-id", system_id, "--source-project-id", str(first["project"]["project_id"]), "--target-project-id", str(second["project"]["project_id"]), "--kind", "event")
            context = self._run_runner(base, "context", "--root", str(root), "--cwd", str(first_path), "--system-id", system_id, "--query", "OrderPaid")
            self.assertEqual({str(first["project"]["project_id"]), str(second["project"]["project_id"])}, {item["project_id"] for item in context["queried_projects"]})

    def test_runner_reads_reference_context_for_an_uncreated_target_without_registration(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            source_path = base / "source"; source_path.mkdir()
            target_path = base / "new-service"
            source = self._run_runner(base, "resolve", "--root", str(root), "--cwd", str(source_path))
            project_id = str(source["project"]["project_id"])
            before = (root / "registry.json").read_bytes()

            preflight = self._run_runner(base, "preflight", "--root", str(root), "--cwd", str(target_path))
            reference = self._run_runner(
                base,
                "context-read",
                "--root",
                str(root),
                "--project-id",
                project_id,
                "--profile",
                "reference",
                "--query",
                "architecture",
            )

            self.assertFalse(preflight["registered"])
            self.assertEqual([project_id], [item["project_id"] for item in reference["queried_projects"]])
            self.assertFalse(target_path.exists())
            self.assertEqual(before, (root / "registry.json").read_bytes())

    def test_complete_knowledge_flow_for_related_empty_and_iterating_projects(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            uncreated = base / "image-gen-agent"
            self.assertFalse(
                self._run_runner(base, "preflight", "--root", str(root), "--cwd", str(uncreated))["registered"]
            )
            self.assertFalse(root.exists())

            payment_path = base / "payment"; payment_path.mkdir()
            order_path = base / "order"; order_path.mkdir()
            payment = self._run_runner(base, "resolve", "--root", str(root), "--cwd", str(payment_path))
            order = self._run_runner(base, "resolve", "--root", str(root), "--cwd", str(order_path))

            def capture_request(name: str, payload: dict[str, object]) -> dict[str, object]:
                request = base / f"{name}.json"
                request.write_text(json.dumps(payload), encoding="utf-8")
                return self._run_runner(base, "capture", "--root", str(root), "--cwd", str(order_path), "--request", str(request), "--today", "2026-07-23")

            capture_request("order-architecture", {
                "operation": "create", "knowledge_id": "order-paid-contract", "scope": "project", "kind": "architecture",
                "title": "OrderPaid contract", "body": "Order service publishes OrderPaid with order_id.",
                "evidence": ["src/events.py:L1-L10"], "status": "current", "write_intent": "durable", "content_kind": "knowledge",
            })
            capture_request("order-source-map", {
                "operation": "create", "knowledge_id": "order-event-source-map", "scope": "project", "kind": "source-map",
                "title": "Order event source map", "body": "SOURCE_MAP_ONLY_TOKEN is implementation navigation.",
                "evidence": ["src/events.py:L1-L10"], "status": "current", "write_intent": "durable", "content_kind": "knowledge",
            })

            system = self._run_runner(base, "system-create", "--root", str(root), "--name", "Commerce")["system"]
            system_id = str(system["system_id"])
            payment_id = str(payment["project"]["project_id"])
            order_id = str(order["project"]["project_id"])
            for project_id in (payment_id, order_id):
                self._run_runner(base, "system-bind-project", "--root", str(root), "--system-id", system_id, "--project-id", project_id)
            self._run_runner(base, "system-relate", "--root", str(root), "--system-id", system_id, "--source-project-id", payment_id, "--target-project-id", order_id, "--kind", "event")

            related = self._run_runner(base, "context", "--root", str(root), "--cwd", str(payment_path), "--system-id", system_id, "--query", "OrderPaid")
            self.assertEqual(order_id, related["current_context"][0]["source_project"]["project_id"])
            reference = self._run_runner(base, "context-read", "--root", str(root), "--project-id", order_id, "--profile", "reference", "--query", "OrderPaid")
            self.assertEqual("order-paid-contract", reference["current_context"][0]["knowledge_id"])
            excluded = self._run_runner(base, "context-read", "--root", str(root), "--project-id", order_id, "--profile", "reference", "--query", "SOURCE_MAP_ONLY_TOKEN")
            self.assertEqual([], excluded["current_context"])

            blank_path = base / "blank"; blank_path.mkdir()
            blank = self._run_runner(base, "resolve", "--root", str(root), "--cwd", str(blank_path))
            empty = self._run_runner(base, "context", "--root", str(root), "--cwd", str(blank_path), "--query", "anything")
            self.assertEqual(blank["project"]["project_id"], empty["project"]["project_id"])
            self.assertEqual([], empty["current_context"])

            request = base / "payment-iteration.json"
            request.write_text(json.dumps({
                "operation": "create", "knowledge_id": "payment-retry-policy", "scope": "project", "kind": "decision",
                "title": "Payment retry policy", "body": "Retry once.", "evidence": ["src/retry.py:L1-L10"],
                "status": "current", "write_intent": "durable", "content_kind": "knowledge",
            }), encoding="utf-8")
            self._run_runner(base, "capture", "--root", str(root), "--cwd", str(payment_path), "--request", str(request), "--today", "2026-07-23")
            request.write_text(json.dumps({
                "operation": "revise", "expected_version": 1, "knowledge_id": "payment-retry-policy", "scope": "project", "kind": "decision",
                "title": "Payment retry policy", "body": "Retry once after a transient failure.", "evidence": ["src/retry.py:L1-L12"],
                "status": "current", "write_intent": "durable", "content_kind": "knowledge",
            }), encoding="utf-8")
            self._run_runner(base, "capture", "--root", str(root), "--cwd", str(payment_path), "--request", str(request), "--today", "2026-07-23")
            iteration = self._run_runner(base, "context", "--root", str(root), "--cwd", str(payment_path), "--query", "transient failure", "--include-history")
            self.assertEqual(2, iteration["current_context"][0]["version"])
            self.assertEqual(1, iteration["historical_context"][0]["version"])

    def test_runner_accepts_utf8_bom_capture_requests_and_reports_legacy_roots(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            resolved = self._run_runner(base, "resolve", "--root", str(root), "--cwd", str(repo))
            request = base / "capture.json"
            payload = {
                "operation": "create",
                "knowledge_id": "bom-compatible-request",
                "scope": "project",
                "kind": "business-rule",
                "title": "BOM-compatible request",
                "body": "A Windows-authored request remains readable.",
                "evidence": ["src/example.py:L1-L1"],
                "status": "current",
            }
            request.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))
            captured = self._run_runner(
                base, "capture", "--root", str(root), "--cwd", str(repo),
                "--request", str(request), "--today", "2026-07-22",
            )
            self.assertTrue(captured["event_id"])
            self.assertEqual(
                "Tracebook: created `bom-compatible-request` "
                f"(project `{resolved['project']['name']}`, kind `business-rule`).",
                captured["user_summary"],
            )

            replay = self._run_runner(
                base, "capture", "--root", str(root), "--cwd", str(repo),
                "--request", str(request), "--today", "2026-07-22",
            )
            self.assertTrue(replay["skipped"])
            self.assertNotIn("user_summary", replay)

            payload["operation"] = "revise"
            payload["expected_version"] = 1
            payload["body"] = "A revised Windows-authored request remains readable."
            request.write_text(json.dumps(payload), encoding="utf-8")
            revised = self._run_runner(
                base, "capture", "--root", str(root), "--cwd", str(repo),
                "--request", str(request), "--today", "2026-07-22",
            )
            self.assertEqual(
                "Tracebook: revised `bom-compatible-request` "
                f"(project `{resolved['project']['name']}`, kind `business-rule`).",
                revised["user_summary"],
            )

            domain_payload = {
                "operation": "create",
                "knowledge_id": "refund-terminology",
                "scope": "domain",
                "kind": "domain",
                "title": "Refund terminology",
                "body": "A refund remains incomplete until settlement succeeds.",
                "evidence": ["src/refund.py:L1-L1"],
                "status": "current",
            }
            request.write_text(json.dumps(domain_payload), encoding="utf-8")
            domain = self._run_runner(
                base, "capture", "--root", str(root), "--cwd", str(repo),
                "--request", str(request), "--today", "2026-07-22",
            )
            self.assertEqual(
                "Tracebook: created `refund-terminology` (domain scope, kind `domain`).",
                domain["user_summary"],
            )

            legacy = base / "legacy"
            (legacy / "01-projects").mkdir(parents=True)
            result = subprocess.run(
                [sys.executable, str(RUNNER), "resolve", "--root", str(legacy), "--cwd", str(repo)],
                cwd=base, capture_output=True, check=False, text=True,
            )
            self.assertEqual(2, result.returncode)
            self.assertEqual("", result.stderr)
            error = json.loads(result.stdout)["error"]
            self.assertEqual("UNSUPPORTED_SCHEMA", error["code"])
            self.assertEqual("initialize", error["operation"])

    def test_runner_rejects_null_operation_before_legacy_capture_can_write(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            resolved = self._run_runner(base, "resolve", "--root", str(root), "--cwd", str(repo))
            request = base / "capture.json"
            request.write_text(
                json.dumps(
                    {
                        "operation": None,
                        "knowledge_id": "must-not-fall-back",
                        "scope": "project",
                        "kind": "business-rule",
                        "category": "business-rules",
                        "title": "Must not use the legacy capture path",
                        "body": "A null operation must be rejected before any write.",
                        "evidence": ["src/example.py:L1-L1"],
                        "status": "Current",
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "capture",
                    "--root",
                    str(root),
                    "--cwd",
                    str(repo),
                    "--request",
                    str(request),
                    "--today",
                    "2026-07-22",
                ],
                cwd=base,
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(2, result.returncode)
            self.assertEqual("", result.stderr)
            self.assertEqual(
                "INVALID_REQUEST: schema-v2 capture requires a non-empty operation",
                json.loads(result.stdout)["error"],
            )
            project = root / resolved["project"]["relative_path"]
            self.assertFalse((project / "business-rules.md").exists())

    def test_installed_runner_executes_an_explicit_deep_audit(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)

            resolved = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "resolve",
                    "--root",
                    str(root),
                    "--cwd",
                    str(repo),
                ],
                cwd=base,
                capture_output=True,
                check=True,
                text=True,
            )
            resolved_payload = json.loads(resolved.stdout)
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "audit",
                    "--root",
                    str(root),
                    "--cwd",
                    str(repo),
                    "--source-root",
                    str(repo),
                    "--today",
                    "2026-07-13",
                ],
                cwd=base,
                capture_output=True,
                check=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            self.assertIn("Deep Knowledge Audit", payload["report"])
            health = (
                root
                / "01-projects"
                / resolved_payload["project"]["slug"]
                / "health-status.md"
            )
            self.assertIn("Last Deep Check: 2026-07-13", health.read_text(encoding="utf-8"))
            aggregate = (
                root / "00-global" / "health" / "health-status.md"
            ).read_text(encoding="utf-8")
            self.assertIn(
                f"| project | {resolved_payload['project']['identity']} |",
                aggregate,
            )
            self.assertIn("2026-07-13", aggregate)

    def test_transaction_inspection_is_read_only_and_recovery_is_explicit(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            root.mkdir()
            target = root / "entry.md"
            target.write_text("old\n", encoding="utf-8")

            with patch.object(
                transaction,
                "_replace_target",
                side_effect=OSError("simulated crash"),
            ):
                with self.assertRaisesRegex(OSError, "simulated crash"):
                    transaction.commit_updates(
                        root,
                        "project-demo",
                        "capture",
                        {target: "new\n"},
                        transaction_id="runner-inspect",
                    )
            inspected = self._run_runner(
                base,
                "transactions",
                "--root", str(root),
            )

            self.assertEqual(str(root), inspected["root"])
            self.assertEqual("recoverable", inspected["transactions"][0]["disposition"])
            self.assertEqual("old\n", target.read_text(encoding="utf-8"))

            recovered = self._run_runner(
                base,
                "recover-transactions",
                "--root", str(root),
            )

            self.assertEqual([str(target)], recovered["recovered_paths"])
            self.assertEqual("new\n", target.read_text(encoding="utf-8"))

    def test_capture_scope_flows_to_check_and_audit(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            repo = base / "business"
            (repo / ".git").mkdir(parents=True)
            resolved = self._run_runner(
                base,
                "resolve",
                "--root", str(root),
                "--cwd", str(repo),
            )

            for scope, category, title in (
                ("domain", "terminology", "Settlement term"),
                ("pattern", "backend", "Idempotent consumer"),
            ):
                with self.subTest(scope=scope):
                    request = base / f"{scope}-capture.json"
                    request.write_text(
                        json.dumps(
                            {
                                "operation": "create",
                                "knowledge_id": f"{scope}-scope-check",
                                "scope": scope,
                                "kind": scope,
                                "category": category,
                                "title": title,
                                "body": f"Verified {scope} knowledge.",
                                "evidence": ["src/example.py:L1-L1"],
                                "status": "Current",
                                "write_intent": "durable",
                                "content_kind": "knowledge",
                            }
                        ),
                        encoding="utf-8",
                    )
                    captured = self._run_runner(
                        base,
                        "capture",
                        "--root", str(root),
                        "--cwd", str(repo),
                        "--request", str(request),
                        "--today", "2026-07-19",
                    )
                    health_scope = str(captured["health_scope"])
                    self.assertEqual(scope, health_scope)
                    changed_paths = [str(path) for path in captured["changed_paths"]]
                    new_paths = [str(path) for path in captured["new_paths"]]
                    self.assertGreaterEqual(len(changed_paths), 2)
                    self.assertGreaterEqual(len(new_paths), 1)

                    check_arguments = [
                        "check",
                        "--root", str(root),
                        "--cwd", str(repo),
                        "--source-root", str(repo),
                        "--today", "2026-07-19",
                        "--scope", health_scope,
                    ]
                    for path in changed_paths:
                        check_arguments.extend(("--changed", path))
                    for path in new_paths:
                        check_arguments.extend(("--new-path", path))
                    checked = self._run_runner(base, *check_arguments)
                    self.assertEqual("Light", checked["check_type"])

                    status = root / "00-global" / "health" / "scopes" / f"{scope}-status.md"
                    checked_status = status.read_text(encoding="utf-8")
                    self.assertIn(
                        f"Changes Since Last Regular Check: {len(set(changed_paths))}",
                        checked_status,
                    )
                    self.assertIn(
                        f"New Pages Since Last Regular Check: {len(set(new_paths))}",
                        checked_status,
                    )

                    audited = self._run_runner(
                        base,
                        "audit",
                        "--root", str(root),
                        "--cwd", str(repo),
                        "--source-root", str(repo),
                        "--today", "2026-07-19",
                        "--scope", health_scope,
                    )
                    self.assertIn("Deep Knowledge Audit", audited["report"])

                    log = root / "00-global" / "health" / "logs" / scope / "2026-07.md"
                    aggregate = root / "00-global" / "health" / "health-status.md"
                    self.assertIn("Last Deep Check: 2026-07-19", status.read_text(encoding="utf-8"))
                    self.assertIn(str(resolved["project"]["identity"]), log.read_text(encoding="utf-8"))
                    self.assertIn(f"| {scope} | {scope} |", aggregate.read_text(encoding="utf-8"))

    def test_skill_uses_its_own_directory_for_runner_invocation(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("$SKILL_DIR/scripts/tracebook_runner.py", skill)
        self.assertIn("resolve --root", skill)
        verify_heading = "## Verify Knowledge Writes"
        final_heading = "## Final Task Report"
        self.assertIn(verify_heading, skill)
        self.assertIn(final_heading, skill)
        verify_workflow = skill.split(verify_heading, 1)[1].split(final_heading, 1)[0]
        verify_workflow = " ".join(verify_workflow.split())

        self.assertIn(
            "After every successful capture, require `changed_paths`, `new_paths`, "
            "and `health_scope` in its structured JSON.",
            verify_workflow,
        )
        self.assertIn(
            "Stop and report an incomplete runner response",
            verify_workflow,
        )
        self.assertIn(
            "`health_scope` is absent or is not `project`, `domain`, or `pattern`;",
            verify_workflow,
        )
        self.assertIn(
            "do not fall back to the default project scope.",
            verify_workflow,
        )
        self.assertIn(
            "Pass every capture `changed_paths` item as `--changed`",
            verify_workflow,
        )
        self.assertIn(
            "every `new_paths` item as `--new-path`",
            verify_workflow,
        )
        self.assertIn(
            "the capture `health_scope` as `--scope`.",
            verify_workflow,
        )
        self.assertIn(
            "Run `$SKILL_DIR/scripts/tracebook_runner.py audit` with the same "
            "`--root`, `--cwd`, `--today`, and `--source-root` values, plus the "
            "same scope supplied to check as `--scope`.",
            verify_workflow,
        )


if __name__ == "__main__":
    unittest.main()
