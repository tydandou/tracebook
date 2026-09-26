"""Public retrieval behavior for identifier-driven engineering tasks.

All names, identifiers and descriptions are fictional test fixtures.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.capture import CaptureRequest
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
    capture, read_context_for_path, resolve,
)


class IdentifierRetrievalTest(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="tb-identifiers-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.context = resolve(self.base / "kb", self.repo)

    def write(self, identity, title="说明", body="neutral", **options):
        request = dict(operation="create", scope="project", kind="decision",
                       knowledge_id=identity, title=title, body=body,
                       evidence=("test:fixture",), status="current")
        request.update(options)
        return capture(self.context, CaptureRequest(**request), date(2026, 9, 26))

    def read(self, query="", **options):
        return read_context_for_path(self.context.root, self.repo, query,
                                     **{"profile": "adaptive", **options})

    def ids(self, query="", **options):
        return [item["knowledge_id"] for item in self.read(query, **options)["current_context"]]

    def test_complete_identifiers_outrank_generic_business_words(self):
        self.write("widget-entry", "虚构组件校验入口",
                   "使用 tools/widget_inspect 检查 sample_record。仅用于虚构夹具。")
        for index in range(6):
            self.write(f"background-{index}",
                       "tools widget inspect sample record 数据检查 虚构组件 校验 执行方式",
                       "另一个虚构组件的背景材料。",
                       evidence=(f"src/tools/widget/inspect/sample/record/{index}.py:L1",))
        for query in ("widget_inspect sample_record",
                      "tools widget_inspect sample_record 数据检查 虚构组件 校验 执行方式"):
            with self.subTest(query=query):
                result = self.read(query)
                self.assertEqual("widget-entry", result["current_context"][0]["knowledge_id"])
                self.assertEqual(7, result["matched_count"])
        self.assertEqual([], self.ids(evidence_paths=("tools/widget_inspect/main.py",)))

    def test_hyphen_components_are_discoverable_without_substring_matches(self):
        self.write("handler", body="fetch-customer-settings")
        for query in ("fetch", "customer", "settings", "fetch-customer-settings"):
            with self.subTest(query=query):
                self.assertEqual(["handler"], self.ids(query))
        self.assertEqual([], self.ids("fetcher"))
        self.assertEqual([], self.ids("setting"))
        self.assertEqual([], self.ids("the"))

    def test_complete_query_keeps_references_without_expanding_generic_components(self):
        self.write("refund-policy", title="旧范围", body="只适用于旧模块")
        self.write("modern-rule", body="refund-policy 不适用于当前新模块，需要核验")
        self.write("payment-policy", title="policy", body="policy for another module")
        self.assertEqual(["refund-policy", "modern-rule"], self.ids("refund-policy"))
        self.assertEqual(["refund-policy"], self.ids(knowledge_id="refund-policy", full_content=True))

    def test_general_title_match_does_not_override_combined_relevance(self):
        self.write("relevant-rule", title="当前重试规则", body="refund retry timeout jointly govern refunds",
                   evidence=("src/retry/timeout.py:L1",))
        self.write("background-rule", title="refund", body="产品退款页面配色")
        self.assertEqual(["relevant-rule", "background-rule"], self.ids("refund retry timeout"))

    def test_whole_identifier_is_distinct_from_a_longer_identifier(self):
        self.write("relevant-rule", body="load_user")
        self.write("background-rule", title="load_user_profile", body="Other handler")
        self.assertEqual("relevant-rule", self.ids("load_user")[0])
        self.assertEqual("relevant-rule", self.ids("ｌｏａｄ＿ｕｓｅｒ")[0])
        self.assertEqual({"relevant-rule", "background-rule"}, set(self.ids("load")))

    def test_path_identifier_handles_line_suffix_and_windows_separator(self):
        self.write("relevant-rule", evidence=("src/load-user_profile.py:L12-L19",))
        self.write("background-rule", title="src load-user profile py", body="Other module")
        for query in ("src/load-user_profile.py", r"src\load-user_profile.py", "load-user_profile"):
            with self.subTest(query=query):
                self.assertEqual("relevant-rule", self.ids(query)[0])

    def test_current_evidence_priority_and_union_are_preserved(self):
        self.write("direct-source", body="unrelated", evidence=("src/current.py:L1",))
        self.write("exact-symbol", body="target_fn", evidence=("src/other.py:L1",))
        result = self.read("target_fn", evidence_paths=("src/current.py",))
        self.assertEqual(["direct-source", "exact-symbol"],
                         [x["knowledge_id"] for x in result["current_context"]])
        self.assertEqual([True, False], [x["evidence_match"] for x in result["current_context"]])

    def test_component_history_discovery_returns_current_not_old_rule(self):
        self.write("renamed-rule", body="fetch-customer-settings")
        self.write("renamed-rule", body="Current replacement", operation="revise", expected_version=1)
        result = self.read("fetch")
        self.assertTrue(result["adaptive_history_fallback"])
        self.assertEqual(1, len(result["current_context"]))
        item, = result["current_context"]
        self.assertEqual("Current replacement", item["excerpt"])
        self.assertEqual((2, 1, "history"), (item["version"], item["matched_version"], item["match_source"]))
        self.assertEqual([], result["historical_context"])
        self.write("unrelated-background", title="fetch", body="Other task")
        # Weak Current still suppresses adaptive history; that contract is not changed here.
        self.assertEqual(["unrelated-background"], self.ids("fetch"))
        self.assertEqual({"renamed-rule", "unrelated-background"}, set(self.ids("fetch", profile="audit")))

    def test_queries_are_read_only_isolated_and_revision_aware(self):
        self.write("entry-one", body="alpha_handler")
        self.write("entry-two", body="beta_handler")
        queries = ["alpha_handler", "beta_handler"] * 3
        before = {str(p.relative_to(self.context.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.context.root.rglob("*") if p.is_file()}
        expected = {q: self.read(q) for q in set(queries)}
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(self.read, queries))
        self.assertEqual([expected[q] for q in queries], results)
        self.assertEqual(before, {str(p.relative_to(self.context.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in self.context.root.rglob("*") if p.is_file()})
        results[0]["current_context"][0]["evidence"].append("caller mutation")
        self.assertEqual(expected[queries[0]], self.read(queries[0]))
        self.write("entry-one", body="revised value", operation="revise", expected_version=1)
        self.assertNotIn("entry-one", self.ids("alpha_handler", profile="default"))
        self.assertEqual(2, self.read(knowledge_id="entry-one")["current_context"][0]["version"])


if __name__ == "__main__":
    unittest.main()
