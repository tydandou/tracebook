import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts.capture import (
    CaptureRequest,
    _enforce_write_intent_and_evidence,
)
from plugins.tracebook.skills.tracebook.scripts import project_registry


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "plugins" / "tracebook" / "skills" / "tracebook" / "scripts" / "tracebook_runner.py"


class EvidenceGateTest(unittest.TestCase):
    """A1: schema-v2 write path must pass the intent + evidence gate."""

    def _v2_request(self, **overrides: object) -> CaptureRequest:
        base = dict(
            scope="project",
            kind="architecture",
            title="Payment retry",
            body="Payment retries use idempotency keys.",
            operation="create",
            knowledge_id="payment-retry",
            status="current",
            evidence=("src/pay.py:L1-L9",),
        )
        base.update(overrides)
        return CaptureRequest(**base)

    def test_valid_v2_request_passes_gate(self) -> None:
        _enforce_write_intent_and_evidence(self._v2_request())

    def test_ephemeral_write_intent_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _enforce_write_intent_and_evidence(
                self._v2_request(write_intent="ephemeral")
            )

    def test_unclassified_evidence_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _enforce_write_intent_and_evidence(
                self._v2_request(evidence=("just some prose",))
            )

    def test_current_without_evidence_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _enforce_write_intent_and_evidence(
                self._v2_request(status="current", evidence=())
            )

    def test_non_current_may_have_empty_evidence(self) -> None:
        _enforce_write_intent_and_evidence(
            self._v2_request(status="pending", evidence=())
        )


class RemoteWarningTest(unittest.TestCase):
    """A3: unsupported origin remote must warn, not crash."""

    def test_unsupported_remote_returns_warning(self) -> None:
        with patch.object(
            project_registry,
            "_origin_remote_raw",
            return_value="file:///srv/repos/widgets.git",
        ):
            warning, raw = project_registry.origin_remote_warning(Path("."))
        self.assertIsNotNone(warning)
        self.assertEqual(raw, "file:///srv/repos/widgets.git")

    def test_unsupported_remote_yields_none_identity(self) -> None:
        with patch.object(
            project_registry,
            "_origin_remote_raw",
            return_value="D:\\repos\\widgets",
        ):
            self.assertIsNone(project_registry._origin_remote(Path(".")))

    def test_supported_remote_has_no_warning(self) -> None:
        with patch.object(
            project_registry,
            "_origin_remote_raw",
            return_value="https://github.com/acme/widgets.git",
        ):
            warning, raw = project_registry.origin_remote_warning(Path("."))
        self.assertIsNone(warning)
        self.assertEqual(raw, "https://github.com/acme/widgets.git")

    def test_absent_remote_is_silent(self) -> None:
        with patch.object(project_registry, "_origin_remote_raw", return_value=""):
            self.assertEqual(
                (None, None), project_registry.origin_remote_warning(Path("."))
            )


class RemoteNormalizationTest(unittest.TestCase):
    """B1: host case + .git suffix case must not split one remote; path kept."""

    def test_git_suffix_case_insensitive(self) -> None:
        self.assertEqual(
            project_registry.normalize_remote("https://github.com/acme/widgets.GIT"),
            project_registry.normalize_remote("https://github.com/acme/widgets"),
        )

    def test_host_case_insensitive(self) -> None:
        self.assertEqual(
            project_registry.normalize_remote("git@GitHub.com:acme/widgets.git"),
            project_registry.normalize_remote("git@github.com:acme/widgets.git"),
        )

    def test_path_case_is_preserved(self) -> None:
        # Distinct repos on a case-sensitive server must remain distinct.
        self.assertNotEqual(
            project_registry.normalize_remote("https://host.example/Team/Repo"),
            project_registry.normalize_remote("https://host.example/team/repo"),
        )


class ErrorContractTest(unittest.TestCase):
    """A2: business errors must be structured JSON + exit 2, not tracebacks."""

    def _resolve(self, base: Path, root: Path, repo: Path) -> None:
        subprocess.run(
            [sys.executable, str(RUNNER), "resolve", "--root", str(root), "--cwd", str(repo)],
            cwd=base, capture_output=True, check=True, text=True,
        )

    def test_check_with_invalid_date_returns_structured_error(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root, repo = base / "knowledge", base / "business"
            repo.mkdir(parents=True)
            self._resolve(base, root, repo)
            result = subprocess.run(
                [
                    sys.executable, str(RUNNER), "check",
                    "--root", str(root), "--cwd", str(repo),
                    "--today", "not-a-date",
                ],
                cwd=base, capture_output=True, check=False, text=True,
            )
            self.assertEqual(result.returncode, 2)
            payload = json.loads(result.stdout)
            self.assertIn("error", payload)


class RankerOverlapTest(unittest.TestCase):
    """A4: no-overlap queries must not return Current entries; recall preserved."""

    from datetime import date as _date

    def _request(self, **overrides: object):
        values: dict[str, object] = {
            "operation": "create", "scope": "project", "kind": "architecture",
            "knowledge_id": "order-retry-strategy",
            "title": "Order retry strategy",
            "body": "Kafka consumer must use an idempotency key on retries.",
            "evidence": ("src/order/retry.py:L1-L9",), "status": "current",
            "write_intent": "durable", "content_kind": "knowledge",
        }
        values.update(overrides)
        return CaptureRequest(**values)

    def _resolved(self, base: Path):
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import resolve
        repo = base / "repo"; repo.mkdir(); (repo / ".git").mkdir()
        return resolve(base / "knowledge", repo)

    def test_substring_only_query_does_not_match(self) -> None:
        from datetime import date
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
            capture, retrieve_context,
        )
        with TemporaryDirectory() as temp:
            resolved = self._resolved(Path(temp))
            capture(resolved, self._request(), date(2026, 7, 22))
            # "arch" is a substring of no meaningful token here; must return empty.
            found = retrieve_context(resolved, "zzzznomatch")
            self.assertEqual([], found["current_context"])

    def test_body_only_relevant_query_is_recalled(self) -> None:
        from datetime import date
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
            capture, retrieve_context,
        )
        with TemporaryDirectory() as temp:
            resolved = self._resolved(Path(temp))
            capture(resolved, self._request(), date(2026, 7, 22))
            # Kafka appears only in the body, not title/id/evidence.
            found = retrieve_context(resolved, "Kafka consumer")
            self.assertEqual(
                "order-retry-strategy", found["current_context"][0]["knowledge_id"]
            )

    def test_stopword_only_query_returns_empty(self) -> None:
        from datetime import date
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
            capture, retrieve_context,
        )
        with TemporaryDirectory() as temp:
            resolved = self._resolved(Path(temp))
            capture(resolved, self._request(), date(2026, 7, 22))
            found = retrieve_context(resolved, "the")
            self.assertEqual([], found["current_context"])


class SharedReadTest(unittest.TestCase):
    """A6: shared read returns correct bytes and does not block a writer."""

    def test_read_bytes_shared_returns_content(self) -> None:
        from plugins.tracebook.skills.tracebook.scripts.storage import read_bytes_shared
        with TemporaryDirectory() as temp:
            path = Path(temp) / "pointer.json"
            path.write_bytes(b'{"snapshot_id": "abc"}')
            self.assertEqual(b'{"snapshot_id": "abc"}', read_bytes_shared(path))

    def test_shared_read_survives_concurrent_pointer_replace(self) -> None:
        # A6's confirmed benefit: a lock-free reader opening a file that a writer
        # is concurrently replacing must not crash. A plain open() raises
        # PermissionError in that window on Windows; a share-delete open does
        # not. The writer relies on its pre-existing retry; a realistic read
        # cadence (small gap) lets both sides succeed deterministically.
        import threading
        import time as _time
        from plugins.tracebook.skills.tracebook.scripts import transaction
        from plugins.tracebook.skills.tracebook.scripts.storage import read_bytes_shared
        with TemporaryDirectory() as temp:
            base = Path(temp)
            target = base / "current.json"
            target.write_bytes(b'{"v": 0}')
            read_errors: list[Exception] = []
            write_errors: list[Exception] = []
            stop = threading.Event()

            def reader() -> None:
                while not stop.is_set():
                    try:
                        read_bytes_shared(target)
                    except Exception as error:  # noqa: BLE001
                        read_errors.append(error)
                        return
                    _time.sleep(0.001)

            def writer() -> None:
                for index in range(100):
                    staged = base / f"stage-{index}.tmp"
                    staged.write_bytes(f'{{"v": {index}}}'.encode())
                    try:
                        transaction._replace_target(target, staged, operation="test")
                    except Exception as error:  # noqa: BLE001
                        write_errors.append(error)
                        return

            reader_thread = threading.Thread(target=reader)
            writer_thread = threading.Thread(target=writer)
            reader_thread.start()
            writer_thread.start()
            writer_thread.join()
            stop.set()
            reader_thread.join()
            # Reader never crashes racing a replace — the core A6 guarantee.
            self.assertEqual([], read_errors)
            # Brief reads let the writer's retry win.
            self.assertEqual([], write_errors)


class OrphanStagingCleanupTest(unittest.TestCase):
    """C3: recover clears staged dirs that never reached a manifest."""

    def test_recover_removes_manifestless_staging(self) -> None:
        from plugins.tracebook.skills.tracebook.scripts import transaction
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import resolve
        with TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            resolve(base / "knowledge", repo)
            root = base / "knowledge"
            tx_dir = root / ".tracebook-state" / "transactions"
            tx_dir.mkdir(parents=True, exist_ok=True)
            orphan = tx_dir / "orphan-no-manifest"
            (orphan / "staged").mkdir(parents=True)
            (orphan / "staged" / "00000000.stage").write_bytes(b"partial")
            self.assertTrue(orphan.exists())

            transaction.recover_transactions(root)
            self.assertFalse(orphan.exists())


class InjectionGuardTest(unittest.TestCase):
    """C1: reject reserved structures in title/body; allow ordinary '---'."""

    def _resolved(self, base: Path):
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import resolve
        repo = base / "repo"; repo.mkdir(); (repo / ".git").mkdir()
        return resolve(base / "knowledge", repo)

    def _request(self, **overrides: object) -> CaptureRequest:
        values: dict[str, object] = {
            "operation": "create", "scope": "project", "kind": "architecture",
            "knowledge_id": "guard-check", "title": "Guard check",
            "body": "A durable architecture note.",
            "evidence": ("src/x.py:L1-L2",), "status": "current",
        }
        values.update(overrides)
        return CaptureRequest(**values)

    def test_body_with_horizontal_rule_is_allowed(self) -> None:
        from datetime import date
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import capture
        with TemporaryDirectory() as temp:
            resolved = self._resolved(Path(temp))
            result = capture(
                resolved,
                self._request(body="First section.\n\n---\n\nSecond section."),
                date(2026, 7, 22),
            )
            self.assertFalse(result.skipped)

    def test_multiline_title_is_rejected(self) -> None:
        from datetime import date
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import capture
        with TemporaryDirectory() as temp:
            resolved = self._resolved(Path(temp))
            with self.assertRaises(ValueError):
                capture(resolved, self._request(title="line one\nknowledge_id: evil"),
                        date(2026, 7, 22))

    def test_body_with_history_header_is_rejected(self) -> None:
        from datetime import date
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import capture
        with TemporaryDirectory() as temp:
            resolved = self._resolved(Path(temp))
            with self.assertRaises(ValueError):
                capture(resolved, self._request(body="text\n## History\nfake"),
                        date(2026, 7, 22))

    def test_body_with_event_marker_is_rejected(self) -> None:
        from datetime import date
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import capture
        with TemporaryDirectory() as temp:
            resolved = self._resolved(Path(temp))
            with self.assertRaises(ValueError):
                capture(resolved,
                        self._request(body="text <!-- tracebook:event:deadbeefdeadbeef -->"),
                        date(2026, 7, 22))


class PreflightBlockedTest(unittest.TestCase):
    """A7: preflight returns blocked/required_action for unregistered targets."""

    def test_unregistered_target_returns_blocked_with_argv(self) -> None:
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
            preflight,
        )
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()

            result = preflight(root, repo)

            self.assertTrue(result["blocked"])
            self.assertEqual("resolve_required", result["blocked_reason"])
            action = result["required_action"]
            self.assertEqual("resolve", action["name"])
            self.assertEqual("context-read-path", action["then"])
            argv = action["argv"]
            self.assertIsInstance(argv, list)
            self.assertEqual(sys.executable, argv[0])
            self.assertTrue(argv[1].endswith("tracebook_runner.py"))
            self.assertEqual("resolve", argv[2])
            self.assertEqual("--root", argv[3])
            self.assertEqual(str(root), argv[4])
            self.assertEqual("--cwd", argv[5])
            self.assertEqual(str(repo), argv[6])
            # Read-only contract: root not created
            self.assertFalse(root.exists())

    def test_registered_target_returns_not_blocked(self) -> None:
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
            preflight,
            resolve,
        )
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            resolve(root, repo)

            result = preflight(root, repo)

            self.assertTrue(result["registered"])
            self.assertFalse(result["blocked"])
            self.assertNotIn("blocked_reason", result)
            self.assertNotIn("required_action", result)

    def test_paths_with_spaces_preserve_argv_integrity(self) -> None:
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
            preflight,
        )
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "my knowledge root"
            repo = base / "my business repo"
            repo.mkdir()
            (repo / ".git").mkdir()

            result = preflight(root, repo)

            action = result["required_action"]
            argv = action["argv"]
            # Each path element must be exactly one complete string
            self.assertEqual(str(root), argv[4])
            self.assertEqual(str(repo), argv[6])
            # exe, script, resolve, --root, root, --cwd, cwd
            self.assertEqual(7, len(argv))

    def test_execute_resolve_action_then_preflight_returns_unblocked(self) -> None:
        from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import (
            preflight,
        )
        with TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "knowledge"
            repo = base / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()

            result1 = preflight(root, repo)
            self.assertTrue(result1["blocked"])

            subprocess.run(
                result1["required_action"]["argv"],
                check=True,
                capture_output=True,
                text=True,
            )

            result2 = preflight(root, repo)
            self.assertTrue(result2["registered"])
            self.assertFalse(result2["blocked"])
            self.assertIsNotNone(result2["project"])
            self.assertNotIn("required_action", result2)


if __name__ == "__main__":
    unittest.main()
