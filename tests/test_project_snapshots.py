from __future__ import annotations

from datetime import date
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts.capture import CaptureRequest
from plugins.tracebook.skills.tracebook.scripts.errors import TracebookError
from plugins.tracebook.skills.tracebook.scripts import knowledge_entity
from plugins.tracebook.skills.tracebook.scripts.knowledge_entity import capture_entity
from plugins.tracebook.skills.tracebook.scripts import transaction
from plugins.tracebook.skills.tracebook.scripts import snapshots
from plugins.tracebook.skills.tracebook.scripts import tracebook_runner
from plugins.tracebook.skills.tracebook.scripts.snapshots import project_knowledge_root
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
    read_context_for_path,
    resolve,
)


class ProjectSnapshotTest(unittest.TestCase):
    @staticmethod
    def _request(*, body: str, operation: str = "create", expected_version: int | None = None) -> CaptureRequest:
        return CaptureRequest(
            operation=operation,
            knowledge_id="snapshot-contract",
            scope="project",
            kind="architecture",
            title="Snapshot contract",
            body=body,
            evidence=("src/snapshot.py:L1",),
            status="current",
            expected_version=expected_version,
        )

    def test_read_path_uses_snapshot_without_locks_or_writes(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "service"; (repo / ".git").mkdir(parents=True)
            context = resolve(root, repo)
            capture_entity(root, context.record, self._request(body="version one"), date(2026, 7, 23))
            pointer = root / ".tracebook-state" / "snapshots" / context.record.project_id / "current.json"
            before = {path: path.read_bytes() for path in (root / ".tracebook-state").rglob("*") if path.is_file()}

            with patch(
                "plugins.tracebook.skills.tracebook.scripts.tracebook_runner.file_lock",
                side_effect=AssertionError("read path must not acquire a lock"),
            ):
                payload = read_context_for_path(root, repo, "version one")

            self.assertEqual("snapshot-contract", payload["current_context"][0]["knowledge_id"])
            self.assertEqual([], payload["warnings"])
            self.assertTrue(json.loads(pointer.read_text(encoding="utf-8"))["snapshot_id"])
            after = {path: path.read_bytes() for path in (root / ".tracebook-state").rglob("*") if path.is_file()}
            self.assertEqual(before, after)

    def test_pointer_switches_only_after_complete_snapshot_content(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "service"; (repo / ".git").mkdir(parents=True)
            context = resolve(root, repo)
            capture_entity(root, context.record, self._request(body="version one"), date(2026, 7, 23))
            pointer = root / ".tracebook-state" / "snapshots" / context.record.project_id / "current.json"
            replaced: list[Path] = []
            original_replace = transaction._replace_target

            def record_replace(target: Path, staged: Path, *, operation: str) -> None:
                replaced.append(target)
                original_replace(target, staged, operation=operation)

            with patch.object(transaction, "_replace_target", side_effect=record_replace):
                capture_entity(
                    root,
                    context.record,
                    self._request(body="version two", operation="revise", expected_version=1),
                    date(2026, 7, 23),
                )

            self.assertEqual(pointer, replaced[-1])
            payload = read_context_for_path(root, repo, "version two")
            self.assertEqual(2, payload["current_context"][0]["version"])
            snapshot_root, mode = project_knowledge_root(root, context.record, operation="test")
            self.assertEqual("snapshot", mode)
            self.assertIn("version two", (snapshot_root / "architecture" / "snapshot-contract.md").read_text(encoding="utf-8"))

    def test_reader_keeps_previous_snapshot_until_crashed_pointer_commit_recovers(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "service"; (repo / ".git").mkdir(parents=True)
            context = resolve(root, repo)
            capture_entity(root, context.record, self._request(body="version one"), date(2026, 7, 23))
            pointer = root / ".tracebook-state" / "snapshots" / context.record.project_id / "current.json"
            original_replace = transaction._replace_target

            def fail_before_pointer(target: Path, staged: Path, *, operation: str) -> None:
                if target == pointer:
                    raise OSError("simulated crash before pointer")
                original_replace(target, staged, operation=operation)

            with patch.object(transaction, "_replace_target", side_effect=fail_before_pointer):
                with self.assertRaises(OSError):
                    capture_entity(
                        root,
                        context.record,
                        self._request(body="version two", operation="revise", expected_version=1),
                        date(2026, 7, 23),
                    )

            before_recovery = read_context_for_path(root, repo, "version one")
            self.assertEqual(1, before_recovery["current_context"][0]["version"])
            transaction.recover_transactions(root)
            after_recovery = read_context_for_path(root, repo, "version two")
            self.assertEqual(2, after_recovery["current_context"][0]["version"])

    def test_snapshot_versions_are_pruned_to_retention_bound(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "service"; (repo / ".git").mkdir(parents=True)
            context = resolve(root, repo)
            for index in range(15):
                capture_entity(
                    root,
                    context.record,
                    CaptureRequest(
                        operation="create",
                        knowledge_id=f"rule-{index:03d}",
                        scope="project",
                        kind="architecture",
                        title=f"Rule {index}",
                        body=f"Body for rule {index}.",
                        evidence=(f"src/rule_{index}.py:L1",),
                        status="current",
                    ),
                    date(2026, 7, 23),
                )
            versions = root / ".tracebook-state" / "snapshots" / context.record.project_id / "versions"
            live = {directory for directory in versions.iterdir() if directory.is_dir()}
            self.assertLessEqual(len(live), snapshots.SNAPSHOT_RETENTION)
            snapshot_root, mode = project_knowledge_root(root, context.record, operation="test")
            self.assertEqual("snapshot", mode)
            self.assertTrue(snapshot_root.is_dir())
            payload = read_context_for_path(root, repo, "Rule 14")
            self.assertEqual("rule-014", payload["current_context"][0]["knowledge_id"])

    def test_reader_retries_when_its_resolved_snapshot_is_retired(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "service"; (repo / ".git").mkdir(parents=True)
            context = resolve(root, repo)
            capture_entity(
                root,
                context.record,
                self._request(body="Version one."),
                date(2026, 7, 23),
            )
            real_build = tracebook_runner.build_context
            calls = 0

            def retire_first_root(*args: object, **kwargs: object) -> dict[str, object]:
                nonlocal calls
                calls += 1
                if calls == 1:
                    capture_entity(
                        root,
                        context.record,
                        self._request(
                            body="Version two.",
                            operation="revise",
                            expected_version=1,
                        ),
                        date(2026, 7, 23),
                    )
                    snapshots.prune_project_snapshots(root, context.record, keep=1)
                return real_build(*args, **kwargs)

            with patch.object(
                tracebook_runner,
                "build_context",
                side_effect=retire_first_root,
            ):
                payload = read_context_for_path(root, repo, "Version two")

            self.assertEqual(2, calls)
            self.assertEqual(2, payload["current_context"][0]["version"])
            self.assertIn("Version two", payload["current_context"][0]["excerpt"])

    def test_prune_failure_never_fails_an_already_committed_capture(self) -> None:
        """GC runs after the pointer commits, so its errors must stay contained.

        Two failure points are injected: enumerating versions (stat) and deleting
        a tree. In both cases the knowledge must still be readable — reporting an
        error for a durable write would be worse than leaking a directory.
        """
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "service"; (repo / ".git").mkdir(parents=True)
            context = resolve(root, repo)
            capture_entity(root, context.record, self._request(body="Version one."), date(2026, 7, 23))
            versions = root / ".tracebook-state" / "snapshots" / context.record.project_id / "versions"

            real_pointer = snapshots._pointer_snapshot_id

            def fail_only_for_prune(*args: object, operation: str, **kwargs: object) -> str | None:
                if operation == "snapshot-prune":
                    raise PermissionError("locked by scanner")
                return real_pointer(*args, operation=operation, **kwargs)

            with patch.object(snapshots, "_pointer_snapshot_id", side_effect=fail_only_for_prune):
                second = capture_entity(
                    root,
                    context.record,
                    self._request(body="Version two.", operation="revise", expected_version=1),
                    date(2026, 7, 23),
                )
            self.assertFalse(second.skipped)
            self.assertEqual(2, read_context_for_path(root, repo, "Version two")["current_context"][0]["version"])

            with patch.object(snapshots, "_remove_tree", side_effect=OSError("in use")):
                third = capture_entity(
                    root,
                    context.record,
                    self._request(body="Version three.", operation="revise", expected_version=2),
                    date(2026, 7, 23),
                )
            self.assertFalse(third.skipped)
            self.assertEqual(3, read_context_for_path(root, repo, "Version three")["current_context"][0]["version"])
            # Neither injected failure collected anything, so the store is intact
            # and the live pointer still resolves.
            self.assertTrue([item for item in versions.iterdir() if item.is_dir()])
            self.assertEqual("snapshot", project_knowledge_root(root, context.record, operation="test")[1])

    def test_prune_reports_deletion_failures_without_raising(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "service"; (repo / ".git").mkdir(parents=True)
            context = resolve(root, repo)
            capture_entity(root, context.record, self._request(body="Version one."), date(2026, 7, 23))
            capture_entity(
                root,
                context.record,
                self._request(body="Version two.", operation="revise", expected_version=1),
                date(2026, 7, 23),
            )
            versions = (
                root / ".tracebook-state" / "snapshots"
                / context.record.project_id / "versions"
            )
            with patch.object(snapshots, "_remove_tree", side_effect=OSError("in use")):
                failures = snapshots.prune_project_snapshots(root, context.record, keep=1)
            self.assertTrue(failures)
            for failure in failures:
                self.assertIn("in use", failure)
            self.assertTrue(
                any(path.name.startswith(".pruning-") for path in versions.iterdir())
            )

            cleanup_failures = snapshots.prune_project_snapshots(
                root, context.record, keep=1
            )
            self.assertEqual([], cleanup_failures)
            self.assertFalse(
                any(path.name.startswith(".pruning-") for path in versions.iterdir())
            )

    def test_unregistered_path_requires_activation_without_writing(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            registered = base / "registered"; (registered / ".git").mkdir(parents=True)
            resolve(root, registered)
            target = base / "new-service"; target.mkdir()
            registry_before = (root / "registry.json").read_bytes()

            with self.assertRaises(TracebookError) as raised:
                read_context_for_path(root, target, "anything")

            self.assertEqual("PROJECT_ACTIVATION_REQUIRED", raised.exception.code)
            self.assertEqual(registry_before, (root / "registry.json").read_bytes())

    def test_different_project_captures_reach_commit_without_cross_project_locking(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            first_repo = base / "first"; (first_repo / ".git").mkdir(parents=True)
            second_repo = base / "second"; (second_repo / ".git").mkdir(parents=True)
            first = resolve(root, first_repo)
            second = resolve(root, second_repo)
            barrier = Barrier(2)
            original_commit = transaction.commit_updates

            def synchronized_commit(*args: object, **kwargs: object) -> tuple[Path, ...]:
                barrier.wait(timeout=5)
                return original_commit(*args, **kwargs)  # type: ignore[arg-type]

            with patch.object(knowledge_entity, "commit_updates", side_effect=synchronized_commit):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(
                        lambda context: capture_entity(
                            root,
                            context.record,
                            CaptureRequest(
                                operation="create",
                                knowledge_id=f"{context.record.name}-rule",
                                scope="project",
                                kind="architecture",
                                title=f"{context.record.name} rule",
                                body="concurrent independent write",
                                evidence=("src/concurrent.py:L1",),
                                status="current",
                            ),
                            date(2026, 7, 23),
                        ),
                        (first, second),
                    ))

            self.assertEqual(2, len(results))
            for context in (first, second):
                payload = read_context_for_path(root, Path(context.record.locations[0]), "independent write")
                self.assertEqual(1, len(payload["current_context"]))
