from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import time
from typing import Iterator

from .errors import LockTimeoutError

if os.name == "nt":
    import msvcrt
else:
    import fcntl


_LOCK_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")


def _acquire(handle: object) -> None:
    handle.seek(0)
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release(handle: object) -> None:
    handle.seek(0)
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def file_lock(
    root: Path,
    name: str,
    *,
    timeout: float = 10.0,
    poll_interval: float = 0.05,
    operation: str = "unknown",
) -> Iterator[None]:
    if _LOCK_NAME.fullmatch(name) is None:
        raise ValueError(f"Invalid lock name: {name}")

    locks_dir = root / ".tracebook-state" / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    lock_path = locks_dir / f"{name}.lock"
    deadline = time.monotonic() + timeout

    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()

        while True:
            try:
                _acquire(handle)
                break
            except OSError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LockTimeoutError(name, timeout, operation) from None
                time.sleep(min(poll_interval, remaining))

        try:
            yield
        finally:
            _release(handle)
