"""Emit safe lifecycle reminders for the Tracebook Codex plugin."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any


START_MESSAGE = (
    "Tracebook workflow: if this is nontrivial software-repository work "
    "(analysis, debugging, review, code/config changes, tests, builds, "
    "deployment, CI/CD, or incident diagnosis), invoke the Tracebook Skill "
    "and resolve/read its minimal external context before proceeding. Before "
    "the final response, capture and check only new, verified, durable "
    "knowledge, or report exactly one skip reason: not-project-work, "
    "no-durable-conclusion, unverified, already-known, or user-disabled. An "
    "explicit no-write request disables capture, not relevant read-only context."
)

STOP_MESSAGE = (
    "Tracebook final gate: ensure the response reports either the verified "
    "capture plus health-check result, or one controlled skip reason "
    "(not-project-work, no-durable-conclusion, unverified, already-known, "
    "user-disabled). Do not capture raw logs, temporary answers, or inference."
)


def _read_payload() -> dict[str, Any] | None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _inside_git_work_tree(cwd: object) -> bool:
    if not isinstance(cwd, str) or not cwd.strip():
        return False
    directory = Path(cwd)
    if not directory.is_dir():
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--is-inside-work-tree"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def build_output(payload: dict[str, Any]) -> dict[str, object] | None:
    """Return a non-blocking Hook response only for Git repository work."""
    if not _inside_git_work_tree(payload.get("cwd")):
        return None
    event = payload.get("hook_event_name")
    if event == "UserPromptSubmit":
        return {"continue": True, "systemMessage": START_MESSAGE}
    if event == "Stop":
        return {"continue": True, "systemMessage": STOP_MESSAGE}
    return None


def main() -> int:
    payload = _read_payload()
    if payload is None:
        return 0
    output = build_output(payload)
    if output is not None:
        json.dump(output, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
