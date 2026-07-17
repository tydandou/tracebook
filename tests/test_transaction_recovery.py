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
            root = Path(temp)
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
                root = Path(temp)
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
                scope="project",
                kind="business-rule",
                category="business-rules",
                title="Recovered capture rule",
                body="Every managed capture target must roll forward together.",
                evidence=("src/recovery.py:L1-L12",),
                status="Current",
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
            document = project / "business-rules.md"
            index = project / "index.md"
            status = project / "project-status.md"
            log = project / "logs" / "2026-07.md"
            marker = "<!-- tracebook:event:"
            self.assertIn("Recovered capture rule", document.read_text(encoding="utf-8"))
            self.assertIn("business-rules.md", index.read_text(encoding="utf-8"))
            self.assertIn("Recovered capture rule", status.read_text(encoding="utf-8"))
            self.assertEqual(1, log.read_text(encoding="utf-8").count(marker))
            self.assertEqual([], list(transactions.iterdir()))


if __name__ == "__main__":
    unittest.main()
