from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import time
from typing import Any
import uuid

from .errors import TracebookError
from .locking import file_lock
from .storage import (
    atomic_write_bytes,
    atomic_write_text,
    confined_path,
    read_bytes_shared,
    sha256_bytes,
    sha256_file,
)


_MANIFEST_NAME = "manifest.json"
_INTENT_SUFFIX = ".json"
_MANIFEST_KEYS = {
    "version",
    "transaction_id",
    "operation",
    "scope",
    "state",
    "created_at",
    "updates",
}
_INTENT_KEYS = {"version", "transaction_id", "operation", "scope"}
_UPDATE_KEYS = {"target", "staged", "original_hash", "staged_hash"}
_LOCK_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_RESERVED_SCOPES = {"maintenance"}


@dataclass(frozen=True)
class TransactionIssue:
    code: str
    message: str
    target: Path | None = None


@dataclass(frozen=True)
class TransactionDiagnostic:
    transaction_id: str
    operation: str
    scope: str
    state: str
    disposition: str
    issues: tuple[TransactionIssue, ...] = ()


def _failure(operation: str, message: str) -> TracebookError:
    return TracebookError(
        "TRANSACTION_RECOVERY_FAILED",
        message,
        operation,
    )


def _validate_scope(
    scope: object,
    *,
    operation: str,
    manifest_path: Path | None = None,
) -> str:
    if (
        not isinstance(scope, str)
        or _LOCK_NAME.fullmatch(scope) is None
        or scope in _RESERVED_SCOPES
    ):
        location = f" in {manifest_path}" if manifest_path is not None else ""
        raise _failure(operation, f"Invalid transaction scope{location}")
    return scope


def _transactions_directory(root: Path, *, operation: str) -> Path:
    return confined_path(
        root,
        root / ".tracebook-state" / "transactions",
        operation=operation,
    )


def _transaction_intents_directory(root: Path, *, operation: str) -> Path:
    return confined_path(
        root,
        root / ".tracebook-state" / "transaction-intents",
        operation=operation,
    )


def _transaction_directory(
    transactions_dir: Path,
    transaction_id: str,
    *,
    operation: str,
) -> Path:
    resolved_transactions = transactions_dir.resolve()
    lexical_candidate = resolved_transactions / transaction_id
    if (
        lexical_candidate.parent != resolved_transactions
        or lexical_candidate.name != transaction_id
    ):
        raise TracebookError(
            "PATH_OUTSIDE_ROOT",
            f"Transaction path {lexical_candidate} is not a direct child of "
            f"{resolved_transactions}",
            operation,
        )
    try:
        candidate = confined_path(
            resolved_transactions,
            lexical_candidate,
            operation=operation,
        )
    except TracebookError:
        # On Windows, resolving a directory concurrently removed by its writer
        # can transiently produce a $Extend/$Deleted path. Once the lexical
        # child is gone there is nothing left for recovery to inspect or alter.
        if not lexical_candidate.exists():
            return lexical_candidate
        raise
    return candidate


def _intent_path(
    intents_dir: Path,
    transaction_id: str,
    *,
    operation: str,
) -> Path:
    filename = f"{transaction_id}{_INTENT_SUFFIX}"
    resolved_intents = intents_dir.resolve()
    lexical_candidate = resolved_intents / filename
    if lexical_candidate.parent != resolved_intents or lexical_candidate.name != filename:
        raise TracebookError(
            "PATH_OUTSIDE_ROOT",
            f"Transaction intent path {lexical_candidate} is not a direct child of "
            f"{resolved_intents}",
            operation,
        )
    try:
        candidate = confined_path(
            resolved_intents,
            lexical_candidate,
            operation=operation,
        )
    except TracebookError:
        if not lexical_candidate.exists():
            return lexical_candidate
        raise
    return candidate


def _manifest_text(manifest: Mapping[str, object]) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def _intent_text(intent: Mapping[str, object]) -> str:
    return json.dumps(intent, indent=2, sort_keys=True) + "\n"


def _read_intent(intent_path: Path) -> dict[str, Any]:
    try:
        intent = json.loads(read_bytes_shared(intent_path).decode("utf-8"))
    except json.JSONDecodeError as error:
        raise _failure(
            "recover",
            f"Invalid transaction intent {intent_path}: {error.msg}",
        ) from None

    operation = (
        intent.get("operation", "recover")
        if isinstance(intent, dict)
        else "recover"
    )
    if not isinstance(operation, str) or not operation:
        operation = "recover"
    if not isinstance(intent, dict) or set(intent) != _INTENT_KEYS:
        raise _failure(operation, f"Invalid transaction intent {intent_path}")
    if intent["version"] != 1:
        raise _failure(operation, f"Unsupported transaction intent {intent_path}")
    if not isinstance(intent["transaction_id"], str) or not intent["transaction_id"]:
        raise _failure(operation, f"Invalid transaction id in {intent_path}")
    if not isinstance(intent["operation"], str) or not intent["operation"]:
        raise _failure(operation, f"Invalid operation in {intent_path}")
    _validate_scope(
        intent["scope"],
        operation=operation,
        manifest_path=intent_path,
    )
    return intent


def _read_manifest(transaction_dir: Path) -> dict[str, Any]:
    manifest_path = transaction_dir / _MANIFEST_NAME
    try:
        manifest = json.loads(read_bytes_shared(manifest_path).decode("utf-8"))
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
    _validate_scope(
        manifest["scope"],
        operation=operation,
        manifest_path=manifest_path,
    )
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
    staged_root = transaction_dir / "staged"
    resolved_staged_root = staged_root.resolve()
    if staged_root.is_symlink() or resolved_staged_root != staged_root:
        raise TracebookError(
            "PATH_OUTSIDE_ROOT",
            f"Transaction staged directory {staged_root} is not confined",
            operation,
        )
    validated: list[dict[str, Any]] = []
    seen_targets: set[Path] = set()
    seen_staged: set[Path] = set()
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
        try:
            staged.relative_to(resolved_staged_root)
        except ValueError:
            raise TracebookError(
                "PATH_OUTSIDE_ROOT",
                f"Manifest staged path {update['staged']!r} is outside staged directory",
                operation,
            ) from None
        if target in seen_targets:
            raise _failure(operation, f"Duplicate transaction target {target}")
        if staged in seen_staged:
            raise _failure(operation, f"Duplicate transaction staged path {staged}")
        seen_targets.add(target)
        seen_staged.add(staged)
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
    for attempt in range(5):
        try:
            os.replace(staged, target)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))
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


def _cleanup_intent(intent_path: Path) -> None:
    try:
        intent_path.unlink()
    except FileNotFoundError:
        return
    _sync_directory(intent_path.parent)


def commit_updates(
    root: Path,
    scope: str,
    operation: str,
    updates: Mapping[Path, str],
    *,
    transaction_id: str | None = None,
    final_targets: Iterable[Path] = (),
) -> tuple[Path, ...]:
    if not updates:
        return ()

    _validate_scope(scope, operation=operation)
    resolved_root = root.resolve()
    ordered: list[tuple[Path, str]] = []
    seen_targets: set[Path] = set()
    for target, content in updates.items():
        confined_target = confined_path(resolved_root, target, operation=operation)
        if confined_target in seen_targets:
            raise _failure(operation, f"Duplicate transaction target {confined_target}")
        seen_targets.add(confined_target)
        ordered.append((confined_target, content))
    final_paths = {
        confined_path(resolved_root, target, operation=operation)
        for target in final_targets
    }
    if not final_paths <= seen_targets:
        raise _failure(operation, "Final transaction target is not part of updates")
    ordered.sort(
        key=lambda item: (
            item[0] in final_paths,
            item[0].relative_to(resolved_root).as_posix(),
        )
    )

    transactions_dir = _transactions_directory(resolved_root, operation=operation)
    intents_dir = _transaction_intents_directory(resolved_root, operation=operation)
    selected_id = transaction_id if transaction_id is not None else str(uuid.uuid4())
    transaction_dir = _transaction_directory(
        transactions_dir,
        selected_id,
        operation=operation,
    )
    intents_dir.mkdir(parents=True, exist_ok=True)
    intent_path = _intent_path(intents_dir, selected_id, operation=operation)
    if transaction_dir.exists() or intent_path.exists():
        raise _failure(operation, f"Transaction id already exists: {selected_id}")
    intent: dict[str, object] = {
        "version": 1,
        "transaction_id": selected_id,
        "operation": operation,
        "scope": scope,
    }
    # Publish ownership before the transaction directory becomes visible.
    # Production callers hold this scope lock (or maintenance for root layout),
    # so recovery can wait for an active writer before judging a manifestless
    # directory to be abandoned.
    atomic_write_text(intent_path, _intent_text(intent), operation=operation)
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
    _cleanup_intent(intent_path)
    return tuple(target for target, _ in ordered)


def _diagnose_transaction(
    root: Path,
    transactions_dir: Path,
    intents_dir: Path,
    discovered_dir: Path,
) -> TransactionDiagnostic | None:
    transaction_id = discovered_dir.name
    try:
        transaction_dir = _transaction_directory(
            transactions_dir,
            transaction_id,
            operation="inspect",
        )
        manifest = _read_manifest(transaction_dir)
        operation = manifest["operation"]
        scope = manifest["scope"]
        if manifest["transaction_id"] != transaction_id:
            return TransactionDiagnostic(
                transaction_id,
                operation,
                scope,
                manifest["state"],
                "invalid",
                (
                    TransactionIssue(
                        "TRANSACTION_ID_MISMATCH",
                        "Transaction directory does not match manifest id",
                    ),
                ),
            )
        validated = _validated_updates(root, transaction_dir, manifest)
    except FileNotFoundError:
        return _diagnose_staging(
            transactions_dir, intents_dir, transaction_id
        )
    except TracebookError as error:
        if not (discovered_dir / _MANIFEST_NAME).is_file():
            return _diagnose_staging(
                transactions_dir, intents_dir, transaction_id
            )
        return TransactionDiagnostic(
            transaction_id,
            error.operation,
            "unknown",
            "unknown",
            "invalid",
            (TransactionIssue(error.code, error.message),),
        )
    except OSError as error:
        if not (discovered_dir / _MANIFEST_NAME).is_file():
            return _diagnose_staging(
                transactions_dir, intents_dir, transaction_id
            )
        return TransactionDiagnostic(
            transaction_id,
            "inspect",
            "unknown",
            "unknown",
            "invalid",
            (TransactionIssue("TRANSACTION_INSPECTION_FAILED", str(error)),),
        )

    if manifest["state"] == "committed":
        return TransactionDiagnostic(
            transaction_id,
            operation,
            scope,
            "committed",
            "cleanup-ready",
        )

    issues: list[TransactionIssue] = []
    for update in validated:
        current_hash = sha256_file(update["target"])
        if current_hash not in {update["original_hash"], update["staged_hash"]}:
            issues.append(
                TransactionIssue(
                    "TARGET_CHANGED",
                    f"Target changed after preparation: {update['target']}",
                    update["target"],
                )
            )
        staged_hash = sha256_file(update["staged"])
        if staged_hash is None:
            if current_hash != update["staged_hash"]:
                issues.append(
                    TransactionIssue(
                        "STAGED_FILE_MISSING",
                        f"Staged file is missing for incomplete target: {update['target']}",
                        update["target"],
                    )
                )
        elif staged_hash != update["staged_hash"]:
            issues.append(
                TransactionIssue(
                    "STAGED_FILE_CHANGED",
                    f"Staged file changed after preparation: {update['staged']}",
                    update["target"],
                )
            )

    return TransactionDiagnostic(
        transaction_id,
        operation,
        scope,
        "prepared",
        "blocked" if issues else "recoverable",
        tuple(issues),
    )


def _diagnose_staging(
    transactions_dir: Path,
    intents_dir: Path,
    transaction_id: str,
) -> TransactionDiagnostic | None:
    """Diagnose a transaction that has no manifest yet, from its intent alone.

    Read-only and lock-free, which bounds what can be concluded: a writer
    publishes its intent before the transaction directory becomes visible, so an
    intent without a manifest means either a writer still staging files or a
    process that died before the commit point. Only recovery can tell them
    apart, because only recovery takes the scope lock the writer holds. Such a
    transaction is therefore reported as ``writer-or-crash`` and never as
    ``cleanup-ready`` — labelling live staging state safe to delete is the
    failure mode the intent protocol exists to prevent.

    An orphaned directory with no intent at all is the one case that is safe to
    call ``cleanup-ready``: no current writer can own it. If both entries have
    disappeared since the directory snapshots were enumerated, the transaction
    has already been cleaned and must not be reported as an orphan.
    """
    has_directory = (transactions_dir / transaction_id).is_dir()
    intent_path = intents_dir / f"{transaction_id}{_INTENT_SUFFIX}"
    if not intent_path.is_file():
        if not has_directory:
            return None
        return TransactionDiagnostic(
            transaction_id, "inspect", "unknown", "unknown", "cleanup-ready",
            (
                TransactionIssue(
                    "ORPHANED_STAGING_WITHOUT_INTENT",
                    "Staging directory has neither a manifest nor an intent; it "
                    "predates the intent protocol and cannot belong to a writer",
                ),
            ),
        )
    try:
        # Same reader recovery uses, so a diagnosis never contradicts what
        # recovery will do — notably its transaction-id consistency check.
        _, intent = _read_transaction_intent(
            intents_dir, transaction_id, operation="inspect"
        )
    except (TracebookError, OSError) as error:
        if (
            not intent_path.is_file()
            and not (transactions_dir / transaction_id).is_dir()
        ):
            return None
        message = error.message if isinstance(error, TracebookError) else str(error)
        return TransactionDiagnostic(
            transaction_id, "inspect", "unknown", "unknown", "invalid",
            (TransactionIssue("INVALID_TRANSACTION_INTENT", message),),
        )
    code, detail = (
        ("INTENT_WITHOUT_MANIFEST",
         "Intent published and staging directory present, but no manifest yet")
        if has_directory else
        ("INTENT_WITHOUT_TRANSACTION",
         "Intent published with no transaction directory")
    )
    return TransactionDiagnostic(
        transaction_id,
        intent["operation"],
        intent["scope"],
        "staging",
        "writer-or-crash",
        (
            TransactionIssue(
                code,
                f"{detail}; an active writer or a crash before commit. Run "
                "recover-transactions instead of deleting it by hand",
            ),
        ),
    )


def inspect_transactions(root: Path) -> tuple[TransactionDiagnostic, ...]:
    """Read pending transaction state without creating locks or changing files."""
    resolved_root = root.expanduser().resolve()
    try:
        transactions_dir = _transactions_directory(resolved_root, operation="inspect")
        intents_dir = _transaction_intents_directory(resolved_root, operation="inspect")
    except TracebookError as error:
        return (
            TransactionDiagnostic(
                "<transactions>",
                error.operation,
                "unknown",
                "unknown",
                "invalid",
                (TransactionIssue(error.code, error.message),),
            ),
        )
    if not transactions_dir.is_dir() and not intents_dir.is_dir():
        return ()

    # Snapshot identities first, then diagnose each identity once from its
    # current state. A writer may publish a manifest or finish cleanup between
    # the two directory enumerations; branching during enumeration could
    # otherwise report the same transaction twice in contradictory states.
    transaction_ids: set[str] = set()
    diagnostics: list[TransactionDiagnostic] = []
    if transactions_dir.is_dir():
        for discovered_dir in sorted(transactions_dir.iterdir(), key=lambda path: path.name):
            if not discovered_dir.is_dir():
                continue
            transaction_ids.add(discovered_dir.name)
    if intents_dir.is_dir():
        for discovered_intent in sorted(intents_dir.iterdir(), key=lambda path: path.name):
            if not discovered_intent.is_file() or not discovered_intent.name.endswith(_INTENT_SUFFIX):
                continue
            transaction_id = discovered_intent.name[: -len(_INTENT_SUFFIX)]
            transaction_ids.add(transaction_id)
    for transaction_id in sorted(transaction_ids):
        discovered_dir = transactions_dir / transaction_id
        if (discovered_dir / _MANIFEST_NAME).is_file():
            diagnostic = _diagnose_transaction(
                resolved_root, transactions_dir, intents_dir, discovered_dir
            )
        else:
            diagnostic = _diagnose_staging(
                transactions_dir, intents_dir, transaction_id
            )
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return tuple(diagnostics)


def require_clean_transaction_scope(
    root: Path,
    scope: str,
    operation: str,
) -> None:
    """Reject a new writer while an earlier transaction may still own the scope.

    Production callers hold ``scope``'s lock before invoking this check. That
    makes an intent without a manifest a crashed writer rather than a concurrent
    live writer, and closes the race where a later command could overwrite a
    recoverable transaction's targets before explicit recovery.

    Recovery deliberately remains explicit: callers must report the pending
    state and direct the user through ``transactions`` / ``recover-transactions``
    instead of rolling it forward as a hidden side effect of another command.
    """
    _validate_scope(scope, operation=operation)
    observed = inspect_transactions(root)
    conflicts = [
        diagnostic
        for diagnostic in observed
        if diagnostic.scope == scope
    ]
    if not conflicts:
        # Inspection is intentionally lock-free. An unrelated writer can finish
        # between path enumeration and file reads, producing a one-snapshot
        # ``unknown`` diagnosis even though no transaction remains. Real
        # corruption or a legacy orphan is stable, so require the same unknown
        # transaction id to remain unknown in an immediate confirmation pass.
        unknown_ids = {
            diagnostic.transaction_id
            for diagnostic in observed
            if diagnostic.scope == "unknown"
        }
        if unknown_ids:
            conflicts = [
                diagnostic
                for diagnostic in inspect_transactions(root)
                if diagnostic.scope == "unknown"
                and diagnostic.transaction_id in unknown_ids
            ]
    if not conflicts:
        return
    identities = ", ".join(
        f"{diagnostic.transaction_id} ({diagnostic.disposition})"
        for diagnostic in conflicts
    )
    raise TracebookError(
        "TRANSACTION_RECOVERY_REQUIRED",
        f"Pending transaction state blocks {operation}: {identities}. Run "
        "`transactions`, then `recover-transactions`, before retrying",
        operation,
    )


def _read_transaction_intent(
    intents_dir: Path,
    transaction_id: str,
    *,
    operation: str,
) -> tuple[Path, dict[str, Any]]:
    intent_path = _intent_path(
        intents_dir,
        transaction_id,
        operation=operation,
    )
    intent = _read_intent(intent_path)
    if intent["transaction_id"] != transaction_id:
        raise _failure(
            intent["operation"],
            "Transaction intent does not match transaction id",
        )
    return intent_path, intent


def _cleanup_stale_intents(
    root: Path,
    transactions_dir: Path,
    intents_dir: Path,
) -> None:
    if not intents_dir.is_dir():
        return
    for discovered_intent in sorted(intents_dir.iterdir(), key=lambda path: path.name):
        if not discovered_intent.is_file() or not discovered_intent.name.endswith(_INTENT_SUFFIX):
            continue
        transaction_id = discovered_intent.name[: -len(_INTENT_SUFFIX)]
        try:
            intent_path, intent = _read_transaction_intent(
                intents_dir,
                transaction_id,
                operation="recover",
            )
        except FileNotFoundError:
            continue
        transaction_dir = _transaction_directory(
            transactions_dir,
            transaction_id,
            operation="recover",
        )
        if transaction_dir.exists():
            continue
        initial_scope = intent["scope"]
        with file_lock(root, initial_scope, operation="recover"):
            if transaction_dir.exists():
                continue
            try:
                current_intent = _read_intent(intent_path)
            except FileNotFoundError:
                continue
            if (
                current_intent["transaction_id"] != transaction_id
                or current_intent["scope"] != initial_scope
            ):
                raise _failure(
                    current_intent["operation"],
                    "Transaction intent changed while waiting",
                )
            _cleanup_intent(intent_path)


def _cleanup_manifestless_transactions(
    root: Path,
    transactions_dir: Path,
    intents_dir: Path,
) -> None:
    if not transactions_dir.is_dir():
        return
    for discovered_dir in sorted(transactions_dir.iterdir(), key=lambda path: path.name):
        if not discovered_dir.is_dir() or (discovered_dir / _MANIFEST_NAME).is_file():
            continue
        transaction_dir = _transaction_directory(
            transactions_dir,
            discovered_dir.name,
            operation="recover",
        )
        intent_path = _intent_path(
            intents_dir,
            transaction_dir.name,
            operation="recover",
        )
        if not intent_path.is_file():
            # Compatibility for abandoned directories created before intents
            # existed. New writers always publish an intent before making the
            # transaction directory visible.
            shutil.rmtree(transaction_dir, ignore_errors=True)
            continue

        try:
            _, intent = _read_transaction_intent(
                intents_dir,
                transaction_dir.name,
                operation="recover",
            )
        except FileNotFoundError:
            if not transaction_dir.exists():
                continue
            raise _failure(
                "recover",
                "Transaction intent disappeared while directory remained",
            ) from None
        initial_scope = intent["scope"]
        with file_lock(root, initial_scope, operation="recover"):
            if not transaction_dir.exists():
                _cleanup_intent(intent_path)
                continue
            if (transaction_dir / _MANIFEST_NAME).is_file():
                continue
            try:
                current_intent = _read_intent(intent_path)
            except FileNotFoundError:
                raise _failure(
                    intent["operation"],
                    "Transaction intent disappeared while directory remained",
                ) from None
            if (
                current_intent["transaction_id"] != transaction_dir.name
                or current_intent["scope"] != initial_scope
            ):
                raise _failure(
                    current_intent["operation"],
                    "Transaction intent changed while waiting",
                )
            shutil.rmtree(transaction_dir)
            _cleanup_intent(intent_path)


def recover_transactions(root: Path) -> tuple[Path, ...]:
    resolved_root = root.resolve()
    recovered: list[Path] = []
    with file_lock(resolved_root, "maintenance", operation="recover"):
        transactions_dir = _transactions_directory(resolved_root, operation="recover")
        intents_dir = _transaction_intents_directory(resolved_root, operation="recover")
        if not transactions_dir.exists() and not intents_dir.exists():
            return ()

        _cleanup_stale_intents(resolved_root, transactions_dir, intents_dir)
        _cleanup_manifestless_transactions(resolved_root, transactions_dir, intents_dir)
        if not transactions_dir.is_dir():
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
            try:
                initial_manifest = _read_manifest(transaction_dir)
            except FileNotFoundError:
                continue
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
                    _cleanup_intent(
                        _intent_path(
                            intents_dir,
                            transaction_dir.name,
                            operation=operation,
                        )
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
                _cleanup_intent(
                    _intent_path(
                        intents_dir,
                        transaction_dir.name,
                        operation=operation,
                    )
                )
                recovered.extend(update["target"] for update in validated)
    return tuple(recovered)
