"""Executable closeout example: check an existing capture receipt, never capture.

Read a UTF-8 JSON receipt (or the existing ASCII envelope) from stdin. Health
commands may persist reports; failures never roll back or retry the prior write.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
import subprocess
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from request_transport import MAX_REQUEST_BYTES, decode_request  # noqa: E402


def validate_receipt(receipt, root):
    if not isinstance(receipt, dict) or "error" in receipt:
        raise ValueError("Expected a successful capture response, not a request or error")
    if type(receipt.get("skipped")) is not bool:
        raise ValueError("Missing or invalid skipped")
    if receipt.get("health_scope") not in ("project", "domain", "pattern"):
        raise ValueError("Missing or invalid health_scope; no default is safe")
    for key in ("changed_paths", "new_paths"):
        values = receipt.get(key)
        if not isinstance(values, list):
            raise ValueError(f"Missing or invalid {key}")
        for value in values:
            if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
                raise ValueError(f"Invalid path in {key}")
            path = Path(value)
            if not path.is_absolute() or not path.resolve().is_relative_to(root):
                raise ValueError(f"{key} must contain absolute paths inside the specified root")
    if not set(receipt["new_paths"]).issubset(receipt["changed_paths"]):
        raise ValueError("new_paths must be included in changed_paths")
    if receipt["skipped"] and (receipt["changed_paths"] or receipt["new_paths"]):
        raise ValueError("Skipped capture unexpectedly reports changed paths")
    if not receipt["skipped"] and not receipt["changed_paths"]:
        raise ValueError("Non-skipped capture has no changed paths")
    warnings = receipt.get("warnings", [])
    if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
        raise ValueError("Invalid warnings")


def run_health(argv, timeout):
    try:
        process = subprocess.run(argv, capture_output=True, timeout=timeout, shell=False)
    except subprocess.TimeoutExpired:
        return {"state": "failed", "phase": "timeout",
                "error": "Health command timed out; persisted progress is unknown. Do not replay capture."}
    except OSError as error:
        return {"state": "failed", "phase": "process_start", "error": str(error)}
    result = {"state": "failed", "returncode": process.returncode,
              "stderr": process.stderr.decode("utf-8", errors="replace")}
    try:
        response = json.loads(process.stdout.decode("utf-8"))
    except (ValueError, UnicodeError):
        result.update(phase="response_decode", error="Runner did not return UTF-8 JSON",
                      stdout=process.stdout.decode("utf-8", errors="replace"))
        return result
    result["response"] = response
    if process.returncode != 0:
        result["phase"] = "runner"
    elif (not isinstance(response, dict) or "error" in response
          or not isinstance(response.get("findings"), dict)
          or not isinstance(response.get("report"), str)
          or (argv[3] == "check" and response.get("check_type") not in
              ("Local", "Light", "Regular", "Deep"))):
        result.update(phase="response_contract", error="Incomplete health response")
    else:
        result["state"] = "completed"
    return result


def verify(receipt, *, root, cwd, today, timeout=120):
    """Preserve capture/check/audit outcomes separately, including partial success."""
    result = {"capture": receipt, "verification": "incomplete",
              "check": {"state": "not_run"}, "audit": {"state": "not_run"}}
    try:
        root, cwd = Path(root).resolve(), Path(cwd).resolve()
        date.fromisoformat(today)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        if not root.is_dir() or not cwd.is_dir():
            raise ValueError("root and cwd must be existing directories from the capture")
        validate_receipt(receipt, root)
    except (ValueError, OSError, TypeError, RuntimeError) as error:
        result.update(phase="receipt_validation", error=str(error))
        return result
    if receipt["skipped"]:
        result["verification"] = "skipped_no_new_write"
        return result
    common = ["--root", str(root), "--cwd", str(cwd), "--source-root", str(cwd),
              "--today", today, "--scope", receipt["health_scope"]]
    argv = [sys.executable, "-B", str(SCRIPTS / "tracebook_runner.py"), "check", *common]
    for key, flag in (("changed_paths", "--changed"), ("new_paths", "--new-path")):
        for path in receipt[key]:
            argv.extend((flag, path))
    result["check"] = run_health(argv, timeout)
    if result["check"]["state"] != "completed":
        return result
    if result["check"]["response"]["check_type"] == "Deep":
        result["audit"] = run_health(
            [sys.executable, "-B", str(SCRIPTS / "tracebook_runner.py"), "audit", *common], timeout)
        if result["audit"]["state"] != "completed":
            return result
    result["verification"] = "completed"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    try:
        # A receipt may legitimately contain capture's intentional encoding override.
        receipt = decode_request(sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1),
                                 allow_suspicious=True).payload
    except ValueError as error:
        result = {"verification": "incomplete", "phase": "receipt_transport",
                  "error": str(error), "capture": "unknown",
                  "check": {"state": "not_run"}, "audit": {"state": "not_run"}}
    else:
        result = verify(receipt, root=args.root, cwd=args.cwd,
                        today=args.today, timeout=args.timeout)
    # ASCII JSON is lossless even through a legacy Windows console/pipeline.
    print(json.dumps(result, ensure_ascii=True))
    return 2 if result["verification"] == "incomplete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
