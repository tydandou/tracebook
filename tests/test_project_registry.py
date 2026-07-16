from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.project_registry import ensure_project, normalize_remote, registry_path


class ProjectRegistryTest(unittest.TestCase):
    def test_registry_uses_json_extension_for_json_payload(self) -> None:
        with TemporaryDirectory() as temp:
            self.assertEqual(registry_path(Path(temp)).name, "registry.json")

    def test_normalize_remote_removes_protocol_suffix_and_credentials(self) -> None:
        self.assertEqual(
            normalize_remote("git@github.com:acme/widgets.git"),
            "github.com/acme/widgets",
        )
        self.assertEqual(
            normalize_remote("https://token@example.com/acme/widgets.git"),
            "example.com/acme/widgets",
        )

    def test_same_remote_reuses_one_knowledge_directory(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            (root / "01-projects").mkdir(parents=True)
            first = base / "first"
            second = base / "second"
            for repo in (first, second):
                repo.mkdir()
                subprocess.run(
                    ["git", "-C", str(repo), "init", "--quiet"],
                    check=True,
                )
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(repo),
                        "remote",
                        "add",
                        "origin",
                        "git@github.com:acme/widgets.git",
                    ],
                    check=True,
                )

            first_record = ensure_project(root, first)
            second_record = ensure_project(root, second)

            self.assertEqual(first_record.identity, "github.com/acme/widgets")
            self.assertEqual(first_record.relative_path, second_record.relative_path)
            self.assertTrue((root / first_record.relative_path / "index.md").is_file())
            self.assertTrue(
                (root / first_record.relative_path / "project-status.md").is_file()
            )
            self.assertFalse((root / first_record.relative_path / "AGENTS.md").exists())

    def test_local_repository_without_remote_uses_stable_path_identity(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "knowledge"
            (root / "01-projects").mkdir(parents=True)
            repo = Path(temp) / "local-only"
            (repo / ".git").mkdir(parents=True)

            first = ensure_project(root, repo)
            second = ensure_project(root, repo)

            self.assertTrue(first.identity.startswith("local/"))
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
