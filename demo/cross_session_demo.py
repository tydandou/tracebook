"""Run an isolated Tracebook capture-and-recall demonstration.

The demo uses the repository's real runner, creates both the business repository
and knowledge root under one temporary directory, and removes them on exit.
It never reads or writes the user's configured Tracebook root.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNNER = (
    REPOSITORY_ROOT
    / "plugins"
    / "tracebook"
    / "skills"
    / "tracebook"
    / "scripts"
    / "tracebook_runner.py"
)
KNOWLEDGE_ID = "refund-retry-policy"
FACT = "Refunds retry at most twice with a 3-second timeout."


def _run(*args: str, stdin: str | None = None) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        [sys.executable, str(RUNNER), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Runner command failed ({' '.join(args)}):\n"
            f"{completed.stderr or completed.stdout}"
        )
    return json.loads(completed.stdout)


def run_demo() -> dict[str, Any]:
    with TemporaryDirectory(prefix="tracebook-demo-") as temporary:
        base = Path(temporary).resolve()
        knowledge_root = base / "knowledge"
        project = base / "refund-service"
        source = project / "src"
        source.mkdir(parents=True)
        (project / ".git").mkdir()
        (source / "refunds.py").write_text(
            "MAX_RETRIES = 2\n"
            "TIMEOUT_SECONDS = 3\n\n"
            "def retry_allowed(attempt: int) -> bool:\n"
            "    return attempt < MAX_RETRIES\n",
            encoding="utf-8",
        )

        preflight = _run(
            "preflight", "--root", str(knowledge_root), "--cwd", str(project)
        )
        if not preflight.get("blocked"):
            raise RuntimeError("New demo project unexpectedly started as registered")

        resolved = _run(
            "resolve", "--root", str(knowledge_root), "--cwd", str(project)
        )

        capture_request = {
            "operation": "create",
            "knowledge_id": KNOWLEDGE_ID,
            "scope": "project",
            "kind": "business-rule",
            "status": "current",
            "title": "Refund retry policy",
            "body": FACT,
            "evidence": ["src/refunds.py:L1-L5"],
        }
        capture = _run(
            "capture",
            "--root",
            str(knowledge_root),
            "--cwd",
            str(project),
            "--request",
            "-",
            stdin=json.dumps(capture_request),
        )

        check_args = [
            "check",
            "--root",
            str(knowledge_root),
            "--cwd",
            str(project),
            "--source-root",
            str(project),
            "--scope",
            str(capture["health_scope"]),
        ]
        for changed_path in capture["changed_paths"]:
            check_args.extend(("--changed", changed_path))
        for new_path in capture["new_paths"]:
            check_args.extend(("--new-path", new_path))
        check = _run(*check_args)

        recalled = _run(
            "context-read-path",
            "--root",
            str(knowledge_root),
            "--cwd",
            str(project),
            "--query",
            "refund retry timeout",
        )
        matches = [
            item
            for item in recalled.get("current_context", [])
            if item.get("knowledge_id") == KNOWLEDGE_ID
        ]
        if not matches:
            raise RuntimeError("Session 2 did not retrieve the captured policy")

        return {
            "session_1": {
                "project_id": resolved["project"]["project_id"],
                "knowledge_id": KNOWLEDGE_ID,
                "status": "current",
                "fact": FACT,
                "evidence": capture_request["evidence"],
            },
            "verification": {
                "check_type": check["check_type"],
                "broken_links": "### Broken Links\n\n- None" in check["report"],
                "missing_sources": "### Missing Sources\n\n- None" in check["report"],
            },
            "session_2": {
                "query": "refund retry timeout",
                "recalled_knowledge_id": matches[0]["knowledge_id"],
                "fact": FACT,
            },
            "result": "cross-session retrieval verified",
            "cleanup": "temporary business repository and knowledge root removed on exit",
        }


def _print_human(result: dict[str, Any]) -> None:
    print("SESSION 1  verified refund retry policy")
    print(
        "CAPTURE    "
        f"{result['session_1']['knowledge_id']} | "
        f"{result['session_1']['status']} | evidence attached"
    )
    health = result["verification"]
    health_summary = (
        "no broken links or missing sources"
        if health["broken_links"] and health["missing_sources"]
        else "review health report"
    )
    print(f"CHECK      {health['check_type']} | {health_summary}")
    print()
    print(f"SESSION 2  query: {result['session_2']['query']}")
    print(f"RECALLED   {result['session_2']['recalled_knowledge_id']}")
    print(f"FACT       {result['session_2']['fact']}")
    print()
    print(f"RESULT     {result['result']}")
    print(f"CLEANUP    {result['cleanup']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON output."
    )
    args = parser.parse_args()

    result = run_demo()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
