import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.context_search import _evidence_keys
from plugins.tracebook.skills.tracebook.scripts.knowledge_parse import (
    CURRENT_SECTION,
    current_evidence_paths,
    evidence_lookup_key,
    is_file_evidence,
    invalid_current_file_evidence,
    parse_query_evidence,
    stored_evidence_path,
)


class KnowledgeParseTest(unittest.TestCase):
    def test_lookup_key_strips_line_suffix_and_normalizes_separators(self) -> None:
        self.assertEqual(
            evidence_lookup_key("src/order/RefundController.java:L87"),
            evidence_lookup_key("src\\order\\RefundController.java"),
        )

    def test_lookup_key_case_sensitivity_matches_platform(self) -> None:
        same = evidence_lookup_key("SRC/Order.java") == evidence_lookup_key("src/order.java")
        self.assertEqual(os.name == "nt", same)

    def test_non_file_evidence_is_excluded(self) -> None:
        for value in ("http://x/y", "https://x/y", "test:Foo", "command:make", "human:ok"):
            self.assertFalse(is_file_evidence(value))
        self.assertTrue(is_file_evidence("src/main.py:L1"))

    def test_stored_evidence_rejects_paths_outside_repository(self) -> None:
        for value in (
            "../../outside.txt:L1",
            "/absolute/outside.txt:L1",
            "C:\\outside\\file.txt:L1",
            "file:outside.txt",
        ):
            with self.subTest(value=value):
                self.assertIsNone(stored_evidence_path(value))
        self.assertEqual(
            "src/order/RefundController.java",
            stored_evidence_path("ｓｒｃ\\order\\RefundController.java:L87"),
        )

    def test_invalid_current_file_evidence_reports_only_local_path_violations(self) -> None:
        content = _page(["../../outside.txt:L1", "https://example.test/evidence"])
        self.assertEqual(
            ["../../outside.txt:L1"],
            invalid_current_file_evidence(content),
        )

    def test_relative_path_yields_key(self) -> None:
        key, warning = parse_query_evidence("src/order/RefundController.java:L87", source_root=None)
        self.assertIsNone(warning)
        self.assertEqual(evidence_lookup_key("src/order/RefundController.java"), key)

    def test_project_absolute_path_is_relativized(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            target = root / "src" / "order" / "RefundController.java"
            target.parent.mkdir(parents=True)
            target.write_text("x", encoding="utf-8")
            key, warning = parse_query_evidence(str(target), source_root=root)
            self.assertIsNone(warning)
            self.assertEqual(evidence_lookup_key("src/order/RefundController.java"), key)

    def test_absolute_path_outside_project_warns(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve() / "project"
            root.mkdir()
            outside = Path(temp).resolve() / "other" / "X.java"
            key, warning = parse_query_evidence(str(outside), source_root=root)
            self.assertIsNone(key)
            self.assertIn("outside the project", warning)

    def test_absolute_path_without_source_root_warns(self) -> None:
        key, warning = parse_query_evidence("/abs/src/X.java", source_root=None)
        self.assertIsNone(key)
        self.assertIn("no project source root", warning)


def _page(current_evidence: list[str]) -> str:
    """An authority page whose Current evidence is ``current_evidence``."""
    listed = "\n".join(f"- `{item}`" for item in current_evidence)
    return (
        "---\nschema_version: 2\n---\n\n"
        f"## Current\n\nRefunds retry twice.\n\nEvidence:\n{listed}\n\n"
        "## History\n\n### Version 1 — 2026-01-01\n\n"
        "Older conclusion.\n\nEvidence:\n- `src/old/Retired.java:L1`\n"
    )


class EvidenceParseAgreementTest(unittest.TestCase):
    """F1 (review candidates) and E1 (evidence reverse query) must agree.

    Both now read evidence through ``knowledge_parse``; these cases pin the
    agreement on the forms that previously differed between the two copies.
    """

    def _sides(self, entry: str) -> tuple[set[str], set[str]]:
        content = _page([entry])
        review = {evidence_lookup_key(path) for path in current_evidence_paths(content)}
        section = CURRENT_SECTION.search(content).group(1)
        return review, _evidence_keys(section)

    def test_line_suffix_backslashes_and_nfkc_agree(self) -> None:
        for entry in (
            "src/order/RefundController.java",
            "src/order/RefundController.java:L87",
            "src/order/RefundController.java:L87-L92",
            "src\\order\\RefundController.java:L87",
            "ｓｒｃ/order/RefundController.java",  # NFKC-normalizable fullwidth
        ):
            with self.subTest(entry=entry):
                review, retrieval = self._sides(entry)
                self.assertEqual(review, retrieval)
                self.assertEqual(
                    {evidence_lookup_key("src/order/RefundController.java")}, retrieval
                )

    def test_non_file_entries_are_dropped_by_both_sides(self) -> None:
        for entry in ("https://x/y", "test:RefundTest", "command:make check", "human:reviewed"):
            with self.subTest(entry=entry):
                review, retrieval = self._sides(entry)
                self.assertEqual(set(), review)
                self.assertEqual(set(), retrieval)

    def test_history_evidence_is_excluded_from_both_sides(self) -> None:
        content = _page(["src/order/RefundController.java:L87"])
        retired = evidence_lookup_key("src/old/Retired.java")
        review = {evidence_lookup_key(path) for path in current_evidence_paths(content)}
        retrieval = _evidence_keys(CURRENT_SECTION.search(content).group(1))
        self.assertNotIn(retired, review)
        self.assertNotIn(retired, retrieval)


if __name__ == "__main__":
    unittest.main()
