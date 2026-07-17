import errno
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts.errors import (
    LockTimeoutError,
    TracebookError,
    error_payload,
)
from plugins.tracebook.skills.tracebook.scripts.locking import file_lock


def _symlink_or_skip(
    test: unittest.TestCase,
    link: Path,
    target: Path,
    *,
    target_is_directory: bool,
) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except NotImplementedError as error:
        test.skipTest(f"platform denied test symlink creation: {error}")
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
            test.skipTest(f"platform denied test symlink creation: {error}")
        raise


class LockingTest(unittest.TestCase):
    def test_error_payload_is_stable(self) -> None:
        error = LockTimeoutError("project-widgets", 0.1, "capture")
        self.assertEqual(
            {
                "ok": False,
                "error": {
                    "code": "LOCK_TIMEOUT",
                    "message": "Timed out after 0.1s waiting for lock project-widgets",
                    "operation": "capture",
                    "retryable": True,
                },
            },
            error_payload(error),
        )

    def test_second_process_times_out_and_lock_is_reusable(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            helper = (
                "from pathlib import Path\n"
                "import sys,time\n"
                "from plugins.tracebook.skills.tracebook.scripts.locking import file_lock\n"
                "with file_lock(Path(sys.argv[1]), 'project-widgets'):\n"
                "    print('locked', flush=True)\n"
                "    time.sleep(1.0)\n"
            )
            holder = subprocess.Popen(
                [sys.executable, "-c", helper, str(root)],
                cwd=Path(__file__).resolve().parents[1],
                stdout=subprocess.PIPE,
                text=True,
            )
            self.assertEqual("locked", holder.stdout.readline().strip())
            started = time.monotonic()
            with self.assertRaises(LockTimeoutError):
                with file_lock(
                    root,
                    "project-widgets",
                    timeout=0.1,
                    operation="capture",
                ):
                    pass
            self.assertGreaterEqual(time.monotonic() - started, 0.1)
            holder.wait(timeout=5)
            holder.stdout.close()
            with file_lock(root, "project-widgets", timeout=0.5):
                pass

    def test_non_contention_os_error_is_propagated(self) -> None:
        failure = OSError(errno.EIO, "simulated I/O failure")
        with TemporaryDirectory() as temp:
            with patch(
                "plugins.tracebook.skills.tracebook.scripts.locking._acquire",
                side_effect=failure,
            ):
                with self.assertRaises(Exception) as raised:
                    with file_lock(Path(temp), "project-widgets", timeout=0):
                        pass

        self.assertIs(failure, raised.exception)

    def test_directory_at_lock_path_is_rejected_without_modification(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            lock_path = (
                root / ".tracebook-state" / "locks" / "project-widgets.lock"
            )
            lock_path.mkdir(parents=True)

            with self.assertRaises(TracebookError) as raised:
                with file_lock(root, "project-widgets", operation="capture"):
                    pass

            self.assertEqual("INVALID_LOCK_STATE", raised.exception.code)
            self.assertFalse(raised.exception.retryable)
            self.assertTrue(lock_path.is_dir())
            self.assertEqual([], list(lock_path.iterdir()))

    def test_non_directory_lock_parents_are_rejected_without_modification(self) -> None:
        for component in ("state", "locks"):
            with self.subTest(component=component), TemporaryDirectory() as temp:
                root = Path(temp)
                state_dir = root / ".tracebook-state"
                invalid_path = state_dir
                if component == "locks":
                    state_dir.mkdir()
                    invalid_path = state_dir / "locks"
                invalid_path.write_bytes(b"invalid parent\n")

                with self.assertRaises(TracebookError) as raised:
                    with file_lock(root, "project-widgets", operation="capture"):
                        pass

                self.assertEqual("INVALID_LOCK_STATE", raised.exception.code)
                self.assertFalse(raised.exception.retryable)
                self.assertEqual(b"invalid parent\n", invalid_path.read_bytes())

    def test_state_directory_symlink_escape_is_rejected_before_outside_write(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            temporary_root = Path(temp)
            root = temporary_root / "root"
            outside = temporary_root / "outside"
            root.mkdir()
            outside.mkdir()
            sentinel = outside / "sentinel"
            sentinel.write_bytes(b"unchanged\n")
            _symlink_or_skip(
                self,
                root / ".tracebook-state",
                outside,
                target_is_directory=True,
            )

            with self.assertRaises(TracebookError) as raised:
                with file_lock(root, "project-widgets", operation="capture"):
                    pass

            self.assertEqual("INVALID_LOCK_STATE", raised.exception.code)
            self.assertFalse(raised.exception.retryable)
            self.assertEqual(b"unchanged\n", sentinel.read_bytes())
            self.assertFalse((outside / "locks").exists())

    def test_locks_directory_symlink_escape_is_rejected_before_outside_write(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            temporary_root = Path(temp)
            root = temporary_root / "root"
            state_dir = root / ".tracebook-state"
            outside = temporary_root / "outside"
            state_dir.mkdir(parents=True)
            outside.mkdir()
            sentinel = outside / "sentinel"
            sentinel.write_bytes(b"unchanged\n")
            _symlink_or_skip(
                self,
                state_dir / "locks",
                outside,
                target_is_directory=True,
            )

            with self.assertRaises(TracebookError) as raised:
                with file_lock(root, "project-widgets", operation="capture"):
                    pass

            self.assertEqual("INVALID_LOCK_STATE", raised.exception.code)
            self.assertFalse(raised.exception.retryable)
            self.assertEqual(b"unchanged\n", sentinel.read_bytes())
            self.assertFalse((outside / "project-widgets.lock").exists())

    def test_lock_file_symlink_escape_is_rejected_without_changing_target(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            temporary_root = Path(temp)
            root = temporary_root / "root"
            locks_dir = root / ".tracebook-state" / "locks"
            locks_dir.mkdir(parents=True)
            outside_file = temporary_root / "outside.lock"
            outside_file.write_bytes(b"unchanged\n")
            _symlink_or_skip(
                self,
                locks_dir / "project-widgets.lock",
                outside_file,
                target_is_directory=False,
            )

            with self.assertRaises(TracebookError) as raised:
                with file_lock(root, "project-widgets", operation="capture"):
                    pass

            self.assertEqual("INVALID_LOCK_STATE", raised.exception.code)
            self.assertFalse(raised.exception.retryable)
            self.assertEqual(b"unchanged\n", outside_file.read_bytes())

    def test_concurrent_first_locks_share_directory_creation(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            worker_count = 8
            ready = threading.Barrier(worker_count)

            def acquire(index: int) -> None:
                ready.wait(timeout=5)
                with file_lock(root, f"worker-{index}", timeout=1):
                    pass

            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                list(executor.map(acquire, range(worker_count)))

            locks_dir = root / ".tracebook-state" / "locks"
            self.assertEqual(
                {f"worker-{index}.lock" for index in range(worker_count)},
                {path.name for path in locks_dir.iterdir()},
            )


if __name__ == "__main__":
    unittest.main()
