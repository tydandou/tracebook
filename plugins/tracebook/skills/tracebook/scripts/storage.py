from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

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

        os.replace(temporary_path, path)
        temporary_path = None

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
