from __future__ import annotations

from contextlib import contextmanager
import errno
import os
from pathlib import Path
import re
import stat
import time
from typing import Iterator

from .errors import LockTimeoutError, TracebookError

if os.name == "nt":
    import msvcrt

    _LOCK_CONTENTION_ERRNOS = {errno.EACCES}
else:
    import fcntl

    _LOCK_CONTENTION_ERRNOS = {errno.EACCES, errno.EAGAIN}


_LOCK_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")


def _invalid_lock_state(path: Path, operation: str, reason: str) -> TracebookError:
    return TracebookError(
        "INVALID_LOCK_STATE",
        f"Invalid lock state at {path}: {reason}",
        operation,
    )


def _is_reparse_point(path_stat: os.stat_result) -> bool:
    attributes = getattr(path_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _validate_directory(path: Path, *, operation: str) -> bool:
    path_stat = _lstat(path)
    if path_stat is None:
        return False
    if stat.S_ISLNK(path_stat.st_mode) or _is_reparse_point(path_stat):
        raise _invalid_lock_state(path, operation, "reparse points are not allowed")
    if not stat.S_ISDIR(path_stat.st_mode):
        raise _invalid_lock_state(path, operation, "expected a directory")
    return True


def _ensure_directory(path: Path, *, operation: str) -> None:
    if _validate_directory(path, operation=operation):
        return
    try:
        path.mkdir()
    except FileExistsError:
        pass
    if not _validate_directory(path, operation=operation):
        raise _invalid_lock_state(path, operation, "directory creation did not persist")


def _validate_lock_file(
    path: Path,
    *,
    operation: str,
) -> os.stat_result | None:
    path_stat = _lstat(path)
    if path_stat is None:
        return None
    if stat.S_ISLNK(path_stat.st_mode) or _is_reparse_point(path_stat):
        raise _invalid_lock_state(path, operation, "reparse points are not allowed")
    if not stat.S_ISREG(path_stat.st_mode):
        raise _invalid_lock_state(path, operation, "expected a regular file")
    return path_stat


def _open_lock_file(path: Path, *, operation: str) -> object:
    _validate_lock_file(path, operation=operation)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o666)
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.EISDIR}:
            raise _invalid_lock_state(
                path,
                operation,
                "path changed while opening the lock file",
            ) from None
        raise

    try:
        opened_stat = os.fstat(descriptor)
        path_stat = _validate_lock_file(path, operation=operation)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or path_stat is None
            or not os.path.samestat(opened_stat, path_stat)
        ):
            raise _invalid_lock_state(
                path,
                operation,
                "opened handle is not the confined regular lock file",
            )
        handle = os.fdopen(descriptor, "a+b")
    except BaseException:
        os.close(descriptor)
        raise
    return handle


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

    resolved_root = root.resolve()
    if not _validate_directory(resolved_root, operation=operation):
        resolved_root.mkdir(parents=True, exist_ok=True)
        if not _validate_directory(resolved_root, operation=operation):
            raise _invalid_lock_state(
                resolved_root,
                operation,
                "knowledge root creation did not persist",
            )
    state_dir = resolved_root / ".tracebook-state"
    _ensure_directory(state_dir, operation=operation)
    locks_dir = state_dir / "locks"
    _ensure_directory(locks_dir, operation=operation)
    lock_path = locks_dir / f"{name}.lock"
    deadline = time.monotonic() + timeout

    with _open_lock_file(lock_path, operation=operation) as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()

        while True:
            try:
                _acquire(handle)
                break
            except OSError as error:
                if error.errno not in _LOCK_CONTENTION_ERRNOS:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LockTimeoutError(name, timeout, operation) from None
                time.sleep(min(poll_interval, remaining))

        try:
            yield
        finally:
            _release(handle)
