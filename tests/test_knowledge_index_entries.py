from pathlib import Path
import json
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

RUNNER = (
    Path(__file__).resolve().parents[1]
    / "plugins" / "tracebook" / "skills" / "tracebook" / "scripts" / "tracebook_runner.py"
)


class KnowledgeIndexEntryTest(unittest.TestCase):
    """A project index must hold one entry per entity, titled as it is now."""

    def _run(self, *arguments: str, stdin: bytes | None = None, expect_ok: bool = True):
        result = subprocess.run(
            [sys.executable, str(RUNNER), *arguments],
            capture_output=True, check=False, input=stdin,
        )
        payload = json.loads(result.stdout.decode("utf-8"))
        if expect_ok:
            self.assertEqual(0, result.returncode, payload)
        return payload

    def _fixture(self, base: Path) -> tuple[Path, Path, Path]:
        root, repo = base / "knowledge", base / "service"
        (repo / "src").mkdir(parents=True)
        (repo / ".git").mkdir()
        (repo / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
        resolved = self._run("resolve", "--root", str(root), "--cwd", str(repo))
        index = root / resolved["project"]["relative_path"] / "index.md"
        return root, repo, index

    def _capture(self, root: Path, repo: Path, title: str, **over) -> dict:
        request = {
            "operation": "create", "knowledge_id": "timeout-policy",
            "scope": "project", "kind": "decision", "title": title,
            "body": "Conclusion under test.", "evidence": ["src/app.py:L1"],
        }
        request.update(over)
        return self._run(
            "capture", "--root", str(root), "--cwd", str(repo),
            "--request", "-", "--today", "2026-08-10",
            stdin=json.dumps(request, ensure_ascii=False).encode("utf-8"),
        )

    def _entries(self, index: Path) -> list[str]:
        return [
            line.strip() for line in index.read_text(encoding="utf-8").splitlines()
            if line.startswith("- [")
        ]

    def test_retitled_revisions_keep_one_entry_carrying_the_current_title(self) -> None:
        with TemporaryDirectory() as temp:
            root, repo, index = self._fixture(Path(temp))
            self._capture(root, repo, "Timeout policy")
            self.assertEqual(1, len(self._entries(index)), self._entries(index))

            for version, title in ((1, "Timeout policy v2"), (2, "Request timeout policy")):
                self._capture(root, repo, title,
                              operation="revise", expected_version=version)
                entries = self._entries(index)
                self.assertEqual(1, len(entries), entries)
                self.assertIn(title, entries[0])

            # The superseded titles are gone, not merely outnumbered.
            body = index.read_text(encoding="utf-8")
            self.assertNotIn("Timeout policy v2", body)
            self.assertIn("Request timeout policy", body)

    def test_replaying_an_identical_capture_leaves_the_index_byte_identical(self) -> None:
        with TemporaryDirectory() as temp:
            root, repo, index = self._fixture(Path(temp))
            self._capture(root, repo, "Timeout policy")
            before = index.read_bytes()
            replay = self._capture(root, repo, "Timeout policy")
            self.assertTrue(replay["skipped"], replay)
            self.assertEqual(before, index.read_bytes())

    def test_distinct_entities_each_keep_their_own_entry(self) -> None:
        with TemporaryDirectory() as temp:
            root, repo, index = self._fixture(Path(temp))
            self._capture(root, repo, "Timeout policy")
            self._capture(root, repo, "Retry policy", knowledge_id="retry-policy")
            entries = self._entries(index)
            self.assertEqual(2, len(entries), entries)
            self.assertTrue(any("timeout-policy.md" in e for e in entries), entries)
            self.assertTrue(any("retry-policy.md" in e for e in entries), entries)

    def _entity_integrity(self, root: Path, repo: Path) -> str:
        report = self._run(
            "check", "--root", str(root), "--cwd", str(repo), "--today", "2026-08-10",
        )["report"]
        start = report.find("### Schema-v2 Entity Integrity")
        return report[start:start + 700] if start >= 0 else ""

    def test_check_reports_an_index_that_links_one_entity_twice(self) -> None:
        """`_duplicate_pages` skips index.md, so this needs its own signal."""
        with TemporaryDirectory() as temp:
            root, repo, index = self._fixture(Path(temp))
            self._capture(root, repo, "Timeout policy")
            self.assertIn("- None", self._entity_integrity(root, repo))

            link = self._entries(index)[0].split("](", 1)[1].rstrip(")")
            index.write_text(
                index.read_text(encoding="utf-8").rstrip()
                + f"\n- [Stale title]({link})\n",
                encoding="utf-8",
            )
            section = self._entity_integrity(root, repo)
            self.assertIn("2 entries link", section)
            self.assertIn(link, section)
            self.assertIn("stale titles", section)

    def test_check_ignores_repeated_links_to_an_ordinary_markdown_page(self) -> None:
        with TemporaryDirectory() as temp:
            root, repo, index = self._fixture(Path(temp))
            project = index.parent
            notes = project / "notes.md"
            notes.write_text("# Notes\n", encoding="utf-8")
            index.write_text(
                index.read_text(encoding="utf-8").rstrip()
                + "\n- [Notes](notes.md)\n- [Notes again](./notes.md)\n",
                encoding="utf-8",
            )

            self.assertIn("- None", self._entity_integrity(root, repo))

    def test_check_stays_clean_once_the_duplicate_is_converged(self) -> None:
        with TemporaryDirectory() as temp:
            root, repo, index = self._fixture(Path(temp))
            self._capture(root, repo, "Timeout policy")
            link = self._entries(index)[0].split("](", 1)[1].rstrip(")")
            index.write_text(
                index.read_text(encoding="utf-8").rstrip()
                + f"\n- [Stale title]({link})\n",
                encoding="utf-8",
            )
            self.assertIn("2 entries link", self._entity_integrity(root, repo))

            self._capture(root, repo, "Final title",
                          operation="revise", expected_version=1)
            self.assertIn("- None", self._entity_integrity(root, repo))

    def test_a_write_converges_an_index_that_already_accumulated_duplicates(self) -> None:
        """Pre-existing duplicates for the touched link collapse to one entry."""
        with TemporaryDirectory() as temp:
            root, repo, index = self._fixture(Path(temp))
            self._capture(root, repo, "Timeout policy")
            link = self._entries(index)[0].split("](", 1)[1].rstrip(")")
            index.write_text(
                index.read_text(encoding="utf-8").rstrip()
                + f"\n- [Stale title one]({link})\n- [Stale title two]({link})\n",
                encoding="utf-8",
            )
            self.assertEqual(3, len(self._entries(index)))

            self._capture(root, repo, "Final title",
                          operation="revise", expected_version=1)
            entries = self._entries(index)
            self.assertEqual(1, len(entries), entries)
            self.assertIn("Final title", entries[0])

    def test_domain_and_pattern_indexes_also_converge_by_stable_link(self) -> None:
        with TemporaryDirectory() as temp:
            root, repo, _ = self._fixture(Path(temp))
            for scope, directory in (("domain", "02-domain"), ("pattern", "03-patterns")):
                with self.subTest(scope=scope):
                    knowledge_id = f"{scope}-timeout-policy"
                    self._capture(
                        root,
                        repo,
                        f"{scope.title()} timeout policy",
                        scope=scope,
                        knowledge_id=knowledge_id,
                    )
                    self._capture(
                        root,
                        repo,
                        f"Current {scope} timeout policy",
                        scope=scope,
                        knowledge_id=knowledge_id,
                        operation="revise",
                        expected_version=1,
                    )
                    index = root / directory / "index.md"
                    entries = [
                        line for line in self._entries(index)
                        if f"{knowledge_id}.md" in line
                    ]
                    self.assertEqual(1, len(entries), entries)
                    self.assertIn(f"Current {scope} timeout policy", entries[0])


if __name__ == "__main__":
    unittest.main()
