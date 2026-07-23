"""Immutable project knowledge snapshots for lock-free context reads."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Mapping
from uuid import uuid4

from .errors import TracebookError
from .locking import file_lock
from .project_registry import ProjectRecord, project_lock_name
from .storage import confined_path
from .transaction import commit_updates


_SNAPSHOT_ID = re.compile(r"[0-9a-f]{32}")


def _error(code: str, message: str, operation: str) -> TracebookError:
    return TracebookError(code, message, operation)


def _base(root: Path, record: ProjectRecord) -> Path:
    return root.resolve() / ".tracebook-state" / "snapshots" / record.project_id


def pointer_path(root: Path, record: ProjectRecord) -> Path:
    return _base(root, record) / "current.json"


def _version_root(root: Path, record: ProjectRecord, snapshot_id: str) -> Path:
    return _base(root, record) / "versions" / snapshot_id


def _pointer(root: Path, record: ProjectRecord, snapshot_id: str) -> str:
    return json.dumps(
        {
            "version": 1,
            "project_id": record.project_id,
            "snapshot_id": snapshot_id,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        sort_keys=True,
    ) + "\n"


def _pointer_snapshot_id(root: Path, record: ProjectRecord, *, operation: str) -> str | None:
    path = pointer_path(root, record)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise _error("INVALID_SNAPSHOT_POINTER", f"Invalid snapshot pointer at {path}: {error}", operation) from None
    snapshot_id = payload.get("snapshot_id") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or payload.get("project_id") != record.project_id
        or not isinstance(snapshot_id, str)
        or _SNAPSHOT_ID.fullmatch(snapshot_id) is None
    ):
        raise _error("INVALID_SNAPSHOT_POINTER", f"Invalid snapshot pointer at {path}", operation)
    return snapshot_id


def project_knowledge_root(root: Path, record: ProjectRecord, *, operation: str) -> tuple[Path, str]:
    """Return the immutable read tree, with an explicit legacy fallback."""
    resolved_root = root.resolve()
    snapshot_id = _pointer_snapshot_id(resolved_root, record, operation=operation)
    if snapshot_id is None:
        return resolved_root / record.relative_path / "knowledge", "legacy"
    directory = _version_root(resolved_root, record, snapshot_id) / "knowledge"
    if not directory.is_dir():
        raise _error(
            "INVALID_SNAPSHOT_POINTER",
            f"Snapshot {snapshot_id} for {record.project_id} is missing its knowledge tree",
            operation,
        )
    return directory, "snapshot"


def prepare_project_snapshot_updates(
    root: Path,
    record: ProjectRecord,
    updates: Mapping[Path, str],
    *,
    operation: str,
) -> tuple[dict[Path, str], Path]:
    """Build an immutable copy of the project's post-commit authority pages.

    The caller includes these updates in the same transaction as the materialized
    project files and makes the returned pointer target the final replacement.
    """
    resolved_root = root.resolve()
    legacy_knowledge = resolved_root / record.relative_path / "knowledge"
    replacement: dict[Path, str] = {}
    for target, content in updates.items():
        confined = confined_path(resolved_root, target, operation=operation)
        try:
            relative = confined.relative_to(legacy_knowledge)
        except ValueError:
            continue
        replacement[relative] = content

    source_files: dict[Path, str] = {}
    if legacy_knowledge.is_dir():
        for source in sorted(legacy_knowledge.rglob("*.md"), key=lambda path: path.as_posix()):
            relative = source.relative_to(legacy_knowledge)
            source_files[relative] = replacement.pop(relative, source.read_text(encoding="utf-8"))
    source_files.update(replacement)

    snapshot_id = uuid4().hex
    snapshot_knowledge = _version_root(resolved_root, record, snapshot_id) / "knowledge"
    snapshot_knowledge.mkdir(parents=True, exist_ok=True)
    snapshot_updates: dict[Path, str] = {}
    for relative, content in source_files.items():
        target = snapshot_knowledge / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        snapshot_updates[target] = content

    pointer = pointer_path(resolved_root, record)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    snapshot_updates[pointer] = _pointer(resolved_root, record, snapshot_id)
    return snapshot_updates, pointer


def has_snapshot(root: Path, record: ProjectRecord) -> bool:
    return _pointer_snapshot_id(root.resolve(), record, operation="snapshot") is not None


def ensure_project_snapshot(root: Path, record: ProjectRecord) -> tuple[Path, ...]:
    """Seed a legacy project's first snapshot under its project-level lock."""
    resolved_root = root.resolve()
    with file_lock(resolved_root, project_lock_name(record), operation="snapshot-seed"):
        if has_snapshot(resolved_root, record):
            return ()
        updates, pointer = prepare_project_snapshot_updates(
            resolved_root,
            record,
            {},
            operation="snapshot-seed",
        )
        return commit_updates(
            resolved_root,
            project_lock_name(record),
            "snapshot-seed",
            updates,
            final_targets=(pointer,),
        )
