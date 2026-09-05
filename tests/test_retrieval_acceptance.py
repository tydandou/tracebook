"""Synthetic acceptance cases; contract checks are not an agent recall score."""

from datetime import date
import hashlib
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.capture import CaptureRequest
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
    capture, check, read_context_for_path, resolve,
)


def fingerprint(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def write_item(context, identity="refund-policy", day=1, **overrides):
    values = dict(operation="create", knowledge_id=identity, scope="project",
                  kind="decision", title="Refund retry policy", status="current",
                  body="Legacyhandoff refund retries use nine attempts.",
                  evidence=("src/retry.py:L1",))
    values.update(overrides)
    return capture(context, CaptureRequest(**values), date(2026, 9, day))


def prepare_cases(base):
    repo = base / "sample-app"
    (repo / "src").mkdir(parents=True)
    for name, content in (("retry.py", "ATTEMPTS = 2\n"),
                          ("payment.py", "ATTEMPTS = 2\n"),
                          ("socket.py", "DEADLINE = 3\n")):
        (repo / "src" / name).write_text(content, encoding="utf-8")
    context = resolve(base / "kb", repo)
    write_item(context)
    write_item(context, operation="revise", expected_version=1, day=2,
               body="背景说明。" * 110 + "Currenthandoff refund retries use two attempts. 退款重试最多两次。")
    write_item(context, "payment-policy", title="支付回调", body="支付回调失败后最多重试两次。",
               evidence=("src/payment.py:L1",))
    write_item(context, "socket-policy", title="Socket deadline",
               body="Socket deadline is three seconds.", evidence=("src/socket.py:L1",))
    write_item(context, "pending-policy", title="Pending proposal", body="pendingtoken",
               status="pending", evidence=())
    write_item(context, "retired-policy", title="Retired proposal", body="retiredtoken",
               status="deprecated")
    write_item(context, "replacement-policy", title="Replacement policy", body="successortoken", evidence=("test:replacement",))
    write_item(context, "superseded-policy", title="Superseded proposal", body="supersededtoken",
               status="superseded", replacement_knowledge_id="replacement-policy")
    return repo, context


# relevant_ids is an independently declared semantic target; expected_ids describes
# today's documented API behavior. A contract pass with an empty semantic hit is
# explicitly a retrieval gap, never a successful answer or a model judgment.
QUERY_CASES = (
    ("exact-query", {"query": "refund-policy"}, ("refund-policy",), ("refund-policy",)),
    ("exact-id", {"knowledge_id": "refund-policy"}, ("refund-policy",), ("refund-policy",)),
    ("english-literal", {"query": "refund"}, ("refund-policy",), ("refund-policy",)),
    ("chinese-literal", {"query": "支付回调"}, ("payment-policy",), ("payment-policy",)),
    ("mixed-language", {"query": "refund 重试"}, ("refund-policy", "payment-policy"), ("refund-policy", "payment-policy")),
    ("unknown-question", {"query": "unrelatedxyz"}, (), ()),
    ("english-synonym", {"query": "reimbursement"}, (), ("refund-policy",)),
    ("cross-language", {"query": "套接字截止时间"}, (), ("socket-policy",)),
    ("old-term-default", {"query": "Legacyhandoff"}, (), ("refund-policy",)),
    ("old-term-attachment", {"query": "Legacyhandoff", "include_history": True}, (), ("refund-policy",)),
    ("old-term-audit", {"query": "Legacyhandoff", "profile": "audit"}, ("refund-policy",), ("refund-policy",)),
    ("past-as-of", {"query": "Legacyhandoff", "profile": "audit", "as_of": date(2026, 9, 1)}, ("refund-policy",), ("refund-policy",)),
    ("future-term-as-of", {"query": "Currenthandoff", "profile": "audit", "as_of": date(2026, 9, 1)}, (), ()),
    ("full-current", {"knowledge_id": "refund-policy", "full_content": True}, ("refund-policy",), ("refund-policy",)),
    ("current-evidence", {"evidence_paths": ("src/retry.py",)}, ("refund-policy",), ("refund-policy",)),
    ("pending-default", {"query": "pendingtoken"}, (), ()),
    ("pending-explicit", {"query": "pendingtoken", "status": "pending"}, ("pending-policy",), ("pending-policy",)),
    ("retired-default", {"query": "retiredtoken", "profile": "audit"}, (), ()),
    ("retired-explicit", {"query": "retiredtoken", "status": "deprecated"}, ("retired-policy",), ("retired-policy",)),
    ("superseded-default", {"query": "supersededtoken", "profile": "audit"}, (), ()),
    ("superseded-explicit", {"query": "supersededtoken", "status": "superseded"}, ("superseded-policy",), ("superseded-policy",)),
    ("wrong-kind", {"knowledge_id": "refund-policy", "kind": "module"}, (), ()),
    ("wrong-domain", {"query": "refund", "scope": "domain"}, (), ()),
    ("wrong-pattern", {"query": "refund", "scope": "pattern"}, (), ()),
)


class RetrievalAcceptanceTest(unittest.TestCase):
    def test_explicit_query_matrix_and_read_purity(self):
        with TemporaryDirectory(prefix="tba-") as temporary:
            repo, context = prepare_cases(Path(temporary).resolve())
            before = fingerprint(context.root)
            source_before = fingerprint(repo)
            for name, options, expected, _ in QUERY_CASES:
                with self.subTest(case=name):
                    result = read_context_for_path(context.root, repo, **{"query": "", **options})
                    self.assertEqual(set(expected), {x["knowledge_id"] for x in result["current_context"]})
                    if name == "past-as-of":
                        self.assertEqual(1, result["current_context"][0]["version"])
                    if name == "old-term-audit":
                        self.assertEqual(2, result["current_context"][0]["version"])
                        self.assertEqual(1, result["current_context"][0]["matched_version"])
                    if name == "superseded-explicit":
                        self.assertEqual("replacement-policy", result["current_context"][0]["replacement_knowledge_id"])
            self.assertEqual(before, fingerprint(context.root))
            self.assertEqual(source_before, fingerprint(repo))

    def test_full_read_followup_and_intervening_revision_are_visible(self):
        with TemporaryDirectory(prefix="tbf-") as temporary:
            repo, context = prepare_cases(Path(temporary).resolve())
            first = read_context_for_path(context.root, repo, "Currenthandoff")
            self.assertTrue(first["current_context"][0]["excerpt_truncated"])
            self.assertNotIn("two attempts", first["current_context"][0]["excerpt"])
            full = read_context_for_path(context.root, repo, "", knowledge_id="refund-policy", full_content=True)
            self.assertIn("two attempts", full["current_context"][0]["body"])
            self.assertEqual(first["read_snapshots"], full["read_snapshots"])
            write_item(context, operation="revise", expected_version=2, day=3, body="Newest rule uses four attempts.")
            new = read_context_for_path(context.root, repo, "", knowledge_id="refund-policy", full_content=True)
            self.assertEqual(3, new["current_context"][0]["version"])
            self.assertNotEqual(full["read_snapshots"], new["read_snapshots"])
            self.assertIn("four attempts", new["current_context"][0]["body"])

    def test_no_write_gate_does_not_disable_reading(self):
        with TemporaryDirectory(prefix="tbn-") as temporary:
            repo, context = prepare_cases(Path(temporary).resolve())
            before = fingerprint(context.root)
            skipped = write_item(context, "blocked-write", user_prohibits_write=True)
            self.assertTrue(skipped.skipped)
            result = read_context_for_path(context.root, repo, "", knowledge_id="refund-policy")
            self.assertEqual(1, result["matched_count"])
            self.assertEqual(before, fingerprint(context.root))

    def test_identity_sharing_does_not_assert_branch_applicability(self):
        with TemporaryDirectory(prefix="tbg-") as temporary:
            base = Path(temporary).resolve()
            contexts = []
            repos = []
            commits = []
            for branch, attempts, remote in (
                ("legacy", 9, "https://github.com/example/sample-app.git"),
                ("modern", 2, "git@github.com:example/sample-app.git"),
            ):
                repo = base / branch
                repo.mkdir()
                subprocess.run(["git", "init", "-q", "-b", branch, str(repo)], check=True, capture_output=True)
                (repo / "src").mkdir()
                (repo / "src/retry.py").write_text(f"ATTEMPTS = {attempts}\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(repo), "add", "src/retry.py"], check=True, capture_output=True)
                subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                                "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture revision"], check=True, capture_output=True)
                subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", remote], check=True, capture_output=True)
                commits.append(subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"]))
                repos.append(repo)
                contexts.append(resolve(base / "kb", repo))
            self.assertNotEqual(commits[0], commits[1])
            self.assertEqual(contexts[0].record.project_id, contexts[1].record.project_id)
            write_item(contexts[1], body="Modern branch: ATTEMPTS = 2. Verify source before applying.")
            results = [read_context_for_path(base / "kb", repo, "", knowledge_id="refund-policy", full_content=True) for repo in repos]
            self.assertEqual(results[0]["current_context"], results[1]["current_context"])
            self.assertIn("ATTEMPTS = 9", (repos[0] / "src/retry.py").read_text())
            self.assertIn("ATTEMPTS = 2", results[0]["current_context"][0]["body"])

    def test_missing_source_is_reported_after_structurally_valid_capture(self):
        with TemporaryDirectory(prefix="tbh-") as temporary:
            repo, context = prepare_cases(Path(temporary).resolve())
            written = write_item(context, "missing-source", evidence=("src/absent.py:L1",))
            report = check(context, list(written.changed_paths), date(2026, 9, 5),
                           source_root=repo, new_paths=list(written.new_paths)).report
            self.assertTrue(any(item.knowledge_id == "missing-source" and item.reason == "source_missing"
                                for item in report.review_candidates))


if __name__ == "__main__":
    unittest.main()
