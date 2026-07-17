from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any
import uuid

from .errors import TracebookError
from .locking import file_lock
from .storage import (
    atomic_write_bytes,
    atomic_write_text,
    confined_path,
    sha256_bytes,
    sha256_file,
)


_MANIFEST_NAME = "manifest.json"
_MANIFEST_KEYS = {
    "version",
    "transaction_id",
    "operation",
    "scope",
    "state",
    "created_at",
    "updates",
}
_UPDATE_KEYS = {"target", "staged", "original_hash", "staged_hash"}
_LOCK_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _failure(operation: str, message: str) -> TracebookError:
    return TracebookError(
        "TRANSACTION_RECOVERY_FAILED",
        message,
        operation,
    )


def _transactions_directory(root: Path, *, operation: str) -> Path:
    return confined_path(
        root,
        root / ".tracebook-state" / "transactions",
        operation=operation,
    )


def _transaction_directory(
    transactions_dir: Path,
    transaction_id: str,
    *,
    operation: str,
) -> Path:
    candidate = confined_path(
        transactions_dir,
        transactions_dir / transaction_id,
        operation=operation,
    )
    resolved_transactions = transactions_dir.resolve()
    if candidate.parent != resolved_transactions or candidate.name != transaction_id:
        raise TracebookError(
            "PATH_OUTSIDE_ROOT",
            f"Transaction path {candidate} is not a direct child of {resolved_transactions}",
            operation,
        )
    return candidate


def _manifest_text(manifest: Mapping[str, object]) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def _read_manifest(transaction_dir: Path) -> dict[str, Any]:
    manifest_path = transaction_dir / _MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise _failure(
            "recover",
            f"Invalid transaction manifest {manifest_path}: {error.msg}",
        ) from None

    operation = (
        manifest.get("operation", "recover")
        if isinstance(manifest, dict)
        else "recover"
    )
    if not isinstance(operation, str) or not operation:
        operation = "recover"
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
        raise _failure(operation, f"Invalid transaction manifest {manifest_path}")
    if manifest["version"] != 1:
        raise _failure(operation, f"Unsupported transaction manifest {manifest_path}")
    if not isinstance(manifest["transaction_id"], str) or not manifest["transaction_id"]:
        raise _failure(operation, f"Invalid transaction id in {manifest_path}")
    if not isinstance(manifest["operation"], str) or not manifest["operation"]:
        raise _failure(operation, f"Invalid operation in {manifest_path}")
    if (
        not isinstance(manifest["scope"], str)
        or _LOCK_NAME.fullmatch(manifest["scope"]) is None
    ):
        raise _failure(operation, f"Invalid lock scope in {manifest_path}")
    if manifest["state"] not in {"prepared", "committed"}:
        raise _failure(operation, f"Invalid transaction state in {manifest_path}")
    if not isinstance(manifest["created_at"], str) or not manifest["created_at"]:
        raise _failure(operation, f"Invalid creation timestamp in {manifest_path}")
    if not isinstance(manifest["updates"], list):
        raise _failure(operation, f"Invalid updates in {manifest_path}")
    return manifest


def _relative_path(
    base: Path,
    value: object,
    *,
    operation: str,
    field: str,
) -> Path:
    if not isinstance(value, str) or not value:
        raise _failure(operation, f"Invalid {field} path in transaction manifest")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != value:
        raise TracebookError(
            "PATH_OUTSIDE_ROOT",
            f"Manifest {field} path {value!r} is not a confined relative POSIX path",
            operation,
        )
    return confined_path(base, base.joinpath(*relative.parts), operation=operation)


def _validated_updates(
    root: Path,
    transaction_dir: Path,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    operation = manifest["operation"]
    validated: list[dict[str, Any]] = []
    seen_targets: set[Path] = set()
    for update in manifest["updates"]:
        if not isinstance(update, dict) or set(update) != _UPDATE_KEYS:
            raise _failure(operation, "Invalid update entry in transaction manifest")
        original_hash = update["original_hash"]
        staged_hash = update["staged_hash"]
        if original_hash is not None and (
            not isinstance(original_hash, str)
            or _SHA256.fullmatch(original_hash) is None
        ):
            raise _failure(operation, "Invalid original hash in transaction manifest")
        if not isinstance(staged_hash, str) or _SHA256.fullmatch(staged_hash) is None:
            raise _failure(operation, "Invalid staged hash in transaction manifest")

        target = _relative_path(
            root,
            update["target"],
            operation=operation,
            field="target",
        )
        staged_relative = PurePosixPath(update["staged"])
        if len(staged_relative.parts) < 2 or staged_relative.parts[0] != "staged":
            raise TracebookError(
                "PATH_OUTSIDE_ROOT",
                f"Manifest staged path {update['staged']!r} is outside staged directory",
                operation,
            )
        staged = _relative_path(
            transaction_dir,
            update["staged"],
            operation=operation,
            field="staged",
        )
        if target in seen_targets:
            raise _failure(operation, f"Duplicate transaction target {target}")
        seen_targets.add(target)
        validated.append(
            {
                "target": target,
                "staged": staged,
                "original_hash": original_hash,
                "staged_hash": staged_hash,
            }
        )
    return validated


def _sync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_target(target: Path, staged: Path, *, operation: str) -> None:
    del operation
    os.replace(staged, target)
    _sync_directory(target.parent)
    if staged.parent != target.parent:
        _sync_directory(staged.parent)


def _cleanup_transaction(root: Path, transaction_dir: Path, *, operation: str) -> None:
    transactions_dir = _transactions_directory(root, operation=operation)
    confined_transaction = _transaction_directory(
        transactions_dir,
        transaction_dir.name,
        operation=operation,
    )
    if confined_transaction != transaction_dir.resolve():
        raise TracebookError(
            "PATH_OUTSIDE_ROOT",
            f"Transaction path {transaction_dir} is not confined",
            operation,
        )
    manifest = _read_manifest(confined_transaction)
    if manifest["transaction_id"] != confined_transaction.name:
        raise _failure(operation, "Transaction directory does not match manifest id")
    if manifest["state"] != "committed":
        raise _failure(operation, "Refusing to clean an uncommitted transaction")
    _validated_updates(root, confined_transaction, manifest)
    shutil.rmtree(confined_transaction)


def commit_updates(
    root: Path,
    scope: str,
    operation: str,
    updates: Mapping[Path, str],
    *,
    transaction_id: str | None = None,
) -> tuple[Path, ...]:
    if not updates:
        return ()

    resolved_root = root.resolve()
    ordered: list[tuple[Path, str]] = []
    for target, content in updates.items():
        confined_target = confined_path(resolved_root, target, operation=operation)
        ordered.append((confined_target, content))
    ordered.sort(key=lambda item: item[0].relative_to(resolved_root).as_posix())

    transactions_dir = _transactions_directory(resolved_root, operation=operation)
    selected_id = transaction_id if transaction_id is not None else str(uuid.uuid4())
    transaction_dir = _transaction_directory(
        transactions_dir,
        selected_id,
        operation=operation,
    )
    staged_dir = transaction_dir / "staged"
    staged_dir.mkdir(parents=True, exist_ok=False)

    manifest_updates: list[dict[str, object]] = []
    for index, (target, content) in enumerate(ordered):
        staged = staged_dir / f"{index:08d}.stage"
        content_bytes = content.encode("utf-8")
        atomic_write_bytes(staged, content_bytes, operation=operation)
        manifest_updates.append(
            {
                "target": target.relative_to(resolved_root).as_posix(),
                "staged": staged.relative_to(transaction_dir).as_posix(),
                "original_hash": sha256_file(target),
                "staged_hash": sha256_bytes(content_bytes),
            }
        )

    manifest: dict[str, object] = {
        "version": 1,
        "transaction_id": selected_id,
        "operation": operation,
        "scope": scope,
        "state": "prepared",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "updates": manifest_updates,
    }
    manifest_path = transaction_dir / _MANIFEST_NAME
    atomic_write_text(manifest_path, _manifest_text(manifest), operation=operation)

    for update, (target, _) in zip(manifest_updates, ordered):
        _replace_target(
            target,
            transaction_dir.joinpath(*PurePosixPath(update["staged"]).parts),
            operation=operation,
        )

    manifest["state"] = "committed"
    atomic_write_text(manifest_path, _manifest_text(manifest), operation=operation)
    _cleanup_transaction(resolved_root, transaction_dir, operation=operation)
    return tuple(target for target, _ in ordered)


def recover_transactions(root: Path) -> tuple[Path, ...]:
    resolved_root = root.resolve()
    recovered: list[Path] = []
    with file_lock(resolved_root, "maintenance", operation="recover"):
        transactions_dir = _transactions_directory(resolved_root, operation="recover")
        if not transactions_dir.exists():
            return ()

        transaction_dirs = sorted(
            (
                path
                for path in transactions_dir.iterdir()
                if path.is_dir() and (path / _MANIFEST_NAME).is_file()
            ),
            key=lambda path: path.name,
        )
        for discovered_dir in transaction_dirs:
            transaction_dir = _transaction_directory(
                transactions_dir,
                discovered_dir.name,
                operation="recover",
            )
            initial_manifest = _read_manifest(transaction_dir)
            initial_scope = initial_manifest["scope"]
            with file_lock(resolved_root, initial_scope, operation="recover"):
                manifest_path = transaction_dir / _MANIFEST_NAME
                if not manifest_path.exists():
                    continue
                manifest = _read_manifest(transaction_dir)
                operation = manifest["operation"]
                if manifest["scope"] != initial_scope:
                    raise _failure(operation, "Transaction scope changed while waiting")
                if manifest["transaction_id"] != transaction_dir.name:
                    raise _failure(operation, "Transaction directory does not match manifest id")
                validated = _validated_updates(resolved_root, transaction_dir, manifest)

                if manifest["state"] == "committed":
                    _cleanup_transaction(
                        resolved_root,
                        transaction_dir,
                        operation=operation,
                    )
                    continue

                replacement_plan: list[dict[str, Any]] = []
                for update in validated:
                    current_hash = sha256_file(update["target"])
                    if current_hash not in {
                        update["original_hash"],
                        update["staged_hash"],
                    }:
                        raise _failure(
                            operation,
                            f"Target changed after preparation: {update['target']}",
                        )
                    staged_hash = sha256_file(update["staged"])
                    if staged_hash is None:
                        if current_hash != update["staged_hash"]:
                            raise _failure(
                                operation,
                                f"Staged file is missing for incomplete target: {update['target']}",
                            )
                    elif staged_hash != update["staged_hash"]:
                        raise _failure(
                            operation,
                            f"Staged file changed after preparation: {update['staged']}",
                        )
                    replacement_plan.append(
                        {**update, "staged_is_present": staged_hash is not None}
                    )

                for update in replacement_plan:
                    if update["staged_is_present"]:
                        _replace_target(
                            update["target"],
                            update["staged"],
                            operation=operation,
                        )

                manifest["state"] = "committed"
                atomic_write_text(
                    manifest_path,
                    _manifest_text(manifest),
                    operation=operation,
                )
                _cleanup_transaction(
                    resolved_root,
                    transaction_dir,
                    operation=operation,
                )
                recovered.extend(update["target"] for update in validated)
    return tuple(recovered)
