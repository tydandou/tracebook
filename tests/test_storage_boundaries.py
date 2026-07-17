import errno
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.errors import TracebookError
from plugins.tracebook.skills.tracebook.scripts import knowledge_root
from plugins.tracebook.skills.tracebook.scripts.storage import confined_path
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import resolve


class StorageBoundaryTest(unittest.TestCase):
    def test_external_root_is_resolved_for_allowed_sibling_and_parent(self) -> None:
        for relationship in ("sibling", "parent"):
            with self.subTest(relationship=relationship), TemporaryDirectory() as temp:
                base = Path(temp)
                repository = base / "business"
                (repository / ".git").mkdir(parents=True)
                root = base / "knowledge" if relationship == "sibling" else base

                resolved_root, resolved_repository = (
                    knowledge_root.validate_external_root(root, repository)
                )

                self.assertEqual(root.resolve(), resolved_root)
                self.assertEqual(repository.resolve(), resolved_repository)

                context = resolve(root, repository)
                self.assertEqual(root.resolve(), context.root)
                self.assertTrue((root / "registry.json").is_file())
                self.assertFalse((repository / "AGENTS.md").exists())

    def test_resolve_rejects_root_equal_to_or_below_repository_before_write(
        self,
    ) -> None:
        for relationship in ("equal", "descendant"):
            with self.subTest(relationship=relationship), TemporaryDirectory() as temp:
                repository = Path(temp) / "business"
                (repository / ".git").mkdir(parents=True)
                root = (
                    repository
                    if relationship == "equal"
                    else repository / "knowledge"
                )

                with self.assertRaises(TracebookError) as raised:
                    resolve(root, repository)

                self.assertEqual("ROOT_INSIDE_REPOSITORY", raised.exception.code)
                self.assertEqual("resolve", raised.exception.operation)
                self.assertFalse(raised.exception.retryable)
                self.assertFalse((repository / ".tracebook-state").exists())
                self.assertFalse((repository / "AGENTS.md").exists())
                if relationship == "descendant":
                    self.assertFalse(root.exists())

    def test_confined_path_resolves_path_within_root(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "knowledge"
            root.mkdir()
            path = root / "projects" / "widgets.md"

            self.assertEqual(
                path.resolve(),
                confined_path(root, path, operation="check"),
            )

    def test_confined_path_rejects_parent_escape(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "knowledge"
            root.mkdir()
            path = root / ".." / "outside.md"

            with self.assertRaises(TracebookError) as raised:
                confined_path(root, path, operation="capture")

            self.assertEqual("PATH_OUTSIDE_ROOT", raised.exception.code)
            self.assertEqual("capture", raised.exception.operation)
            self.assertFalse(raised.exception.retryable)

    def test_confined_path_rejects_symlink_escape(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            link = root / "linked-outside"
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

            with self.assertRaises(TracebookError) as raised:
                confined_path(root, link / "evidence.md", operation="check")

            self.assertEqual("PATH_OUTSIDE_ROOT", raised.exception.code)
            self.assertEqual("check", raised.exception.operation)


if __name__ == "__main__":
    unittest.main()
