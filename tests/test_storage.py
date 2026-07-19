from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts.storage import (
    atomic_write_bytes,
    atomic_write_text,
    sha256_bytes,
    sha256_file,
)


class StorageTest(unittest.TestCase):
    def test_sha256_bytes_returns_known_digest(self) -> None:
        self.assertEqual(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            sha256_bytes(b"abc"),
        )

    def test_sha256_file_hashes_bytes_and_missing_file_returns_none(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "knowledge.md"
            path.write_bytes(b"abc")

            self.assertEqual(sha256_bytes(b"abc"), sha256_file(path))
            self.assertIsNone(sha256_file(path.with_name("missing.md")))

    def test_atomic_write_replaces_complete_content(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "status.md"
            path.write_text("old", encoding="utf-8")

            atomic_write_text(path, "new\n", operation="check")

            self.assertEqual("new\n", path.read_text(encoding="utf-8"))
            self.assertEqual([], list(path.parent.glob(".status.md.*.tmp")))

    def test_atomic_write_bytes_preserves_exact_bytes(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "evidence.bin"
            content = b"\x00\xffnew\r\n"

            atomic_write_bytes(path, content, operation="capture")

            self.assertEqual(content, path.read_bytes())
            self.assertEqual([], list(path.parent.glob(".evidence.bin.*.tmp")))

    def test_atomic_write_removes_unconsumed_temp_file(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "status.md"
            failure = OSError("simulated replace failure")

            with patch(
                "plugins.tracebook.skills.tracebook.scripts.storage.os.replace",
                side_effect=failure,
            ):
                with self.assertRaises(OSError) as raised:
                    atomic_write_text(path, "new\n", operation="check")

            self.assertIs(failure, raised.exception)
            self.assertFalse(path.exists())
            self.assertEqual([], list(path.parent.glob(".status.md.*.tmp")))


if __name__ == "__main__":
    unittest.main()
