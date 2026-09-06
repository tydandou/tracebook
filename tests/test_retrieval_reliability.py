"""Observable retrieval contracts: discovery, complete content and bounded output."""

from datetime import date
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.capture import CaptureRequest
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
    capture, read_context, read_context_for_path, resolve, retrieve_context,
)


ARRAY_FIELDS = (
    "current_context", "historical_context", "warnings",
    "omitted_entities", "history_omitted_entities",
)


class RetrievalReliabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory(prefix="tbr-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.resolved = resolve(self.base / "kb", self.repo)

    def write(self, *, target=None, day=1, **changes):
        values = dict(operation="create", scope="project", kind="decision",
                      knowledge_id="retry-rule", title="Retry policy",
                      body="legacyhandoff", evidence=("src/retry.py:L1",),
                      status="current")
        values.update(changes)
        return capture(target or self.resolved, CaptureRequest(**values), date(2026, 9, day))

    def read(self, query="", **options):
        return read_context_for_path(self.resolved.root, self.repo, query, **options)

    def assert_budget(self, result, limit):
        measured = sum(len(json.dumps(result[field], ensure_ascii=False,
                                     separators=(",", ":"))) - 2 for field in ARRAY_FIELDS)
        self.assertEqual(measured, result["budget_chars_used"])
        self.assertLessEqual(measured, limit)

    def revised(self):
        self.write()
        self.write(operation="revise", expected_version=1, body="currenthandoff", day=2)

    def test_history_discovers_current_only_in_explicit_audit_profile(self):
        self.revised()
        for options in ({}, {"include_history": True}):
            self.assertEqual([], self.read("legacyhandoff", **options)["current_context"])
        for result in (
            self.read("legacyhandoff", profile="audit"),
            retrieve_context(self.resolved, "legacyhandoff", profile="audit"),
        ):
            current, = result["current_context"]
            self.assertEqual(2, current["version"])
            self.assertEqual("currenthandoff", current["excerpt"])
            self.assertEqual("history", current["match_source"])
            self.assertEqual(1, current["matched_version"])
            self.assertEqual([1], [item["version"] for item in result["historical_context"]])
            self.assertEqual("current", current["version_state"])
            self.assert_budget(result, 50000)

    def test_adaptive_profile_uses_history_only_after_zero_current_matches(self):
        self.revised()
        current = self.read("currenthandoff", profile="adaptive")
        self.assertFalse(current["adaptive_history_fallback"])
        self.assertFalse(current["history_inspected"])
        self.assertEqual("selected_version", current["current_context"][0]["match_source"])

        for result in (
            self.read("legacyhandoff", profile="adaptive"),
            retrieve_context(self.resolved, "legacyhandoff", profile="adaptive"),
            read_context(
                self.resolved.root,
                (self.resolved.record.project_id,),
                "legacyhandoff",
                profile="adaptive",
            ),
        ):
            selected, = result["current_context"]
            self.assertTrue(result["adaptive_history_fallback"])
            self.assertTrue(result["history_inspected"])
            self.assertEqual([], result["historical_context"])
            self.assertEqual(2, selected["version"])
            self.assertEqual("history", selected["match_source"])
            self.assertEqual(1, selected["matched_version"])
            self.assert_budget(result, 20000)

        unknown = self.read("unknownhistoricalterm", profile="adaptive")
        self.assertTrue(unknown["adaptive_history_fallback"])
        self.assertTrue(unknown["history_inspected"])
        self.assertEqual([], unknown["current_context"])

        exact = self.read(knowledge_id="retry-rule", profile="adaptive")
        self.assertFalse(exact["adaptive_history_fallback"])
        self.assertFalse(exact["history_inspected"])

    def test_full_content_is_complete_from_snapshot_and_explicitly_bounded(self):
        body = "正文和引号 \"\\\"\n" * 100 + "关键结论 newtailtoken"
        written = self.write(body=body)
        discovery = self.read("newtailtoken")
        item, = discovery["current_context"]
        self.assertNotIn("newtailtoken", item["excerpt"])
        self.assertTrue(item["excerpt_truncated"])
        self.assertFalse(discovery["truncated"])
        # A mutable materialized page must not replace the committed read tree.
        written.new_paths[0].write_text("uncommitted manual edit", encoding="utf-8")
        complete = self.read(knowledge_id="retry-rule", full_content=True)
        self.assertEqual(body, complete["current_context"][0]["body"])
        self.assertEqual(discovery["read_snapshots"], complete["read_snapshots"])
        self.assert_budget(complete, 20000)
        small = self.read(knowledge_id="retry-rule", full_content=True, max_chars=100)
        self.assertEqual([], small["current_context"])
        self.assertIn("max_chars", small["truncation_reason"])
        self.assert_budget(small, 100)
        with self.assertRaisesRegex(ValueError, "full-content requires knowledge-id"):
            self.read("newtailtoken", full_content=True)

    def test_uninspected_history_is_unknown_and_as_of_does_not_see_future_terms(self):
        self.revised()
        default = self.read("currenthandoff")
        self.assertFalse(default["history_inspected"])
        self.assertIsNone(default["history_available"])
        self.assertIsNone(default["history_available_count"])
        old = self.read("legacyhandoff", profile="audit", as_of=date(2026, 9, 1))
        self.assertEqual(1, old["current_context"][0]["version"])
        self.assertEqual("historical", old["current_context"][0]["version_state"])
        self.assertEqual("2026-09-01", old["as_of"])
        self.assertEqual([], old["historical_context"])
        self.assertEqual([], self.read("currenthandoff", profile="audit",
                                      as_of=date(2026, 9, 1))["current_context"])

    def test_audit_never_resurrects_ineligible_entities(self):
        for status in ("pending", "deprecated", "superseded"):
            with self.subTest(status=status):
                identity = "rule-" + status
                self.write(knowledge_id=identity)
                extra = {}
                if status == "superseded":
                    self.write(knowledge_id="replacement", body="current replacement")
                    extra["replacement_knowledge_id"] = "replacement"
                self.write(knowledge_id=identity, operation="change-status",
                           expected_version=1, body="retired conclusion", status=status,
                           day=2, **extra)
                found = self.read("legacyhandoff", profile="audit")
                self.assertNotIn(identity, [item["knowledge_id"] for item in found["current_context"]])
                explicit = self.read("legacyhandoff", profile="audit", status=status)
                self.assertEqual([identity], [item["knowledge_id"] for item in explicit["current_context"]])
                self.assertEqual(status, explicit["current_context"][0]["status"])

    def test_history_identity_includes_project_kind_and_scope(self):
        self.revised()
        self.write(kind="module", body="unrelated module")
        self.write(scope="domain", body="unrelated domain")
        self.write(scope="pattern", body="unrelated pattern")
        other_repo = self.base / "other"
        other_repo.mkdir()
        other = resolve(self.resolved.root, other_repo)
        self.write(target=other, body="otherlegacy")
        self.write(target=other, operation="revise", expected_version=1,
                   body="othercurrent", day=2)
        local = self.read("otherlegacy", profile="audit")
        self.assertEqual([], local["current_context"])
        self.assertEqual([], self.read("legacyhandoff", profile="audit", kind="module")["current_context"])
        combined = read_context(self.resolved.root,
                                (self.resolved.record.project_id, other.record.project_id),
                                "legacyhandoff otherlegacy", profile="audit", scope="all")
        self.assertEqual(2, combined["matched_count"])
        self.assertEqual(2, len({item["path"] for item in combined["current_context"]}))
        self.assertEqual({self.resolved.record.project_id, other.record.project_id},
                         {item["source_project"]["project_id"] for item in combined["historical_context"]})
        for scope in ("domain", "pattern"):
            self.assertEqual([], self.read("legacyhandoff", profile="audit", scope=scope)["current_context"])

    def test_history_evidence_does_not_become_current_reverse_lookup(self):
        self.write()
        self.write(operation="revise", expected_version=1, body="currenthandoff",
                   evidence=("src/current.py:L1",), day=2)
        self.assertEqual([], self.read(evidence_paths=("src/retry.py",), profile="audit")["current_context"])
        combined = self.read("legacyhandoff", evidence_paths=("src/retry.py",), profile="audit")
        self.assertFalse(combined["current_context"][0]["evidence_match"])

    def test_limits_count_entities_separately_from_attached_versions(self):
        self.revised()
        self.write(operation="revise", expected_version=2, body="thirdhandoff", day=3)
        found = self.read(knowledge_id="retry-rule", include_history=True,
                          max_results=1, max_chars=10000, full_content=True)
        self.assertEqual(1, found["returned_current_count"])
        self.assertEqual(2, found["returned_history_count"])
        self.assertEqual(3, found["returned_count"])
        self.assertEqual(["currenthandoff", "legacyhandoff"],
                         [item["body"] for item in found["historical_context"]])
        self.assert_budget(found, 10000)

    def test_warnings_and_omission_samples_share_budget_and_read_is_pure(self):
        self.revised()
        for index in range(12):
            self.write(knowledge_id=f"rule-{index}", body="currenthandoff")
        root = self.resolved.root
        fingerprint = lambda: {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in root.rglob("*") if p.is_file()}
        before = fingerprint()
        for limit in (1, 900, 2000, 10000):
            result = self.read("currenthandoff", profile="audit", max_results=1,
                               max_chars=limit, evidence_paths=(str(self.base / "outside.py"),))
            self.assertEqual(13, result["matched_count"])
            self.assertEqual(1, result["warning_count"])
            self.assertLessEqual(len(result["omitted_entities"]), 10)
            self.assertTrue(result["omitted_samples_truncated"])
            self.assert_budget(result, limit)
            self.assertEqual(result, self.read("currenthandoff", profile="audit", max_results=1,
                                              max_chars=limit, evidence_paths=(str(self.base / "outside.py"),)))
        self.assertEqual(before, fingerprint())

    def test_invalid_evidence_only_uses_same_budget_without_scanning_pages(self):
        self.write()
        result = self.read(evidence_paths=(str(self.base / "outside.py"),), max_chars=1)
        self.assertEqual([], result["current_context"])
        self.assertEqual(0, result["matched_count"])
        self.assertEqual(1, result["omitted_warning_count"])
        self.assertFalse(result["history_inspected"])
        self.assert_budget(result, 1)
        with self.assertRaisesRegex(ValueError, "result limits must be positive"):
            self.read(evidence_paths=(str(self.base / "outside.py"),), max_chars=0)


if __name__ == "__main__":
    unittest.main()
