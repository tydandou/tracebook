"""Validate, route, and persist governed Tracebook capture requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from .project_registry import ProjectRecord


@dataclass(frozen=True)
class CaptureRequest:
    scope: str
    kind: str
    category: str
    title: str
    body: str
    evidence: tuple[str, ...] = ()
    status: str = "Current"
    write_intent: str = "durable"
    content_kind: str = "knowledge"
    replacement: str | None = None
    topic: str | None = None
    user_prohibits_write: bool = False


@dataclass(frozen=True)
class CaptureResult:
    changed_paths: tuple[Path, ...]
    new_paths: tuple[Path, ...] = ()
    skipped: bool = False
    health_scope: str | None = None
    event_id: str | None = None


PROJECT_DOCUMENTS = {
    "architecture": "architecture.md",
    "api": "api.md",
    "business-rule": "business-rules.md",
    "database": "database.md",
    "module": "modules.md",
    "source-map": "source-map.md",
    "terminology": "terminology.md",
}
CATEGORY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
LINE_SUFFIX = re.compile(r":L\d+(?:-L\d+)?$")
WINDOWS_ABSOLUTE = re.compile(r"^[a-zA-Z]:/")
EVENT_MARKER = "<!-- tracebook:event:{event_id} -->"


def _invalid_request(field: str, reason: str) -> ValueError:
    return ValueError(f"INVALID_REQUEST: {field} {reason}")


def _safe_category(category: str) -> str:
    if not isinstance(category, str) or CATEGORY.fullmatch(category) is None:
        raise _invalid_request("category", "is unsupported")
    return category


def _safe_relative_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    return not (
        not normalized
        or path.is_absolute()
        or WINDOWS_ABSOLUTE.match(normalized)
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


def validate_capture(request: CaptureRequest) -> None:
    """Validate capture structure and lexical evidence without filesystem I/O."""
    if request.write_intent != "durable":
        raise _invalid_request("write intent", "is unsupported")
    if request.content_kind != "knowledge":
        raise _invalid_request("content kind", "is unsupported")
    if request.status not in {
        "Current",
        "Pending",
        "Deprecated",
        "Superseded",
        "Historical",
    }:
        raise _invalid_request("status", f"is unsupported: {request.status}")
    if not isinstance(request.title, str) or not request.title.strip():
        raise _invalid_request("title", "must not be empty")
    if not isinstance(request.body, str) or not request.body.strip():
        raise _invalid_request("body", "must not be empty")
    if isinstance(request.evidence, str) or not isinstance(
        request.evidence, (tuple, list)
    ):
        raise _invalid_request("evidence", "must be a sequence")
    if request.status == "Current" and not request.evidence:
        raise _invalid_request("evidence", "is required for Current knowledge")
    for item in request.evidence:
        if not _valid_evidence(item):
            raise _invalid_request("evidence", f"is unclassified: {item!r}")

    category = _safe_category(request.category)
    if request.scope == "project":
        if request.kind in PROJECT_DOCUMENTS:
            if category != Path(PROJECT_DOCUMENTS[request.kind]).stem:
                raise _invalid_request(
                    "category",
                    "must match the project document kind",
                )
        elif request.kind not in {"decision", "synthesis"}:
            raise _invalid_request("kind", "is unsupported for project scope")
    elif request.scope == "domain":
        if request.kind != "domain":
            raise _invalid_request("kind", "is unsupported for domain scope")
    elif request.scope == "pattern":
        if request.kind != "pattern":
            raise _invalid_request("kind", "is unsupported for pattern scope")
    else:
        raise _invalid_request("scope", "is unsupported")

    if request.status == "Superseded" and not request.replacement:
        raise _invalid_request("replacement", "is required for Superseded knowledge")
    if request.replacement is not None:
        if not isinstance(request.replacement, str) or not _safe_relative_path(
            request.replacement.strip()
        ):
            raise _invalid_request("replacement", "must remain inside the knowledge root")


def capture_lock_name(record: ProjectRecord, request: CaptureRequest) -> str:
    """Return the future transaction lock scope without acquiring a lock."""
    if request.scope == "project":
        return f"capture-project-{_safe_category(record.slug)}"
    if request.scope in {"domain", "pattern"}:
        return f"capture-{request.scope}"
    raise _invalid_request("scope", "is unsupported")


def _project_directory(root: Path, record: ProjectRecord) -> Path:
    return root / record.relative_path


def _capture_destination(
    root: Path,
    record: ProjectRecord,
    request: CaptureRequest,
) -> tuple[Path, Path]:
    category = request.category
    if request.scope == "project":
        directory = _project_directory(root, record)
        if request.kind in PROJECT_DOCUMENTS:
            document = directory / PROJECT_DOCUMENTS[request.kind]
            split_directories = {
                "business-rule": "business-rules",
                "api": "api",
                "database": "database",
                "source-map": "source-map",
            }
            if (
                request.kind in split_directories
                and document.exists()
                and len(document.read_text(encoding="utf-8").splitlines()) > 300
            ):
                if not request.topic:
                    raise _invalid_request(
                        "topic",
                        "is required after the document exceeds 300 lines",
                    )
                document = (
                    directory
                    / split_directories[request.kind]
                    / f"{_safe_category(request.topic)}.md"
                )
        elif request.kind == "decision":
            document = directory / "decisions" / f"{category}.md"
        else:
            document = directory / "synthesis" / f"{category}.md"
        index = directory / "index.md"
    elif request.scope == "domain":
        document = root / "02-domain" / f"{category}.md"
        index = root / "02-domain" / "index.md"
    else:
        document = root / "03-patterns" / f"{category}.md"
        index = root / "03-patterns" / "index.md"

    if request.status in {"Deprecated", "Historical"}:
        if request.scope == "project":
            project = _project_directory(root, record)
            document = project / "archive" / document.relative_to(project)
        else:
            document = root / "99-archive" / request.scope / f"{category}.md"

    try:
        document.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise _invalid_request(
            "destination",
            "must remain inside the external root",
        ) from error
    return document, index


def _event_id(
    root: Path,
    record: ProjectRecord,
    destination: Path,
    request: CaptureRequest,
) -> str:
    canonical = {
        "project": record.identity,
        "destination": destination.resolve().relative_to(root.resolve()).as_posix(),
        "title": request.title,
        "body": request.body,
        "evidence": list(request.evidence),
        "status": request.status,
        "replacement": request.replacement,
    }
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _append_once(path: Path, text: str) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if text in current:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(current + text, encoding="utf-8")
    return True


def _requires_frontmatter(request: CaptureRequest) -> bool:
    return (
        request.scope in {"domain", "pattern"}
        or request.kind in {"decision", "synthesis"}
        or request.status in {"Deprecated", "Historical"}
    )


def _frontmatter_type(request: CaptureRequest) -> str:
    if request.kind == "decision":
        return "decision"
    if request.kind == "synthesis":
        return "synthesis"
    if request.scope == "pattern":
        return "pattern"
    return "knowledge"


def _frontmatter_status(status: str) -> str:
    return {
        "Current": "current",
        "Pending": "unconfirmed",
        "Deprecated": "deprecated",
        "Superseded": "superseded",
        "Historical": "historical",
    }[status]


def _with_frontmatter(
    current: str,
    request: CaptureRequest,
    today: date,
    owner_project: str,
) -> str:
    if not _requires_frontmatter(request):
        return current
    status = _frontmatter_status(request.status)
    if current.startswith("---\n"):
        current = re.sub(
            r"(?m)^status: .*$",
            f"status: {status}",
            current,
            count=1,
        )
        return re.sub(
            r"(?m)^updated: .*$",
            f"updated: {today.isoformat()}",
            current,
            count=1,
        )
    header = "\n".join(
        [
            "---",
            f"type: {_frontmatter_type(request)}",
            f"status: {status}",
            f"scope: {request.scope}",
            f"owner_project: {owner_project}",
            f"created: {today.isoformat()}",
            f"updated: {today.isoformat()}",
            "tags: []",
            "---",
            "",
        ]
    )
    return header + current


def _append_knowledge_entry(
    path: Path,
    text: str,
    request: CaptureRequest,
    today: date,
    owner_project: str,
) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    current = _with_frontmatter(current, request, today, owner_project)
    if text in current:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(current + text, encoding="utf-8")
    return True


def _append_project_log(path: Path, entry: str) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if entry in current:
        return False
    if "## Knowledge\n" not in current:
        if current and not current.endswith("\n"):
            current += "\n"
        current += "## Knowledge\n\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(current + entry, encoding="utf-8")
    return True


def capture_knowledge(
    root: Path,
    record: ProjectRecord,
    request: CaptureRequest,
    today: date,
) -> CaptureResult:
    """Persist a validated capture with a stable, destination-scoped event ID."""
    health_scope = request.scope
    if request.user_prohibits_write:
        return CaptureResult(
            changed_paths=(),
            new_paths=(),
            skipped=True,
            health_scope=health_scope,
            event_id=None,
        )

    validate_capture(request)
    root = root.expanduser().resolve()
    document, index = _capture_destination(root, record, request)
    event_id = _event_id(root, record, document, request)
    marker = EVENT_MARKER.format(event_id=event_id)
    if document.exists() and marker in document.read_text(encoding="utf-8"):
        return CaptureResult(
            changed_paths=(),
            new_paths=(),
            skipped=True,
            health_scope=health_scope,
            event_id=event_id,
        )

    evidence = list(request.evidence) or ["Pending evidence review"]
    entry_lines = [
        f"## {request.title}",
        "",
        request.body,
        "",
        f"Status: {request.status}",
        "",
        "Evidence:",
        *(f"- `{item}`" for item in evidence),
    ]
    if request.replacement:
        entry_lines.extend(["", f"Replacement: `{request.replacement}`"])
    entry_lines.extend(["", marker, ""])
    entry = "\n".join(entry_lines)

    changed: list[Path] = []
    new_paths: list[Path] = []
    document_is_new = not document.exists()
    if _append_knowledge_entry(document, entry, request, today, record.slug):
        changed.append(document)
        if document_is_new:
            new_paths.append(document)

    link = document.relative_to(index.parent).as_posix()
    index_entry = f"- [{request.category}]({link})\n"
    if _append_once(index, index_entry):
        changed.append(index)

    if request.scope == "project":
        project = _project_directory(root, record)
        status = project / "project-status.md"
        if _append_once(status, f"- {today.isoformat()}: {request.title}\n"):
            changed.append(status)
        log = project / "logs" / f"{today:%Y-%m}.md"
        log_entry = f"- {today.isoformat()}: {request.title}\n{marker}\n"
        if _append_project_log(log, log_entry):
            changed.append(log)

    return CaptureResult(
        changed_paths=tuple(changed),
        new_paths=tuple(new_paths),
        skipped=False,
        health_scope=health_scope,
        event_id=event_id,
    )
