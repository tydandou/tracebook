import errno
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.errors import TracebookError
from plugins.tracebook.skills.tracebook.scripts.project_registry import ensure_project, normalize_remote, registry_path


class ProjectRegistryTest(unittest.TestCase):
    def _local_repository(self, base: Path, name: str = "repo") -> Path:
        repository = base / name
        (repository / ".git").mkdir(parents=True)
        return repository

    def _symlink_or_skip(
        self,
        link: Path,
        target: Path,
        *,
        target_is_directory: bool = False,
    ) -> None:
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
        except NotImplementedError as error:
            self.skipTest(f"platform denied test symlink creation: {error}")
        except OSError as error:
            unavailable_errnos = {errno.EACCES, errno.EPERM}
            for name in ("ENOTSUP", "EOPNOTSUPP"):
                value = getattr(errno, name, None)
                if value is not None:
                    unavailable_errnos.add(value)
            if (
                error.errno in unavailable_errnos
                or getattr(error, "winerror", None) == 1314
            ):
                self.skipTest(f"platform denied test symlink creation: {error}")
            raise

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

    def test_corrupt_registry_bytes_are_preserved(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            (root / "01-projects").mkdir(parents=True)
            repository = self._local_repository(base)
            path = registry_path(root)
            corrupt = b'{"version": 1, "projects":\xff'
            path.write_bytes(corrupt)

            with self.assertRaises(TracebookError) as raised:
                ensure_project(root, repository)

            self.assertEqual("CORRUPT_REGISTRY", raised.exception.code)
            self.assertEqual("resolve", raised.exception.operation)
            self.assertFalse(raised.exception.retryable)
            self.assertEqual(corrupt, path.read_bytes())
            self.assertEqual([], list((root / "01-projects").iterdir()))

    def test_registry_directory_is_reported_as_corrupt(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            (root / "01-projects").mkdir(parents=True)
            repository = self._local_repository(base)
            path = registry_path(root)
            path.mkdir()

            with self.assertRaises(TracebookError) as raised:
                ensure_project(root, repository)

            self.assertEqual("CORRUPT_REGISTRY", raised.exception.code)
            self.assertEqual("resolve", raised.exception.operation)
            self.assertTrue(path.is_dir())
            self.assertEqual([], list((root / "01-projects").iterdir()))

    def test_dangling_registry_symlink_is_reported_as_corrupt_without_replacement(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            (root / "01-projects").mkdir(parents=True)
            repository = self._local_repository(base)
            path = registry_path(root)
            outside = base / "missing-registry-target.json"
            self._symlink_or_skip(path, outside)

            with self.assertRaises(TracebookError) as raised:
                ensure_project(root, repository)

            self.assertEqual("CORRUPT_REGISTRY", raised.exception.code)
            self.assertEqual("resolve", raised.exception.operation)
            self.assertTrue(path.is_symlink())
            self.assertFalse(outside.exists())
            self.assertEqual([], list((root / "01-projects").iterdir()))

    def test_project_minimum_files_reject_directory_entries(self) -> None:
        for filename in ("index.md", "project-status.md"):
            with self.subTest(filename=filename), TemporaryDirectory() as temp:
                base = Path(temp)
                root = base / "knowledge"
                (root / "01-projects").mkdir(parents=True)
                repository = self._local_repository(base)
                record = ensure_project(root, repository)
                entry = root / record.relative_path / filename
                entry.unlink()
                entry.mkdir()

                with self.assertRaises(TracebookError) as raised:
                    ensure_project(root, repository)

                self.assertEqual("INVALID_PROJECT_STATE", raised.exception.code)
                self.assertEqual("resolve", raised.exception.operation)
                self.assertTrue(entry.is_dir())

    def test_project_minimum_files_reject_external_symlinks_without_overwrite(
        self,
    ) -> None:
        for filename in ("index.md", "project-status.md"):
            with self.subTest(filename=filename), TemporaryDirectory() as temp:
                base = Path(temp)
                root = base / "knowledge"
                (root / "01-projects").mkdir(parents=True)
                repository = self._local_repository(base)
                record = ensure_project(root, repository)
                entry = root / record.relative_path / filename
                entry.unlink()
                outside = base / f"outside-{filename}"
                original = b"outside content must remain unchanged\r\n"
                outside.write_bytes(original)
                self._symlink_or_skip(entry, outside)

                with self.assertRaises(TracebookError) as raised:
                    ensure_project(root, repository)

                self.assertEqual("INVALID_PROJECT_STATE", raised.exception.code)
                self.assertEqual("resolve", raised.exception.operation)
                self.assertTrue(entry.is_symlink())
                self.assertEqual(original, outside.read_bytes())

    def test_registry_schema_is_strict_for_version_projects_and_record_fields(
        self,
    ) -> None:
        invalid_payloads = (
            {"version": 2, "projects": {}},
            {"version": 1, "projects": []},
            {
                "version": 1,
                "projects": {
                    "local/example": {
                        "identity": "local/example",
                        "slug": 7,
                        "relative_path": "01-projects/example",
                    }
                },
            },
            {
                "version": 1,
                "projects": {
                    "local/example": {
                        "identity": "local/different",
                        "slug": "example",
                        "relative_path": "01-projects/example",
                    }
                },
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), TemporaryDirectory() as temp:
                base = Path(temp)
                root = base / "knowledge"
                (root / "01-projects").mkdir(parents=True)
                repository = self._local_repository(base)
                original = (json.dumps(payload) + "\n").encode("utf-8")
                path = registry_path(root)
                path.write_bytes(original)

                with self.assertRaises(TracebookError) as raised:
                    ensure_project(root, repository)

                self.assertEqual("CORRUPT_REGISTRY", raised.exception.code)
                self.assertEqual(original, path.read_bytes())

    def test_registry_relative_path_must_remain_under_projects_directory(
        self,
    ) -> None:
        for relative_path in ("../outside", "00-global/not-a-project"):
            with self.subTest(relative_path=relative_path), TemporaryDirectory() as temp:
                base = Path(temp)
                root = base / "knowledge"
                (root / "01-projects").mkdir(parents=True)
                repository = self._local_repository(base)
                identity = (
                    "local/"
                    + hashlib.sha256(
                        str(repository.resolve()).casefold().encode("utf-8")
                    ).hexdigest()[:12]
                )
                payload = {
                    "version": 1,
                    "projects": {
                        identity: {
                            "identity": identity,
                            "slug": "escaped",
                            "relative_path": relative_path,
                        }
                    },
                }
                path = registry_path(root)
                original = (json.dumps(payload) + "\n").encode("utf-8")
                path.write_bytes(original)

                with self.assertRaises(TracebookError) as raised:
                    ensure_project(root, repository)

                self.assertEqual("CORRUPT_REGISTRY", raised.exception.code)
                self.assertEqual(original, path.read_bytes())
                self.assertFalse((base / "outside").exists())

    def test_registry_relative_path_rejects_symlink_escape(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            projects = root / "01-projects"
            outside = base / "outside"
            projects.mkdir(parents=True)
            outside.mkdir()
            link = projects / "linked-outside"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except NotImplementedError as error:
                self.skipTest(f"platform denied test symlink creation: {error}")
            except OSError as error:
                unavailable_errnos = {errno.EACCES, errno.EPERM}
                for name in ("ENOTSUP", "EOPNOTSUPP"):
                    value = getattr(errno, name, None)
                    if value is not None:
                        unavailable_errnos.add(value)
                if (
                    error.errno in unavailable_errnos
                    or getattr(error, "winerror", None) == 1314
                ):
                    self.skipTest(f"platform denied test symlink creation: {error}")
                raise
            repository = self._local_repository(base)
            identity = (
                "local/"
                + hashlib.sha256(
                    str(repository.resolve()).casefold().encode("utf-8")
                ).hexdigest()[:12]
            )
            payload = {
                "version": 1,
                "projects": {
                    identity: {
                        "identity": identity,
                        "slug": "escaped",
                        "relative_path": "01-projects/linked-outside/escaped",
                    }
                },
            }
            path = registry_path(root)
            original = (json.dumps(payload) + "\n").encode("utf-8")
            path.write_bytes(original)

            with self.assertRaises(TracebookError) as raised:
                ensure_project(root, repository)

            self.assertEqual("CORRUPT_REGISTRY", raised.exception.code)
            self.assertEqual(original, path.read_bytes())
            self.assertEqual([], list(outside.iterdir()))


if __name__ == "__main__":
    unittest.main()
