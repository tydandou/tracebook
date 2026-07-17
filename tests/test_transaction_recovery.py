from contextlib import contextmanager
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts.errors import TracebookError
from plugins.tracebook.skills.tracebook.scripts.storage import sha256_bytes
from plugins.tracebook.skills.tracebook.scripts import transaction


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

    def test_empty_updates_return_without_creating_transaction_state(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)

            self.assertEqual(
                (),
                transaction.commit_updates(root, "project-demo", "capture", {}),
            )

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


if __name__ == "__main__":
    unittest.main()
