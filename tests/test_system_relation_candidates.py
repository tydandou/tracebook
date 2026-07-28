from datetime import date
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

RUNNER = (
    Path(__file__).resolve().parents[1]
    / "plugins" / "tracebook" / "skills" / "tracebook" / "scripts" / "tracebook_runner.py"
)


class SystemRelationCandidateTest(unittest.TestCase):
    """`check` must surface cross-repository evidence as a relation candidate."""

    def _run(self, *arguments: str, stdin: bytes | None = None, expect_ok: bool = True) -> dict:
        result = subprocess.run(
            [sys.executable, str(RUNNER), *arguments],
            capture_output=True, check=False, input=stdin,
        )
        payload = json.loads(result.stdout.decode("utf-8"))
        if expect_ok:
            self.assertEqual(0, result.returncode, payload)
        return payload

    def _repo(self, path: Path, name: str) -> Path:
        (path / "src").mkdir(parents=True)
        (path / ".git").mkdir()
        (path / "src" / f"{name}.go").write_text(f"package {name}\n", encoding="utf-8")
        return path

    def _capture(self, root: Path, repo: Path, knowledge_id: str, evidence: list[str]) -> dict:
        return self._run(
            "capture", "--root", str(root), "--cwd", str(repo),
            "--request", "-", "--today", "2026-08-10",
            stdin=json.dumps({
                "operation": "create", "knowledge_id": knowledge_id,
                "scope": "project", "kind": "decision",
                "title": knowledge_id, "body": "Conclusion under test.",
                "evidence": evidence,
            }, ensure_ascii=False).encode("utf-8"),
        )

    def _candidates(self, root: Path, repo: Path) -> list[str]:
        report = self._run(
            "check", "--root", str(root), "--cwd", str(repo),
            "--source-root", str(repo), "--today", "2026-08-10",
        )["report"]
        start = report.find("### Review Candidates")
        section = report[start:] if start >= 0 else ""
        return [
            line for line in section.splitlines()
            if "system_relation_candidate" in line
        ]

    def _fixture(self, base: Path) -> tuple[Path, Path, Path, dict]:
        """A nested layout: `dte` is registered inside the `docs` working tree.

        The capture gate rejects `..` and absolute evidence paths, so a stored
        file path can only reach another project when that project is registered
        at a subdirectory — the monorepo case. This is the reachable shape of the
        signal, not an artificial one.
        """
        root = base / "knowledge"
        docs = self._repo(base / "docs", "docs")
        dte = self._repo(docs / "services" / "dte", "dte")
        ids = {}
        for repo, name in ((docs, "docs"), (dte, "dte")):
            resolved = self._run("resolve", "--root", str(root), "--cwd", str(repo))
            ids[name] = resolved["project"]["project_id"]
        return root, docs, dte, ids

    def test_evidence_in_another_registered_project_is_reported(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root, docs, dte, _ = self._fixture(base)
            self._capture(root, docs, "spans-two-repos", ["services/dte/src/dte.go:L1"])

            lines = self._candidates(root, docs)
            self.assertEqual(1, len(lines), lines)
            self.assertIn("[advisory]", lines[0])
            self.assertIn("spans-two-repos", lines[0])
            self.assertIn("dte", lines[0])
            self.assertIn("no system relation recorded", lines[0])

    def test_no_candidate_once_a_system_relation_exists(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root, docs, dte, ids = self._fixture(base)
            self._capture(root, docs, "spans-two-repos", ["services/dte/src/dte.go:L1"])
            self.assertTrue(self._candidates(root, docs), "fixture must flag first")

            system = self._run("system-create", "--root", str(root), "--name", "Delivery")
            system_id = system["system"]["system_id"]
            for project_id in ids.values():
                self._run(
                    "system-bind-project", "--root", str(root),
                    "--system-id", system_id, "--project-id", project_id,
                )
            self._run(
                "system-relate", "--root", str(root), "--system-id", system_id,
                "--source-project-id", ids["docs"],
                "--target-project-id", ids["dte"], "--kind", "designs",
            )

            self.assertEqual([], self._candidates(root, docs))

    def test_shared_topic_words_alone_never_flag(self) -> None:
        """Guards the deliberate narrowness: only cross-repo evidence counts."""
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root, docs, dte, _ = self._fixture(base)
            # Same subject in both projects, but each cites only its own file.
            self._capture(root, docs, "order-refund-rule", ["src/docs.go:L1"])
            self._capture(root, dte, "order-refund-impl", ["src/dte.go:L1"])

            self.assertEqual([], self._candidates(root, docs))
            self.assertEqual([], self._candidates(root, dte))

    def test_nested_project_citing_its_own_source_never_flags_its_parent(self) -> None:
        """A path is owned by its deepest registered project, not every ancestor."""
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root, docs, dte, _ = self._fixture(base)
            # dte lives inside the docs working tree, so its own files are also
            # under docs' registered location.
            self._capture(root, dte, "owns-its-source", ["src/dte.go:L1"])

            self.assertEqual([], self._candidates(root, dte))

    def test_evidence_naming_an_unregistered_directory_never_flags(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root, docs, _, _ = self._fixture(base)
            vendor = docs / "vendor"
            vendor.mkdir()
            (vendor / "lib.go").write_text("package vendor\n", encoding="utf-8")
            self._capture(root, docs, "cites-vendor", ["vendor/lib.go:L1"])

            self.assertEqual([], self._candidates(root, docs))


if __name__ == "__main__":
    unittest.main()
