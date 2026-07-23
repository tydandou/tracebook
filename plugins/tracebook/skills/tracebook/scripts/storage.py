from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import time

from .errors import TracebookError


def confined_path(root: Path, path: Path, *, operation: str) -> Path:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        raise TracebookError(
            "PATH_OUTSIDE_ROOT",
            f"Path {resolved_path} is outside root {resolved_root}",
            operation,
        ) from None
    return resolved_path


def read_bytes_shared(path: Path) -> bytes:
    """Read a file while allowing a concurrent writer to os.replace it.

    On Windows the default open() omits FILE_SHARE_DELETE, so a reader blocks a
    writer's MoveFileEx-based os.replace with PermissionError. Opening with the
    full share mode lets snapshot pointer swaps proceed while readers hold a
    handle. On POSIX this behaviour is already the default.
    """
    if os.name != "nt":
        return path.read_bytes()
    import ctypes
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    GENERIC_READ = 0x80000000
    SHARE_ALL = 0x1 | 0x2 | 0x4  # READ | WRITE | DELETE
    OPEN_EXISTING = 3
    FLAG_BACKUP_SEMANTICS = 0x02000000
    ERROR_ACCESS_DENIED = 5
    ERROR_SHARING_VIOLATION = 32
    # A concurrent os.replace briefly puts the target in a delete-pending state;
    # a CreateFileW landing in that window returns ACCESS_DENIED even with full
    # share mode. Retry the transient window, mirroring the writer-side retry.
    last_error = 0
    for attempt in range(5):
        handle = kernel32.CreateFileW(
            str(path),
            GENERIC_READ,
            SHARE_ALL,
            None,
            OPEN_EXISTING,
            FLAG_BACKUP_SEMANTICS,
            None,
        )
        if handle != -1:
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                return stream.read()
        last_error = ctypes.get_last_error()
        if last_error not in (ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION) or attempt == 4:
            break
        time.sleep(0.02 * (attempt + 1))
    raise OSError(last_error, f"cannot open {path}")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except FileNotFoundError:
        return None
    return digest.hexdigest()


def atomic_write_bytes(path: Path, content: bytes, *, operation: str) -> None:
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path: Path | None = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        for attempt in range(5):
            try:
                os.replace(temporary_path, path)
                temporary_path = None
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))

        if os.name == "posix":
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def atomic_write_text(path: Path, content: str, *, operation: str) -> None:
    atomic_write_bytes(path, content.encode("utf-8"), operation=operation)
