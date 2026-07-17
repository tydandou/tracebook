from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from plugins.tracebook.skills.tracebook.scripts.errors import (
    LockTimeoutError,
    error_payload,
)
from plugins.tracebook.skills.tracebook.scripts.locking import file_lock


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


if __name__ == "__main__":
    unittest.main()
