"""Validate and route governed Tracebook capture requests to the schema-v2 path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
import re

from .project_registry import ProjectRecord


@dataclass(frozen=True)
class CaptureRequest:
    scope: str
    kind: str
    title: str
    body: str
    evidence: tuple[str, ...] = ()
    status: str = "Current"
    write_intent: str = "durable"
    content_kind: str = "knowledge"
    user_prohibits_write: bool = False
    operation: str | None = None
    knowledge_id: str | None = None
    expected_version: int | None = None
    replacement_knowledge_id: str | None = None


@dataclass(frozen=True)
class CaptureResult:
    changed_paths: tuple[Path, ...]
    new_paths: tuple[Path, ...] = ()
    skipped: bool = False
    health_scope: str | None = None
    event_id: str | None = None


LINE_SUFFIX = re.compile(r":L\d+(?:-L\d+)?$")
SCHEME_OR_DRIVE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _invalid_request(field: str, reason: str) -> ValueError:
    return ValueError(f"INVALID_REQUEST: {field} {reason}")


def _safe_relative_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    return not (
        not normalized
        or path.is_absolute()
        or SCHEME_OR_DRIVE.match(normalized)
        or ".." in path.parts
    )


def _valid_evidence(item: object) -> bool:
    if not isinstance(item, str):
        return False
    value = item.strip()
    if not value:
        return False
    if value.startswith(("http://", "https://")):
        return True
    for prefix in ("test:", "command:", "human:"):
        if value.startswith(prefix):
            return bool(value[len(prefix) :].strip())

    source = LINE_SUFFIX.sub("", value).replace("\\", "/")
    if not _safe_relative_path(source):
        return False
    filename = PurePosixPath(source).name
    return "/" in source or "." in filename


def _enforce_write_intent_and_evidence(request: CaptureRequest) -> None:
    """Intent + evidence gate for the schema-v2 write path."""
    if request.write_intent != "durable":
        raise _invalid_request("write intent", "is unsupported")
    if request.content_kind != "knowledge":
        raise _invalid_request("content kind", "is unsupported")
    if isinstance(request.evidence, str) or not isinstance(
        request.evidence, (tuple, list)
    ):
        raise _invalid_request("evidence", "must be a sequence")
    if isinstance(request.status, str) and request.status.strip().casefold() == "current":
        if not request.evidence:
            raise _invalid_request("evidence", "is required for Current knowledge")
    for item in request.evidence:
        if not _valid_evidence(item):
            raise _invalid_request("evidence", f"is unclassified: {item!r}")


def capture_knowledge(
    root: Path,
    record: ProjectRecord,
    request: CaptureRequest,
    today: date,
) -> CaptureResult:
    """Enforce the write gate, then persist through the schema-v2 entity path."""
    health_scope = request.scope
    if request.user_prohibits_write:
        return CaptureResult(
            changed_paths=(),
            new_paths=(),
            skipped=True,
            health_scope=health_scope,
            event_id=None,
        )

    _enforce_write_intent_and_evidence(request)
    from .knowledge_entity import capture_entity

    result = capture_entity(root.expanduser().resolve(), record, request, today)
    return CaptureResult(
        changed_paths=result.changed_paths,
        new_paths=result.new_paths,
        skipped=result.skipped,
        health_scope=request.scope,
        event_id=result.event_id,
    )
