from contextlib import contextmanager
from datetime import date
import errno
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts.errors import (
    LockTimeoutError,
    TracebookError,
)
from plugins.tracebook.skills.tracebook.scripts.storage import sha256_bytes
from plugins.tracebook.skills.tracebook.scripts import transaction
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
    CaptureRequest,
    capture,
    resolve,
)


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


class TransactionRecoveryTest(unittest.TestCase):
    def _write_targets(self, root: Path, names: tuple[str, ...]) -> dict[Path, str]:
        updates: dict[Path, str] = {}
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f"old:{name}\n".encode("utf-8"))
            updates[target] = f"new:{name}\n"
        return updates

    def _prepare_crashed_transaction(
        self,
        root: Path,
        *,
        fail_after: int,
        transaction_id: str,
        names: tuple[str, ...] = ("z-last.md", "a-first.md", "nested/middle.md"),
    ) -> tuple[dict[Path, str], Path]:
        updates = self._write_targets(root, names)
        original_replace = transaction._replace_target
        successful_replacements = 0

        def crash_after_limit(
            target: Path,
            staged: Path,
            *,
            operation: str,
        ) -> None:
            nonlocal successful_replacements
            if successful_replacements == fail_after:
                raise OSError(f"crash after {fail_after} replacements")
            original_replace(target, staged, operation=operation)
            successful_replacements += 1

        with patch.object(
            transaction,
            "_replace_target",
            side_effect=crash_after_limit,
        ):
            with self.assertRaisesRegex(
                OSError,
                f"crash after {fail_after} replacements",
            ):
                transaction.commit_updates(
                    root,
                    "project-demo",
                    "capture",
                    updates,
                    transaction_id=transaction_id,
                )

        transaction_dir = (
            root / ".tracebook-state" / "transactions" / transaction_id
        )
        self.assertTrue(transaction_dir.is_dir())
        return updates, transaction_dir

    def _read_manifest(self, transaction_dir: Path) -> tuple[str, dict[str, object]]:
        manifest_text = (transaction_dir / "manifest.json").read_text(
            encoding="utf-8"
        )
        return manifest_text, json.loads(manifest_text)

    def _write_manifest(self, transaction_dir: Path, manifest: dict[str, object]) -> None:
        (transaction_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _write_intent(
        self,
        root: Path,
        transaction_id: str,
        *,
        operation: str = "capture",
        scope: str = "project-demo",
    ) -> Path:
        intents = root / ".tracebook-state" / "transaction-intents"
        intents.mkdir(parents=True, exist_ok=True)
        path = intents / f"{transaction_id}.json"
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "transaction_id": transaction_id,
                    "operation": operation,
                    "scope": scope,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def _assert_duplicate_stage_rejected_without_writes(
        self,
        root: Path,
        updates: dict[Path, str],
        transaction_dir: Path,
        shared_stage: Path,
    ) -> None:
        with self.assertRaises(Exception) as raised:
            transaction.recover_transactions(root)

        for target in updates:
            self.assertEqual(
                f"old:{target.relative_to(root).as_posix()}\n".encode("utf-8"),
                target.read_bytes(),
            )
        self.assertTrue(shared_stage.exists())
        self.assertIsInstance(raised.exception, TracebookError)
        self.assertEqual(
            "TRANSACTION_RECOVERY_FAILED",
            raised.exception.code,
        )
        self.assertFalse(raised.exception.retryable)
        self.assertTrue(transaction_dir.exists())

    def test_empty_updates_return_without_creating_transaction_state(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)

            for scope in ("project-demo", "maintenance", "project_demo"):
                with self.subTest(scope=scope):
                    self.assertEqual(
                        (),
                        transaction.commit_updates(root, scope, "capture", {}),
                    )

            self.assertFalse((root / ".tracebook-state").exists())

    def test_nonempty_commit_rejects_invalid_or_reserved_scope_before_writes(
        self,
    ) -> None:
        for scope in ("project_demo", "maintenance"):
            with self.subTest(scope=scope), TemporaryDirectory() as temp:
                root = Path(temp)
                target = root / "item.md"
                target.write_bytes(b"original\n")

                with self.assertRaises(TracebookError) as raised:
                    transaction.commit_updates(
                        root,
                        scope,
                        "capture",
                        {target: "replacement\n"},
                        transaction_id="invalid-scope",
                    )

                self.assertEqual(
                    "TRANSACTION_RECOVERY_FAILED",
                    raised.exception.code,
                )
                self.assertEqual("capture", raised.exception.operation)
                self.assertFalse(raised.exception.retryable)
                self.assertEqual(b"original\n", target.read_bytes())
                self.assertFalse((root / ".tracebook-state").exists())

    def test_commit_applies_sorted_updates_and_removes_transaction(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            updates = self._write_targets(root, ("z-last.md", "a-first.md"))

            committed = transaction.commit_updates(
                root,
                "project-demo",
                "capture",
                updates,
                transaction_id="success",
            )

            self.assertEqual(
                tuple(sorted(updates, key=lambda path: path.relative_to(root).as_posix())),
                committed,
            )
            for target, content in updates.items():
                self.assertEqual(content, target.read_text(encoding="utf-8"))
            self.assertFalse(
                (root / ".tracebook-state" / "transactions" / "success").exists()
            )
            self.assertFalse(
                (root / ".tracebook-state" / "transaction-intents" / "success.json").exists()
            )

    def test_recovery_waits_for_manifestless_active_writer_before_cleanup(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            transaction_dir = (
                root / ".tracebook-state" / "transactions" / "active-writer"
            )
            (transaction_dir / "staged").mkdir(parents=True)
            (transaction_dir / "staged" / "00000000.stage").write_bytes(b"new\n")
            intent_path = self._write_intent(root, "active-writer")
            events: list[str] = []

            @contextmanager
            def completing_writer_lock(
                lock_root: Path,
                name: str,
                *,
                operation: str,
                **_: object,
            ):
                self.assertEqual(root, lock_root.resolve())
                self.assertEqual("recover", operation)
                events.append(f"enter:{name}")
                if name == "project-demo":
                    # The active writer still owns both paths when recovery
                    # starts waiting. It completes before recovery obtains the
                    # scope lock, so the recheck must observe their removal.
                    self.assertTrue(transaction_dir.is_dir())
                    self.assertTrue(intent_path.is_file())
                    shutil.rmtree(transaction_dir)
                    intent_path.unlink()
                try:
                    yield
                finally:
                    events.append(f"exit:{name}")

            with patch.object(transaction, "file_lock", completing_writer_lock):
                recovered = transaction.recover_transactions(root)

            self.assertEqual((), recovered)
            self.assertEqual(
                [
                    "enter:maintenance",
                    "enter:project-demo",
                    "exit:project-demo",
                    "exit:maintenance",
                ],
                events,
            )
            self.assertFalse(transaction_dir.exists())
            self.assertFalse(intent_path.exists())

    def test_manifestless_intent_rejects_reserved_scope_before_nested_lock(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            transaction_dir = (
                root / ".tracebook-state" / "transactions" / "invalid-intent"
            )
            (transaction_dir / "staged").mkdir(parents=True)
            intent_path = self._write_intent(
                root,
                "invalid-intent",
                scope="maintenance",
            )
            lock_events: list[str] = []

            @contextmanager
            def recording_lock(
                lock_root: Path,
                name: str,
                *,
                operation: str,
                **_: object,
            ):
                self.assertEqual(root, lock_root.resolve())
                lock_events.append(name)
                if len(lock_events) > 1:
                    raise AssertionError("invalid intent requested a nested lock")
                yield

            with patch.object(transaction, "file_lock", recording_lock):
                with self.assertRaises(TracebookError) as raised:
                    transaction.recover_transactions(root)

            self.assertEqual("TRANSACTION_RECOVERY_FAILED", raised.exception.code)
            self.assertEqual("capture", raised.exception.operation)
            self.assertEqual(["maintenance"], lock_events)
            self.assertTrue(transaction_dir.is_dir())
            self.assertTrue(intent_path.is_file())

    def test_recovery_cleans_stale_intent_without_transaction_directory(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            intent_path = self._write_intent(root, "intent-only")

            self.assertEqual((), transaction.recover_transactions(root))

            self.assertFalse(intent_path.exists())

    def test_recovery_cleans_crash_after_intent_before_manifest(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            target = root / "entry.md"
            target.write_text("old\n", encoding="utf-8")
            original_write = transaction.atomic_write_bytes
            staged_written = False

            def crash_after_staged_write(
                path: Path,
                content: bytes,
                *,
                operation: str,
            ) -> None:
                nonlocal staged_written
                original_write(path, content, operation=operation)
                staged_written = True
                raise OSError("crash before manifest")

            with patch.object(
                transaction,
                "atomic_write_bytes",
                side_effect=crash_after_staged_write,
            ):
                with self.assertRaisesRegex(OSError, "crash before manifest"):
                    transaction.commit_updates(
                        root,
                        "project-demo",
                        "capture",
                        {target: "new\n"},
                        transaction_id="pre-manifest-crash",
                    )

            transaction_dir = (
                root
                / ".tracebook-state"
                / "transactions"
                / "pre-manifest-crash"
            )
            intent_path = (
                root
                / ".tracebook-state"
                / "transaction-intents"
                / "pre-manifest-crash.json"
            )
            self.assertTrue(staged_written)
            self.assertTrue(transaction_dir.is_dir())
            self.assertFalse((transaction_dir / "manifest.json").exists())
            self.assertTrue(intent_path.is_file())

            self.assertEqual((), transaction.recover_transactions(root))

            self.assertEqual("old\n", target.read_text(encoding="utf-8"))
            self.assertFalse(transaction_dir.exists())
            self.assertFalse(intent_path.exists())

    def test_commit_rejects_duplicate_resolved_targets_before_transaction_write(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "nested").mkdir()
            target = root / "item.md"
            target.write_bytes(b"original\n")
            transaction_dir = (
                root / ".tracebook-state" / "transactions" / "duplicate"
            )

            with self.assertRaises(TracebookError):
                transaction.commit_updates(
                    root,
                    "project-demo",
                    "capture",
                    {
                        target: "first\n",
                        root / "nested" / ".." / "item.md": "second\n",
                    },
                    transaction_id="duplicate",
                )

            self.assertEqual(b"original\n", target.read_bytes())
            self.assertFalse(transaction_dir.exists())

    def test_recovery_rolls_forward_crashes_after_zero_one_and_two_replacements(
        self,
    ) -> None:
        for fail_after in (0, 1, 2):
            with self.subTest(fail_after=fail_after), TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                updates, transaction_dir = self._prepare_crashed_transaction(
                    root,
                    fail_after=fail_after,
                    transaction_id=f"crash-{fail_after}",
                )
                manifest_text, manifest = self._read_manifest(transaction_dir)
                entries = manifest["updates"]

                self.assertEqual(
                    {
                        "version",
                        "transaction_id",
                        "operation",
                        "scope",
                        "state",
                        "created_at",
                        "updates",
                    },
                    set(manifest),
                )
                self.assertEqual(1, manifest["version"])
                self.assertEqual(f"crash-{fail_after}", manifest["transaction_id"])
                self.assertEqual("capture", manifest["operation"])
                self.assertEqual("project-demo", manifest["scope"])
                self.assertEqual("prepared", manifest["state"])
                self.assertIsInstance(manifest["created_at"], str)
                self.assertEqual(
                    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                    manifest_text,
                )
                self.assertEqual(
                    sorted(path.relative_to(root).as_posix() for path in updates),
                    [entry["target"] for entry in entries],
                )
                for entry in entries:
                    self.assertEqual(
                        {"target", "staged", "original_hash", "staged_hash"},
                        set(entry),
                    )
                    target = root / entry["target"]
                    self.assertEqual(
                        sha256_bytes(f"old:{entry['target']}\n".encode("utf-8")),
                        entry["original_hash"],
                    )
                    self.assertEqual(
                        sha256_bytes(updates[target].encode("utf-8")),
                        entry["staged_hash"],
                    )
                self.assertEqual(
                    fail_after,
                    sum(not (transaction_dir / entry["staged"]).exists() for entry in entries),
                )

                recovered = transaction.recover_transactions(root)

                self.assertEqual(
                    tuple(sorted(updates, key=lambda path: path.relative_to(root).as_posix())),
                    recovered,
                )
                for target, content in updates.items():
                    self.assertEqual(content, target.read_text(encoding="utf-8"))
                self.assertFalse(transaction_dir.exists())

    def test_identical_content_is_safe_when_staged_file_is_missing(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "same.md"
            target.write_bytes(b"same\n")
            updates = {target: "same\n"}

            with patch.object(
                transaction,
                "_replace_target",
                side_effect=OSError("crash before replacement"),
            ):
                with self.assertRaisesRegex(OSError, "crash before replacement"):
                    transaction.commit_updates(
                        root,
                        "project-demo",
                        "capture",
                        updates,
                        transaction_id="identical",
                    )

            transaction_dir = (
                root / ".tracebook-state" / "transactions" / "identical"
            )
            _, manifest = self._read_manifest(transaction_dir)
            entry = manifest["updates"][0]
            (transaction_dir / entry["staged"]).unlink()

            recovered = transaction.recover_transactions(root)

            self.assertEqual((target.resolve(),), recovered)
            self.assertEqual("same\n", target.read_text(encoding="utf-8"))
            self.assertFalse(transaction_dir.exists())

    def test_manual_target_modification_blocks_recovery_and_later_writes(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            updates, transaction_dir = self._prepare_crashed_transaction(
                root,
                fail_after=0,
                transaction_id="conflict",
                names=("a-conflict.md", "b-later.md"),
            )
            first, second = sorted(
                updates,
                key=lambda path: path.relative_to(root).as_posix(),
            )
            first.write_text("manual edit\n", encoding="utf-8")

            with self.assertRaises(TracebookError) as raised:
                transaction.recover_transactions(root)

            self.assertEqual("TRANSACTION_RECOVERY_FAILED", raised.exception.code)
            self.assertEqual("capture", raised.exception.operation)
            self.assertFalse(raised.exception.retryable)
            self.assertEqual("manual edit\n", first.read_text(encoding="utf-8"))
            self.assertEqual("old:b-later.md\n", second.read_text(encoding="utf-8"))
            self.assertTrue(transaction_dir.exists())

    def _staging_dir(self, root: Path, transaction_id: str) -> Path:
        staged = root / ".tracebook-state" / "transactions" / transaction_id / "staged"
        staged.mkdir(parents=True, exist_ok=True)
        (staged / "00000000.stage").write_text("staged", encoding="utf-8")
        return staged.parent

    def test_inspection_reports_intent_backed_staging_as_writer_or_crash(self) -> None:
        """An intent without a manifest must never be advertised as safe to delete."""
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self._staging_dir(root, "with-directory")
            self._write_intent(root, "with-directory", scope="project-demo")
            self._write_intent(root, "intent-only", scope="registry")

            found = {d.transaction_id: d for d in transaction.inspect_transactions(root)}
            self.assertEqual({"with-directory", "intent-only"}, set(found))
            for transaction_id, scope, code in (
                ("with-directory", "project-demo", "INTENT_WITHOUT_MANIFEST"),
                ("intent-only", "registry", "INTENT_WITHOUT_TRANSACTION"),
            ):
                with self.subTest(transaction_id=transaction_id):
                    diagnostic = found[transaction_id]
                    self.assertEqual("staging", diagnostic.state)
                    self.assertEqual("writer-or-crash", diagnostic.disposition)
                    self.assertNotEqual("cleanup-ready", diagnostic.disposition)
                    self.assertEqual("capture", diagnostic.operation)
                    self.assertEqual(scope, diagnostic.scope)
                    self.assertEqual(code, diagnostic.issues[0].code)
                    self.assertIn("recover-transactions", diagnostic.issues[0].message)

    def test_inspection_reports_pre_intent_orphan_as_cleanup_ready(self) -> None:
        """A staging directory with no intent cannot belong to a writer."""
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self._staging_dir(root, "pre-intent-orphan")
            (diagnostic,) = transaction.inspect_transactions(root)
            self.assertEqual("pre-intent-orphan", diagnostic.transaction_id)
            self.assertEqual("cleanup-ready", diagnostic.disposition)
            self.assertEqual(
                "ORPHANED_STAGING_WITHOUT_INTENT", diagnostic.issues[0].code
            )

    def test_inspection_agrees_with_recovery_on_a_mismatched_intent_id(self) -> None:
        """A diagnosis must not promise recovery will handle what it rejects."""
        with TemporaryDirectory() as temp:
            root = Path(temp)
            intents = root / ".tracebook-state" / "transaction-intents"
            intents.mkdir(parents=True)
            (intents / "visible-id.json").write_text(
                json.dumps({"version": 1, "transaction_id": "different-id",
                            "operation": "capture", "scope": "registry"},
                           indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (diagnostic,) = transaction.inspect_transactions(root)
            self.assertEqual("visible-id", diagnostic.transaction_id)
            self.assertEqual("invalid", diagnostic.disposition)
            self.assertNotEqual("writer-or-crash", diagnostic.disposition)
            self.assertEqual("INVALID_TRANSACTION_INTENT", diagnostic.issues[0].code)
            self.assertIn("does not match", diagnostic.issues[0].message)
            # Recovery rejects the same state, so the two agree.
            with self.assertRaisesRegex(TracebookError, "does not match"):
                transaction.recover_transactions(root)

    def test_inspection_reports_an_unreadable_intent_as_invalid(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            intents = root / ".tracebook-state" / "transaction-intents"
            intents.mkdir(parents=True)
            (intents / "broken.json").write_text("{not json", encoding="utf-8")
            (diagnostic,) = transaction.inspect_transactions(root)
            self.assertEqual("broken", diagnostic.transaction_id)
            self.assertEqual("invalid", diagnostic.disposition)
            self.assertEqual("INVALID_TRANSACTION_INTENT", diagnostic.issues[0].code)

    def test_inspection_of_staging_state_writes_nothing_and_takes_no_lock(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self._staging_dir(root, "untouched")
            self._write_intent(root, "untouched")
            state = root / ".tracebook-state"
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in sorted(state.rglob("*")) if path.is_file()
            }

            self.assertTrue(transaction.inspect_transactions(root))

            after = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in sorted(state.rglob("*")) if path.is_file()
            }
            self.assertEqual(before, after)
            locks = state / "locks"
            self.assertFalse(
                locks.is_dir() and any(locks.iterdir()),
                f"inspect created lock files: {list(locks.iterdir()) if locks.is_dir() else []}",
            )

    def test_inspection_ignores_an_intent_whose_transaction_has_a_manifest(self) -> None:
        """A committed transaction is diagnosed from its manifest, not twice."""
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self._prepare_crashed_transaction(
                root, fail_after=0, transaction_id="manifest-wins"
            )
            self._write_intent(root, "manifest-wins")
            found = [d for d in transaction.inspect_transactions(root)
                     if d.transaction_id == "manifest-wins"]
            self.assertEqual(1, len(found), found)
            self.assertNotEqual("staging", found[0].state)

    def test_inspection_reports_a_manual_edit_without_writing_or_recovering(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            updates, transaction_dir = self._prepare_crashed_transaction(
                root,
                fail_after=0,
                transaction_id="inspect-conflict",
                names=("a-conflict.md", "b-later.md"),
            )
            first, second = sorted(
                updates,
                key=lambda path: path.relative_to(root).as_posix(),
            )
            first.write_text("manual edit\n", encoding="utf-8")
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in (first, second, transaction_dir / "manifest.json")
            }

            diagnostics = transaction.inspect_transactions(root)

            self.assertEqual(1, len(diagnostics))
            diagnostic = diagnostics[0]
            self.assertEqual("inspect-conflict", diagnostic.transaction_id)
            self.assertEqual("capture", diagnostic.operation)
            self.assertEqual("project-demo", diagnostic.scope)
            self.assertEqual("blocked", diagnostic.disposition)
            self.assertEqual("TARGET_CHANGED", diagnostic.issues[0].code)
            self.assertEqual(first.resolve(), diagnostic.issues[0].target)
            self.assertEqual(
                before,
                {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in (first, second, transaction_dir / "manifest.json")
                },
            )
            self.assertTrue(transaction_dir.exists())

    def test_missing_staged_file_is_rejected_when_target_is_not_staged_content(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            updates, transaction_dir = self._prepare_crashed_transaction(
                root,
                fail_after=0,
                transaction_id="missing-stage",
                names=("a-missing.md", "b-later.md"),
            )
            _, manifest = self._read_manifest(transaction_dir)
            first_entry = manifest["updates"][0]
            (transaction_dir / first_entry["staged"]).unlink()

            with self.assertRaises(TracebookError) as raised:
                transaction.recover_transactions(root)

            self.assertEqual("TRANSACTION_RECOVERY_FAILED", raised.exception.code)
            for target in updates:
                self.assertEqual(
                    f"old:{target.relative_to(root).as_posix()}\n",
                    target.read_text(encoding="utf-8"),
                )
            self.assertTrue(transaction_dir.exists())

    def test_duplicate_resolved_staged_path_is_rejected_before_target_write(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            updates, transaction_dir = self._prepare_crashed_transaction(
                root,
                fail_after=0,
                transaction_id="duplicate-stage",
                names=("a-first.md", "b-second.md"),
            )
            _, manifest = self._read_manifest(transaction_dir)
            first_entry, second_entry = manifest["updates"]
            second_entry["staged"] = first_entry["staged"]
            second_entry["staged_hash"] = first_entry["staged_hash"]
            self._write_manifest(transaction_dir, manifest)
            shared_stage = transaction_dir / first_entry["staged"]

            self._assert_duplicate_stage_rejected_without_writes(
                root,
                updates,
                transaction_dir,
                shared_stage,
            )

    def test_staged_symlink_alias_is_rejected_before_target_write(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            updates, transaction_dir = self._prepare_crashed_transaction(
                root,
                fail_after=0,
                transaction_id="duplicate-stage-alias",
                names=("a-first.md", "b-second.md"),
            )
            _, manifest = self._read_manifest(transaction_dir)
            first_entry, second_entry = manifest["updates"]
            shared_stage = transaction_dir / first_entry["staged"]
            alias = transaction_dir / "staged" / "shared-alias.stage"
            _symlink_or_skip(
                self,
                alias,
                Path(shared_stage.name),
                target_is_directory=False,
            )
            second_entry["staged"] = alias.relative_to(transaction_dir).as_posix()
            second_entry["staged_hash"] = first_entry["staged_hash"]
            self._write_manifest(transaction_dir, manifest)

            self._assert_duplicate_stage_rejected_without_writes(
                root,
                updates,
                transaction_dir,
                shared_stage,
            )

    def test_manifest_path_escape_is_rejected_before_any_target_write(self) -> None:
        for escaped_field, escaped_value in (
            ("target", "../outside.md"),
            ("staged", "../outside.stage"),
        ):
            with self.subTest(field=escaped_field), TemporaryDirectory() as temp:
                temporary_root = Path(temp)
                root = temporary_root / "root"
                root.mkdir()
                updates, transaction_dir = self._prepare_crashed_transaction(
                    root,
                    fail_after=0,
                    transaction_id=f"escape-{escaped_field}",
                    names=("a-first.md", "b-escape.md"),
                )
                _, manifest = self._read_manifest(transaction_dir)
                manifest["updates"][1][escaped_field] = escaped_value
                self._write_manifest(transaction_dir, manifest)
                outside_target = temporary_root / "outside.md"
                outside_stage = transaction_dir.parent / "outside.stage"

                with self.assertRaises(TracebookError):
                    transaction.recover_transactions(root)

                for target in updates:
                    self.assertEqual(
                        f"old:{target.relative_to(root).as_posix()}\n",
                        target.read_text(encoding="utf-8"),
                    )
                self.assertFalse(outside_target.exists())
                self.assertFalse(outside_stage.exists())
                self.assertTrue(transaction_dir.exists())

    def test_recovery_rejects_staged_symlink_escape_before_target_write(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            updates, transaction_dir = self._prepare_crashed_transaction(
                root,
                fail_after=0,
                transaction_id="staged-symlink",
                names=("item.md",),
            )
            target, content = next(iter(updates.items()))
            outside_stage = transaction_dir / "outside.stage"
            outside_stage.write_bytes(content.encode("utf-8"))
            link = transaction_dir / "staged" / "link"
            _symlink_or_skip(
                self,
                link,
                transaction_dir,
                target_is_directory=True,
            )
            _, manifest = self._read_manifest(transaction_dir)
            manifest["updates"][0]["staged"] = "staged/link/outside.stage"
            self._write_manifest(transaction_dir, manifest)

            with self.assertRaises(TracebookError) as raised:
                transaction.recover_transactions(root)

            self.assertEqual("PATH_OUTSIDE_ROOT", raised.exception.code)
            self.assertEqual(b"old:item.md\n", target.read_bytes())
            self.assertTrue(outside_stage.exists())

    def test_recovery_acquires_maintenance_then_scope_and_reloads_manifest(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            updates, transaction_dir = self._prepare_crashed_transaction(
                root,
                fail_after=0,
                transaction_id="reload",
                names=("one.md",),
            )
            events: list[str] = []

            @contextmanager
            def completing_writer_lock(
                lock_root: Path,
                name: str,
                *,
                operation: str,
                **_: object,
            ):
                self.assertEqual(root.resolve(), lock_root.resolve())
                events.append(f"enter:{name}")
                if name == "project-demo":
                    _, manifest = self._read_manifest(transaction_dir)
                    entry = manifest["updates"][0]
                    transaction._replace_target(
                        root / entry["target"],
                        transaction_dir / entry["staged"],
                        operation="capture",
                    )
                    manifest["state"] = "committed"
                    self._write_manifest(transaction_dir, manifest)
                try:
                    yield
                finally:
                    events.append(f"exit:{name}")

            with patch.object(transaction, "file_lock", completing_writer_lock):
                transaction.recover_transactions(root)

            self.assertEqual(
                [
                    "enter:maintenance",
                    "enter:project-demo",
                    "exit:project-demo",
                    "exit:maintenance",
                ],
                events,
            )
            for target, content in updates.items():
                self.assertEqual(content, target.read_text(encoding="utf-8"))
            self.assertFalse(transaction_dir.exists())

    def test_recovery_rejects_reserved_scope_before_nested_lock(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            updates, transaction_dir = self._prepare_crashed_transaction(
                root,
                fail_after=0,
                transaction_id="reserved-scope",
                names=("one.md",),
            )
            _, manifest = self._read_manifest(transaction_dir)
            manifest["scope"] = "maintenance"
            self._write_manifest(transaction_dir, manifest)
            lock_events: list[str] = []

            @contextmanager
            def recording_lock(
                lock_root: Path,
                name: str,
                *,
                operation: str,
                **_: object,
            ):
                self.assertEqual(root.resolve(), lock_root.resolve())
                lock_events.append(name)
                if len(lock_events) > 1:
                    raise LockTimeoutError(name, 0, operation)
                yield

            with patch.object(transaction, "file_lock", recording_lock):
                with self.assertRaises(TracebookError) as raised:
                    transaction.recover_transactions(root)

            self.assertEqual(
                "TRANSACTION_RECOVERY_FAILED",
                raised.exception.code,
            )
            self.assertEqual("capture", raised.exception.operation)
            self.assertFalse(raised.exception.retryable)
            self.assertEqual(["maintenance"], lock_events)
            for target in updates:
                self.assertEqual(b"old:one.md\n", target.read_bytes())
            self.assertTrue(transaction_dir.exists())

    def test_recovery_skips_transaction_deleted_before_initial_manifest_read(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            _, transaction_dir = self._prepare_crashed_transaction(
                root,
                fail_after=0,
                transaction_id="deleted-before-read",
                names=("one.md",),
            )
            original_read_manifest = transaction._read_manifest
            read_count = 0

            def delete_then_read(path: Path):
                nonlocal read_count
                read_count += 1
                if read_count == 1:
                    shutil.rmtree(path)
                    raise FileNotFoundError(path / "manifest.json")
                return original_read_manifest(path)

            with patch.object(
                transaction,
                "_read_manifest",
                side_effect=delete_then_read,
            ):
                recovered = transaction.recover_transactions(root)

            self.assertEqual((), recovered)
            self.assertEqual(1, read_count)
            self.assertFalse(transaction_dir.exists())

    def test_resolve_recovers_a_crashed_project_capture_as_one_transaction(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            repository = base / "business"
            (repository / ".git").mkdir(parents=True)
            context = resolve(root, repository)
            request = CaptureRequest(
                operation="create",
                knowledge_id="recovered-capture-rule",
                scope="project",
                kind="business-rule",
                title="Recovered capture rule",
                body="Every managed capture target must roll forward together.",
                evidence=("src/recovery.py:L1-L12",),
                status="current",
                write_intent="durable",
                content_kind="knowledge",
            )
            original_replace = transaction._replace_target
            replacements = 0

            def crash_after_first_replacement(
                target: Path,
                staged: Path,
                *,
                operation: str,
            ) -> None:
                nonlocal replacements
                if replacements == 1:
                    raise OSError("capture crashed after first replacement")
                original_replace(target, staged, operation=operation)
                replacements += 1

            with patch.object(
                transaction,
                "_replace_target",
                side_effect=crash_after_first_replacement,
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "capture crashed after first replacement",
                ):
                    capture(context, request, date(2026, 7, 13))

            transactions = root / ".tracebook-state" / "transactions"
            self.assertEqual(1, len(list(transactions.iterdir())))

            recovered_context = resolve(root, repository)

            project = recovered_context.root / recovered_context.record.relative_path
            document = project / "knowledge" / "business-rule" / "recovered-capture-rule.md"
            index = project / "index.md"
            status = project / "project-status.md"
            log = project / "logs" / "2026-07.md"
            self.assertIn("Recovered capture rule", document.read_text(encoding="utf-8"))
            self.assertEqual(
                1,
                document.read_text(encoding="utf-8").count("<!-- tracebook:event:"),
            )
            self.assertIn("recovered-capture-rule.md", index.read_text(encoding="utf-8"))
            self.assertIn("recovered-capture-rule", status.read_text(encoding="utf-8"))
            self.assertEqual(1, log.read_text(encoding="utf-8").count("recovered-capture-rule"))
            self.assertEqual([], list(transactions.iterdir()))

    def test_resolve_recovers_crashed_entity_lifecycle_transition(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            repository = base / "business"
            (repository / ".git").mkdir(parents=True)
            context = resolve(root, repository)
            current = CaptureRequest(
                operation="create",
                knowledge_id="keep-one-lifecycle-authority",
                scope="project",
                kind="decision",
                title="Keep one lifecycle authority",
                body="The original current history must survive recovery.",
                evidence=("src/recovery.py:L20-L32",),
                status="current",
                write_intent="durable",
                content_kind="knowledge",
            )
            capture(context, current, date(2026, 7, 13))
            retired = CaptureRequest(
                operation="change-status",
                knowledge_id="keep-one-lifecycle-authority",
                expected_version=1,
                scope="project",
                kind="decision",
                title="Keep one lifecycle authority",
                body="The retired event must roll forward with every target.",
                evidence=("src/recovery.py:L34-L42",),
                status="deprecated",
                write_intent="durable",
                content_kind="knowledge",
            )
            original_replace = transaction._replace_target
            replacements = 0

            def crash_after_two_replacements(
                target: Path,
                staged: Path,
                *,
                operation: str,
            ) -> None:
                nonlocal replacements
                if replacements == 2:
                    raise OSError("lifecycle capture crashed after two replacements")
                original_replace(target, staged, operation=operation)
                replacements += 1

            with patch.object(
                transaction,
                "_replace_target",
                side_effect=crash_after_two_replacements,
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "lifecycle capture crashed after two replacements",
                ):
                    capture(context, retired, date(2026, 7, 14))

            transactions = root / ".tracebook-state" / "transactions"
            self.assertEqual(1, len(list(transactions.iterdir())))

            recovered = resolve(root, repository)
            retry = capture(recovered, retired, date(2026, 7, 15))
            self.assertTrue(retry.skipped)
            marker = f"<!-- tracebook:event:{retry.event_id} -->"

            project = recovered.root / recovered.record.relative_path
            authority_page = project / "knowledge" / "decision" / "keep-one-lifecycle-authority.md"
            index = project / "index.md"
            status = project / "project-status.md"
            log = project / "logs" / "2026-07.md"
            authority = authority_page.read_text(encoding="utf-8")
            self.assertIn("type: decision", authority)
            self.assertIn("status: deprecated", authority)
            self.assertIn("version: 2", authority.split("---", 2)[1])
            # Current section carries the retired event; History preserves the original.
            self.assertIn(retired.body, authority)
            self.assertIn(current.body, authority)
            self.assertIn("### Version 1 — 2026-07-13", authority)
            self.assertEqual(1, authority.count(marker))
            self.assertEqual(1, index.read_text(encoding="utf-8").count("keep-one-lifecycle-authority.md"))
            self.assertIn("keep-one-lifecycle-authority", status.read_text(encoding="utf-8"))
            self.assertEqual(
                1,
                log.read_text(encoding="utf-8").count(retry.event_id),
            )
            self.assertEqual([], list(transactions.iterdir()))


if __name__ == "__main__":
    unittest.main()
