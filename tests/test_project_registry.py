import errno
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.errors import TracebookError
from plugins.tracebook.skills.tracebook.scripts.project_registry import (
    bind_remote,
    ensure_project,
    normalize_remote,
    project_config_path,
    registry_path,
    update_project,
)


class ProjectRegistryTest(unittest.TestCase):
    def _root(self, base: Path) -> Path:
        root = base / "knowledge"
        (root / "01-projects").mkdir(parents=True)
        return root

    def _local_project(self, base: Path, name: str = "project") -> Path:
        path = base / name
        path.mkdir()
        return path

    def _git_project(self, base: Path, name: str, remote: str | None = None) -> Path:
        path = self._local_project(base, name)
        subprocess.run(["git", "-C", str(path), "init", "--quiet"], check=True)
        if remote:
            subprocess.run(
                ["git", "-C", str(path), "remote", "add", "origin", remote],
                check=True,
            )
        return path

    def _symlink_or_skip(self, link: Path, target: Path, *, target_is_directory: bool = False) -> None:
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
            if error.errno in unavailable_errnos or getattr(error, "winerror", None) == 1314:
                self.skipTest(f"platform denied test symlink creation: {error}")
            raise

    def test_normalize_remote_removes_protocol_suffix_and_credentials(self) -> None:
        self.assertEqual(normalize_remote("git@github.com:acme/widgets.git"), "github.com/acme/widgets")
        self.assertEqual(normalize_remote("https://token@example.com/acme/widgets.git"), "example.com/acme/widgets")

    def test_non_git_directory_creates_a_stable_project_id_and_config(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = self._root(base)
            project = self._local_project(base, "inittest")

            first = ensure_project(root, project)
            second = ensure_project(root, project)

            self.assertEqual(first, second)
            self.assertRegex(first.project_id, r"^prj-[0-9a-f]{32}$")
            self.assertEqual("inittest", first.name)
            self.assertRegex(first.relative_path, r"^01-projects/inittest--[0-9a-f]{8}$")
            self.assertEqual((str(project.resolve()),), first.locations)
            self.assertEqual((), first.remotes)
            self.assertTrue(project_config_path(root, first).is_file())
            self.assertTrue((root / first.relative_path / "index.md").is_file())

            projects_index = (root / "01-projects" / "index.md").read_text(encoding="utf-8")
            self.assertIn(f"[inittest]({first.slug}/index.md)", projects_index)

    def test_same_remote_reuses_one_project_id_and_tracks_multiple_locations(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = self._root(base)
            remote = "git@github.com:acme/widgets.git"
            first_path = self._git_project(base, "first", remote)
            second_path = self._git_project(base, "second", remote)

            first = ensure_project(root, first_path)
            second = ensure_project(root, second_path)

            self.assertEqual(first.project_id, second.project_id)
            self.assertEqual(first.relative_path, second.relative_path)
            self.assertEqual("github.com/acme/widgets", second.remotes[0])
            self.assertEqual({str(first_path.resolve()), str(second_path.resolve())}, set(second.locations))

    def test_same_name_without_a_shared_signal_creates_distinct_projects(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = self._root(base)
            first_parent = base / "first"
            second_parent = base / "second"
            first_parent.mkdir()
            second_parent.mkdir()
            first = ensure_project(root, self._local_project(first_parent, "testproject"))
            second = ensure_project(root, self._local_project(second_parent, "testproject"))

            self.assertEqual("testproject", first.name)
            self.assertEqual("testproject", second.name)
            self.assertNotEqual(first.project_id, second.project_id)
            self.assertNotEqual(first.relative_path, second.relative_path)
            self.assertTrue(first.slug.startswith("testproject--"))
            self.assertTrue(second.slug.startswith("testproject--"))

    def test_display_name_is_visible_in_navigation_and_can_change_without_moving_knowledge(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = self._root(base)
            record = ensure_project(root, self._local_project(base, "initial"))
            original_path = record.relative_path

            updated = update_project(root, record.project_id, name="支付平台")

            self.assertEqual(original_path, updated.relative_path)
            self.assertEqual("支付平台", updated.name)
            self.assertTrue(updated.slug.startswith("initial--"))
            self.assertTrue(
                (root / updated.relative_path / "index.md")
                .read_text(encoding="utf-8")
                .startswith("# 支付平台\n")
            )
            projects_index = (root / "01-projects" / "index.md").read_text(encoding="utf-8")
            self.assertIn(f"[支付平台]({updated.slug}/index.md)", projects_index)

    def test_non_latin_project_name_is_preserved_in_the_readable_storage_label(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = self._root(base)
            record = ensure_project(root, self._local_project(base, "支付服务"))

            self.assertRegex(record.relative_path, r"^01-projects/支付服务--[0-9a-f]{8}$")

    def test_explicit_location_update_preserves_project_id_and_knowledge_directory(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = self._root(base)
            old_path = self._local_project(base, "old")
            record = ensure_project(root, old_path)
            new_path = base / "new"

            updated = update_project(root, record.project_id, locations=(str(new_path),))

            self.assertEqual(record.project_id, updated.project_id)
            self.assertEqual(record.relative_path, updated.relative_path)
            self.assertEqual((str(new_path.resolve()),), updated.locations)
            self.assertTrue((root / record.relative_path / "index.md").is_file())

    def test_explicit_remote_binding_connects_a_later_clone(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = self._root(base)
            first_path = self._local_project(base, "first")
            first = ensure_project(root, first_path)
            bound = bind_remote(root, first.project_id, "git@github.com:acme/widgets.git")
            second_path = self._git_project(base, "second", "https://github.com/acme/widgets.git")

            resolved = ensure_project(root, second_path)

            self.assertEqual(first.project_id, bound.project_id)
            self.assertEqual(first.project_id, resolved.project_id)
            self.assertIn(str(second_path.resolve()), resolved.locations)

    def test_conflicting_location_and_remote_are_rejected_without_changes(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = self._root(base)
            first = ensure_project(root, self._local_project(base, "first"))
            bind_remote(root, first.project_id, "github.com/acme/widgets")
            second_path = self._git_project(base, "second", "github.com/acme/widgets")
            second = ensure_project(root, second_path)
            self.assertEqual(first.project_id, second.project_id)

            other_path = self._local_project(base, "other")
            other = ensure_project(root, other_path)
            subprocess.run(["git", "-C", str(other_path), "init", "--quiet"], check=True)
            subprocess.run(["git", "-C", str(other_path), "remote", "add", "origin", "github.com/acme/widgets"], check=True)
            before = registry_path(root).read_bytes()
            with self.assertRaises(TracebookError) as raised:
                ensure_project(root, other_path)

            self.assertEqual("PROJECT_IDENTITY_CONFLICT", raised.exception.code)
            self.assertEqual(before, registry_path(root).read_bytes())
            self.assertNotEqual(first.project_id, other.project_id)

    def test_v1_registry_requires_an_explicit_upgrade(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = self._root(base)
            original = b'{"version": 1, "projects": {}}\n'
            registry_path(root).write_bytes(original)

            with self.assertRaises(TracebookError) as raised:
                ensure_project(root, self._local_project(base))

            self.assertEqual("REGISTRY_UPGRADE_REQUIRED", raised.exception.code)
            self.assertEqual(original, registry_path(root).read_bytes())

    def test_invalid_project_config_is_rejected_without_replacement(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = self._root(base)
            record = ensure_project(root, self._local_project(base))
            path = project_config_path(root, record)
            original = b'{"version": 1}\n'
            path.write_bytes(original)

            with self.assertRaises(TracebookError) as raised:
                ensure_project(root, Path(record.locations[0]))

            self.assertEqual("CORRUPT_REGISTRY", raised.exception.code)
            self.assertEqual(original, path.read_bytes())

    def test_project_minimum_files_reject_directory_entries(self) -> None:
        for filename in ("index.md", "project-status.md"):
            with self.subTest(filename=filename), TemporaryDirectory() as temp:
                base = Path(temp)
                root = self._root(base)
                record = ensure_project(root, self._local_project(base))
                entry = root / record.relative_path / filename
                entry.unlink()
                entry.mkdir()

                with self.assertRaises(TracebookError) as raised:
                    ensure_project(root, Path(record.locations[0]))

                self.assertEqual("INVALID_PROJECT_STATE", raised.exception.code)

    def test_project_minimum_files_reject_external_symlinks_without_overwrite(self) -> None:
        for filename in ("index.md", "project-status.md"):
            with self.subTest(filename=filename), TemporaryDirectory() as temp:
                base = Path(temp)
                root = self._root(base)
                record = ensure_project(root, self._local_project(base))
                entry = root / record.relative_path / filename
                entry.unlink()
                outside = base / f"outside-{filename}"
                original = b"outside content must remain unchanged\r\n"
                outside.write_bytes(original)
                self._symlink_or_skip(entry, outside)

                with self.assertRaises(TracebookError) as raised:
                    ensure_project(root, Path(record.locations[0]))

                self.assertEqual("INVALID_PROJECT_STATE", raised.exception.code)
                self.assertEqual(original, outside.read_bytes())


if __name__ == "__main__":
    unittest.main()
