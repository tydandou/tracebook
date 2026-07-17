import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import resolve


ChildResult = tuple[int | None, str, str]


class ConcurrentWritesTest(unittest.TestCase):
    @staticmethod
    def _cleanup_and_collect(
        processes: list[subprocess.Popen[str]],
        results: list[ChildResult | None],
    ) -> list[ChildResult]:
        for process in processes:
            if process.poll() is None:
                process.kill()
        for index, process in enumerate(processes):
            if results[index] is None:
                stdout, stderr = process.communicate()
                results[index] = (process.returncode, stdout, stderr)
        if any(result is None for result in results):
            raise AssertionError("failed to collect every child process")
        return [result for result in results if result is not None]

    @staticmethod
    def _format_results(results: list[ChildResult]) -> str:
        return "\n\n".join(
            f"child {index}: exit={returncode}\nstdout={stdout}\nstderr={stderr}"
            for index, (returncode, stdout, stderr) in enumerate(results)
        )

    def test_twenty_concurrent_resolves_retain_all_registry_records(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            repositories = base / "repositories"
            ready = base / "ready"
            repositories.mkdir()
            ready.mkdir()
            gate = base / "start"
            child = "\n".join(
                (
                    "import sys, time",
                    "from pathlib import Path",
                    "from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import main",
                    "gate, ready, root, repository = map(Path, sys.argv[1:5])",
                    "ready.touch()",
                    "deadline = time.monotonic() + 30",
                    "while not gate.exists():",
                    "    if time.monotonic() >= deadline:",
                    "        raise TimeoutError(f'barrier timed out: {gate}')",
                    "    time.sleep(0.01)",
                    "raise SystemExit(main(['resolve', '--root', str(root), '--cwd', str(repository)]))",
                )
            )
            processes: list[subprocess.Popen[str]] = []
            for index in range(20):
                repository = repositories / f"repo-{index:02d}"
                (repository / ".git").mkdir(parents=True)
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-c",
                            child,
                            str(gate),
                            str(ready / f"{index:02d}"),
                            str(root),
                            str(repository),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                )

            results: list[ChildResult | None] = [None] * len(processes)
            failure_reason: str | None = None
            try:
                ready_deadline = time.monotonic() + 30
                while len(list(ready.iterdir())) != 20:
                    ready_count = len(list(ready.iterdir()))
                    exited = [
                        index
                        for index, process in enumerate(processes)
                        if process.poll() is not None
                    ]
                    if exited:
                        failure_reason = (
                            "children exited before reaching barrier: "
                            f"ready={ready_count}, indexes={exited}"
                        )
                        break
                    if time.monotonic() >= ready_deadline:
                        failure_reason = (
                            "children timed out before reaching barrier: "
                            f"ready={ready_count}"
                        )
                        break
                    time.sleep(0.02)

                if failure_reason is None:
                    gate.touch()
                    completion_deadline = time.monotonic() + 60
                    for index, process in enumerate(processes):
                        remaining = completion_deadline - time.monotonic()
                        if remaining <= 0:
                            failure_reason = (
                                "children exceeded completion deadline before "
                                f"child {index}"
                            )
                            break
                        try:
                            stdout, stderr = process.communicate(timeout=remaining)
                        except subprocess.TimeoutExpired:
                            failure_reason = (
                                f"child {index} exceeded completion deadline"
                            )
                            break
                        results[index] = (process.returncode, stdout, stderr)
            finally:
                collected = self._cleanup_and_collect(processes, results)

            if failure_reason is not None:
                self.fail(
                    f"{failure_reason}\n\n{self._format_results(collected)}"
                )

            failures = [
                f"child {index}: exit={returncode}\nstdout={stdout}\nstderr={stderr}"
                for index, (returncode, stdout, stderr) in enumerate(collected)
                if returncode != 0
            ]
            self.assertEqual([], failures, "\n\n".join(failures))
            for returncode, stdout, stderr in collected:
                self.assertEqual(0, returncode, stderr)
                payload = json.loads(stdout)
                self.assertIn("project", payload)

            registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            self.assertEqual(1, registry["version"])
            self.assertEqual(20, len(registry["projects"]), registry)
            self.assertEqual(
                20,
                len({record["relative_path"] for record in registry["projects"].values()}),
            )

    def test_two_concurrent_captures_in_one_project_retain_both_events(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            repository = base / "business"
            (repository / ".git").mkdir(parents=True)
            context = resolve(root, repository)
            ready = base / "ready"
            ready.mkdir()
            gate = base / "start"
            requests = base / "requests"
            requests.mkdir()
            child = "\n".join(
                (
                    "import sys, time",
                    "from pathlib import Path",
                    "from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import main",
                    "gate, ready, root, repository, request = map(Path, sys.argv[1:6])",
                    "ready.touch()",
                    "deadline = time.monotonic() + 30",
                    "while not gate.exists():",
                    "    if time.monotonic() >= deadline:",
                    "        raise TimeoutError(f'barrier timed out: {gate}')",
                    "    time.sleep(0.01)",
                    "raise SystemExit(main(['capture', '--root', str(root), '--cwd', str(repository), '--request', str(request), '--today', '2026-07-13']))",
                )
            )
            processes: list[subprocess.Popen[str]] = []
            for index in range(2):
                request_path = requests / f"request-{index}.json"
                request_path.write_text(
                    json.dumps(
                        {
                            "scope": "project",
                            "kind": "business-rule",
                            "category": "business-rules",
                            "title": f"Concurrent rule {index}",
                            "body": f"Concurrent body {index} must be retained.",
                            "evidence": [f"src/rule-{index}.py:L1-L3"],
                            "status": "Current",
                            "write_intent": "durable",
                            "content_kind": "knowledge",
                        }
                    ),
                    encoding="utf-8",
                )
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-c",
                            child,
                            str(gate),
                            str(ready / str(index)),
                            str(root),
                            str(repository),
                            str(request_path),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                )

            results: list[ChildResult | None] = [None] * len(processes)
            failure_reason: str | None = None
            try:
                ready_deadline = time.monotonic() + 30
                while len(list(ready.iterdir())) != 2:
                    if any(process.poll() is not None for process in processes):
                        failure_reason = "a capture child exited before the barrier"
                        break
                    if time.monotonic() >= ready_deadline:
                        failure_reason = "capture children timed out before the barrier"
                        break
                    time.sleep(0.02)
                if failure_reason is None:
                    gate.touch()
                    for index, process in enumerate(processes):
                        try:
                            stdout, stderr = process.communicate(timeout=30)
                        except subprocess.TimeoutExpired:
                            failure_reason = f"capture child {index} timed out"
                            break
                        results[index] = (process.returncode, stdout, stderr)
            finally:
                collected = self._cleanup_and_collect(processes, results)

            if failure_reason is not None:
                self.fail(f"{failure_reason}\n\n{self._format_results(collected)}")
            failures = [
                f"child {index}: exit={returncode}\nstdout={stdout}\nstderr={stderr}"
                for index, (returncode, stdout, stderr) in enumerate(collected)
                if returncode != 0
            ]
            self.assertEqual([], failures, "\n\n".join(failures))
            payloads = [json.loads(stdout) for _, stdout, _ in collected]
            for payload in payloads:
                self.assertIn("event_id", payload)
            event_ids = {payload["event_id"] for payload in payloads}
            self.assertEqual(2, len(event_ids), payloads)

            project = context.root / context.record.relative_path
            document = (project / "business-rules.md").read_text(encoding="utf-8")
            index_content = (project / "index.md").read_text(encoding="utf-8")
            status = (project / "project-status.md").read_text(encoding="utf-8")
            log = (project / "logs" / "2026-07.md").read_text(encoding="utf-8")
            for index in range(2):
                self.assertIn(f"Concurrent rule {index}", document)
                self.assertIn(f"Concurrent rule {index}", status)
            for event_id in event_ids:
                marker = f"<!-- tracebook:event:{event_id} -->"
                self.assertEqual(1, document.count(marker))
                self.assertEqual(1, log.count(marker))
            self.assertEqual(1, index_content.count("(business-rules.md)"))
            self.assertEqual(1, status.count("<!-- tracebook:last-event:"))


if __name__ == "__main__":
    unittest.main()
