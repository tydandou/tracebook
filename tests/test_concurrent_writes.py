import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest


class ConcurrentWritesTest(unittest.TestCase):
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

            results: list[tuple[int, str, str]] = []
            try:
                ready_deadline = time.monotonic() + 30
                while len(list(ready.iterdir())) != 20:
                    exited = [process.returncode for process in processes if process.poll() is not None]
                    if exited or time.monotonic() >= ready_deadline:
                        self.fail(
                            "children failed to reach barrier: "
                            f"ready={len(list(ready.iterdir()))}, exited={exited}"
                        )
                    time.sleep(0.02)
                gate.touch()

                completion_deadline = time.monotonic() + 60
                for process in processes:
                    remaining = completion_deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(process.args, 60)
                    stdout, stderr = process.communicate(timeout=remaining)
                    results.append((process.returncode, stdout, stderr))
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                    process.communicate()

            failures = [
                f"child {index}: exit={returncode}\nstdout={stdout}\nstderr={stderr}"
                for index, (returncode, stdout, stderr) in enumerate(results)
                if returncode != 0
            ]
            self.assertEqual([], failures, "\n\n".join(failures))
            for returncode, stdout, stderr in results:
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


if __name__ == "__main__":
    unittest.main()
