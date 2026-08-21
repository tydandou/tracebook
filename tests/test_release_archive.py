from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class ReleaseArchiveTest(unittest.TestCase):
    excluded_prefixes = (
        "site/",
        "launch/",
        "demo/",
    )
    excluded_files = {
        ".github/workflows/pages.yml",
        "assets/tracebook-social-preview.svg",
        "assets/tracebook-social-preview.png",
        "tests/test_site_artifacts.py",
        "tests/test_cross_session_demo.py",
    }

    def _archive_paths(self, archive_format: str, suffix: str) -> set[str]:
        with TemporaryDirectory() as temp:
            archive = Path(temp) / f"tracebook{suffix}"
            subprocess.run(
                (
                    "git",
                    "archive",
                    "--worktree-attributes",
                    f"--format={archive_format}",
                    f"--output={archive}",
                    "HEAD",
                ),
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            if archive_format == "zip":
                with ZipFile(archive) as package:
                    return set(package.namelist())
            with tarfile.open(archive, mode="r:gz") as package:
                return set(package.getnames())

    def test_git_archives_exclude_website_and_launch_collateral(self) -> None:
        for archive_format, suffix in (("zip", ".zip"), ("tar.gz", ".tar.gz")):
            with self.subTest(archive_format=archive_format):
                paths = self._archive_paths(archive_format, suffix)
                for prefix in self.excluded_prefixes:
                    self.assertFalse(
                        any(path.startswith(prefix) for path in paths),
                        f"release archive unexpectedly contains {prefix}",
                    )
                self.assertTrue(self.excluded_files.isdisjoint(paths))
                self.assertFalse(
                    any(path.startswith("docs/") and path.endswith(".md") for path in paths)
                )
                self.assertIn("plugins/tracebook/skills/tracebook/SKILL.md", paths)
                self.assertIn("LICENSE", paths)
                self.assertIn("README.md", paths)
                self.assertIn("assets/tracebook-hero.svg", paths)

    def test_release_workflow_builds_and_uploads_clean_archives(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("types: [published]", workflow)
        self.assertIn("git archive --format=zip", workflow)
        self.assertIn("git archive --format=tar.gz", workflow)
        self.assertIn("sha256sum", workflow)
        self.assertIn("gh release upload", workflow)


if __name__ == "__main__":
    unittest.main()
