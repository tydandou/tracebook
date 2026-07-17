import errno
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.errors import TracebookError
from plugins.tracebook.skills.tracebook.scripts.storage import confined_path


class StorageBoundaryTest(unittest.TestCase):
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
