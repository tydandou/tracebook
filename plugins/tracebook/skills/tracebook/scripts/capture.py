"""Validate, route, and persist governed Tracebook capture requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re

from .locking import file_lock
from .project_registry import ProjectRecord, project_lock_name
from .snapshots import prepare_project_snapshot_updates
from .transaction import commit_updates


@dataclass(frozen=True)
class CaptureRequest:
    scope: str
    kind: str
    title: str
    body: str
    category: str = "knowledge"
    evidence: tuple[str, ...] = ()
    status: str = "Current"
    write_intent: str = "durable"
    content_kind: str = "knowledge"
    replacement: str | None = None
    topic: str | None = None
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


PROJECT_DOCUMENTS = {
    "architecture": "architecture.md",
    "api": "api.md",
    "business-rule": "business-rules.md",
    "database": "database.md",
    "module": "modules.md",
    "source-map": "source-map.md",
    "terminology": "terminology.md",
}
SPLIT_DIRECTORIES = {
    "business-rule": "business-rules",
    "api": "api",
    "database": "database",
    "source-map": "source-map",
}
CATEGORY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
LINE_SUFFIX = re.compile(r":L\d+(?:-L\d+)?$")
SCHEME_OR_DRIVE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
EVENT_MARKER = "<!-- tracebook:event:{event_id} -->"
LAST_EVENT_MARKER = "<!-- tracebook:last-event:{event_id} -->"
LAST_EVENT_PATTERN = re.compile(r"<!-- tracebook:last-event:[0-9a-f]+ -->")
MANAGED_POINTER_MARKER = "<!-- tracebook:managed-pointer -->"
MANAGED_BACKLINK_MARKER = "<!-- tracebook:managed-pointer-backlink -->"
MANAGED_POINTER_TARGET = re.compile(
    r"(?m)^Managed Entity Authority: \[[^\]\n]+\]\(([^)\n]+)\)$"
)
MANAGED_BACKLINK_LINE = re.compile(r"(?m)^Managed Pointer:.*$")
MANAGED_BACKLINK_BLOCK = re.compile(
    r"\n*<!-- tracebook:managed-pointer-backlink -->\n"
    r"Managed Pointer: \[[^\]\n]+\]\(([^)\n]+)\)\n*"
)


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
    """Intent + evidence gate shared by legacy and schema-v2 write paths."""
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


def validate_capture(request: CaptureRequest) -> None:
    """Validate capture structure and lexical evidence without filesystem I/O."""
    _enforce_write_intent_and_evidence(request)
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

    if request.topic is not None and (
        not isinstance(request.topic, str)
        or CATEGORY.fullmatch(request.topic) is None
    ):
        raise _invalid_request("topic", "is unsupported")

    if request.status == "Superseded" and not request.replacement:
        raise _invalid_request("replacement", "is required for Superseded knowledge")
    if request.replacement is not None:
        if not isinstance(request.replacement, str) or not _safe_relative_path(
            request.replacement.strip()
        ):
            raise _invalid_request("replacement", "must remain inside the knowledge root")


def capture_lock_name(record: ProjectRecord, request: CaptureRequest) -> str:
    """Return the transaction lock scope without acquiring a lock."""
    if request.scope == "project":
        return project_lock_name(record)
    if request.scope in {"domain", "pattern"}:
        return request.scope
    raise _invalid_request("scope", "is unsupported")


def _project_directory(root: Path, record: ProjectRecord) -> Path:
    return root / record.relative_path


def _capture_destination(
    root: Path,
    record: ProjectRecord,
    request: CaptureRequest,
    *,
    allow_split: bool = True,
) -> tuple[Path, Path]:
    category = request.category
    if request.scope == "project":
        directory = _project_directory(root, record)
        if request.kind in PROJECT_DOCUMENTS:
            document = directory / PROJECT_DOCUMENTS[request.kind]
            if (
                allow_split
                and request.kind in SPLIT_DIRECTORIES
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
                    / SPLIT_DIRECTORIES[request.kind]
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
        "evidence": [
            _canonical_evidence_item(item) for item in request.evidence
        ],
        "status": request.status,
        "replacement": _canonical_replacement(request),
    }
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _canonical_evidence_item(item: str) -> str:
    value = item.strip()
    if value.startswith(
        ("http://", "https://", "test:", "command:", "human:")
    ):
        return value
    return value.replace("\\", "/")


def _canonical_replacement(request: CaptureRequest) -> str | None:
    if request.replacement is None:
        return None
    return request.replacement.strip().replace("\\", "/")


def _split_event_candidates(
    root: Path,
    record: ProjectRecord,
    request: CaptureRequest,
) -> tuple[Path, ...]:
    if request.scope != "project" or request.kind not in SPLIT_DIRECTORIES:
        return ()
    base, _ = _capture_destination(
        root,
        record,
        request,
        allow_split=False,
    )
    candidates = [base]
    if request.topic is not None:
        project = _project_directory(root, record)
        child = (
            project
            / SPLIT_DIRECTORIES[request.kind]
            / f"{request.topic}.md"
        )
        if request.status in {"Deprecated", "Historical"}:
            child = project / "archive" / child.relative_to(project)
        try:
            child.resolve().relative_to(root.resolve())
        except ValueError as error:
            raise _invalid_request(
                "destination",
                "must remain inside the external root",
            ) from error
        candidates.append(child)
    return tuple(candidates)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _append_once(current: str, text: str) -> str:
    return current if text in current else current + text


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


def _upsert_frontmatter_fields(
    current: str,
    fields: tuple[tuple[str, str], ...],
) -> str:
    frontmatter_end = current.find("\n---\n", 4)
    if frontmatter_end == -1:
        return current
    frontmatter = current[:frontmatter_end]
    for key, value in fields:
        pattern = rf"(?m)^{re.escape(key)}: .*$"
        replacement = f"{key}: {value}"
        if re.search(pattern, frontmatter):
            frontmatter = re.sub(
                pattern,
                replacement,
                frontmatter,
                count=1,
            )
        else:
            frontmatter += f"\n{replacement}"
    return frontmatter + current[frontmatter_end:]


def _with_frontmatter(
    current: str,
    request: CaptureRequest,
    today: date,
    owner_project: str,
) -> str:
    if not _requires_frontmatter(request):
        return current
    entity_page = request.kind in {"decision", "synthesis"}
    if current.startswith("---\n"):
        if not entity_page:
            return _upsert_frontmatter_fields(
                current,
                (("status", "current"),),
            )
        status = _frontmatter_status(request.status)
        return _upsert_frontmatter_fields(
            current,
            (
                ("status", status),
                ("updated", today.isoformat()),
            ),
        )
    status = _frontmatter_status(request.status) if entity_page else "current"
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


def _entity_title(current: str) -> str | None:
    for pattern in (r"(?m)^# (.+?)\s*$", r"(?m)^## (.+?)\s*$"):
        match = re.search(pattern, current)
        if match is not None:
            return match.group(1).strip()
    return None


def _validate_entity_title(current: str, request: CaptureRequest) -> None:
    if request.kind not in {"decision", "synthesis"}:
        return
    title = _entity_title(current)
    if title is not None and title != request.title.strip():
        raise _invalid_request(
            "title",
            f"must match the existing {request.kind} entity: {title!r}",
        )


def _entity_identity_paths(
    root: Path,
    record: ProjectRecord,
    request: CaptureRequest,
) -> tuple[Path, ...]:
    if request.kind not in {"decision", "synthesis"}:
        return ()
    project = _project_directory(root, record)
    directory = "decisions" if request.kind == "decision" else "synthesis"
    active = project / directory / f"{request.category}.md"
    archived = project / "archive" / active.relative_to(project)
    return active, archived


def _relative_markdown_link(root: Path, source: Path, target: Path) -> str:
    source_parent = source.parent.resolve().relative_to(root.resolve()).as_posix()
    target_relative = target.resolve().relative_to(root.resolve()).as_posix()
    return posixpath.relpath(target_relative, start=source_parent)


def _managed_pointer_content(root: Path, pointer: Path, authority: Path) -> str:
    link = _relative_markdown_link(root, pointer, authority)
    return (
        f"{MANAGED_POINTER_MARKER}\n\n"
        f"Managed Entity Authority: [{pointer.stem}]({link})\n\n"
        "Evidence:\n"
        "- `human: Tracebook managed pointer`\n"
    )


def _without_managed_backlink(content: str) -> str:
    return MANAGED_BACKLINK_BLOCK.sub("\n", content).rstrip() + "\n"


def _with_managed_backlink(
    root: Path,
    authority: Path,
    pointer: Path,
    content: str,
) -> str:
    content = _without_managed_backlink(content)
    link = _relative_markdown_link(root, authority, pointer)
    return (
        content.rstrip()
        + f"\n\n{MANAGED_BACKLINK_MARKER}\n"
        + f"Managed Pointer: [{pointer.stem}]({link})\n"
    )


def _pointer_target(root: Path, pointer: Path, content: str) -> Path | None:
    if MANAGED_POINTER_MARKER not in content:
        return None
    matches = MANAGED_POINTER_TARGET.findall(content)
    if (
        content.count(MANAGED_POINTER_MARKER) != 1
        or len(matches) != 1
        or content.startswith("---\n")
        or _entity_title(content) is not None
    ):
        raise _invalid_request("entity state", "contains a corrupt managed pointer")
    link = matches[0]
    if "\\" in link or SCHEME_OR_DRIVE.match(link) or PurePosixPath(link).is_absolute():
        raise _invalid_request("entity state", "contains a corrupt managed pointer")
    target = pointer.parent.joinpath(*PurePosixPath(link).parts).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise _invalid_request(
            "entity state",
            "contains a managed pointer outside the knowledge root",
        ) from error
    return target


def _managed_backlink_target(
    root: Path,
    authority: Path,
    content: str,
) -> Path | None:
    has_marker = MANAGED_BACKLINK_MARKER in content
    has_line = MANAGED_BACKLINK_LINE.search(content) is not None
    if not has_marker and not has_line:
        return None
    blocks = list(MANAGED_BACKLINK_BLOCK.finditer(content))
    if len(blocks) != 1:
        raise _invalid_request("entity state", "contains a corrupt managed backlink")
    block = blocks[0]
    before = content[: block.start()]
    after = content[block.end() :]
    if (
        MANAGED_BACKLINK_MARKER in before
        or MANAGED_BACKLINK_MARKER in after
        or MANAGED_BACKLINK_LINE.search(before) is not None
        or MANAGED_BACKLINK_LINE.search(after) is not None
    ):
        raise _invalid_request("entity state", "contains a corrupt managed backlink")
    link = block.group(1)
    if "\\" in link or SCHEME_OR_DRIVE.match(link) or PurePosixPath(link).is_absolute():
        raise _invalid_request("entity state", "contains a corrupt managed backlink")
    target = authority.parent.joinpath(*PurePosixPath(link).parts).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise _invalid_request(
            "entity state",
            "contains a managed backlink outside the knowledge root",
        ) from error
    return target


def _entity_storage_state(
    root: Path,
    record: ProjectRecord,
    request: CaptureRequest,
) -> tuple[Path, Path, Path | None, Path | None, dict[Path, str]]:
    active, archived = _entity_identity_paths(root, record, request)
    contents = {active: _read_text(active), archived: _read_text(archived)}
    entities: list[Path] = []
    pointers: list[Path] = []
    backlinks: dict[Path, Path | None] = {}
    for path, content in contents.items():
        if not content:
            continue
        pointer_target = _pointer_target(root, path, content)
        if pointer_target is not None:
            counterpart = archived if path == active else active
            if pointer_target != counterpart.resolve():
                raise _invalid_request(
                    "entity state",
                    "contains a managed pointer to the wrong authority",
                )
            pointers.append(path)
            continue
        if _entity_title(content) is None:
            raise _invalid_request("entity state", "contains an unrecognized page")
        _validate_entity_title(content, request)
        entities.append(path)
        backlinks[path] = _managed_backlink_target(root, path, content)

    if len(entities) > 1 or len(pointers) > 1:
        raise _invalid_request("entity state", "contains multiple authorities")
    if pointers and (not entities or pointers[0] == entities[0]):
        raise _invalid_request("entity state", "contains an orphan managed pointer")
    if entities:
        authority = entities[0]
        backlink = backlinks[authority]
        if pointers:
            if backlink is None:
                raise _invalid_request(
                    "entity state",
                    "is missing its managed backlink",
                )
            if backlink != pointers[0].resolve():
                raise _invalid_request(
                    "entity state",
                    "contains a managed backlink to the wrong pointer",
                )
        elif backlink is not None:
            raise _invalid_request(
                "entity state",
                "contains a managed backlink without a pointer",
            )
    return (
        active,
        archived,
        entities[0] if entities else None,
        pointers[0] if pointers else None,
        contents,
    )


def _entity_index_content(current: str, category: str, entry: str) -> str:
    existing = re.compile(rf"(?m)^- \[{re.escape(category)}\]\([^)\n]+\)\r?\n?")
    current = existing.sub("", current)
    if current and not current.endswith("\n"):
        current += "\n"
    return current + entry


def _knowledge_content(
    current: str,
    entry: str,
    request: CaptureRequest,
    today: date,
    owner_project: str,
) -> str:
    current = _with_frontmatter(current, request, today, owner_project)
    return _append_once(current, entry)


def _project_log_content(current: str, entry: str) -> str:
    if entry in current:
        return current
    if "## Knowledge\n" not in current:
        if current and not current.endswith("\n"):
            current += "\n"
        current += "## Knowledge\n\n"
    return current + entry


def _project_status_content(
    current: str,
    title: str,
    today: date,
    event_id: str,
) -> str:
    status_entry = f"- {today.isoformat()}: {title}\n"
    current = _append_once(current, status_entry)
    marker = LAST_EVENT_MARKER.format(event_id=event_id)
    if LAST_EVENT_PATTERN.search(current):
        return LAST_EVENT_PATTERN.sub(marker, current, count=1)
    if current and not current.endswith("\n"):
        current += "\n"
    return current + marker + "\n"


def _entry_text(
    request: CaptureRequest,
    event_id: str,
    owner_project: str,
) -> str:
    evidence = [
        _canonical_evidence_item(item) for item in request.evidence
    ] or ["Pending evidence review"]
    entry_lines = [
        f"## {request.title}",
        "",
        request.body,
        "",
        f"Status: {request.status}",
    ]
    if request.scope in {"domain", "pattern"}:
        entry_lines.extend(["", f"Owner Project: `{owner_project}`"])
    entry_lines.extend(
        [
            "",
            "Evidence:",
            *(f"- `{item}`" for item in evidence),
        ]
    )
    replacement = _canonical_replacement(request)
    if replacement:
        entry_lines.extend(["", f"Replacement: `{replacement}`"])
    entry_lines.extend(
        ["", EVENT_MARKER.format(event_id=event_id), ""]
    )
    return "\n".join(entry_lines)


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

    if request.operation is not None:
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

    validate_capture(request)
    root = root.expanduser().resolve()
    scope = capture_lock_name(record, request)
    with file_lock(root, scope, operation="capture"):
        for candidate in _split_event_candidates(root, record, request):
            candidate_event_id = _event_id(root, record, candidate, request)
            candidate_marker = EVENT_MARKER.format(event_id=candidate_event_id)
            if candidate_marker in _read_text(candidate):
                return CaptureResult(
                    changed_paths=(),
                    new_paths=(),
                    skipped=True,
                    health_scope=health_scope,
                    event_id=candidate_event_id,
                )

        document, index = _capture_destination(root, record, request)
        event_id = _event_id(root, record, document, request)
        marker = EVENT_MARKER.format(event_id=event_id)
        updates: dict[Path, str] = {}
        document_is_new = not document.exists()
        entry = _entry_text(request, event_id, record.identity)
        entity_page = request.kind in {"decision", "synthesis"}
        record_project_event = True
        if entity_page:
            (
                active,
                archived,
                authority,
                pointer,
                entity_contents,
            ) = _entity_storage_state(root, record, request)
            document_current = entity_contents[document]
            if authority == document and marker in document_current:
                return CaptureResult(
                    changed_paths=(),
                    new_paths=(),
                    skipped=True,
                    health_scope=health_scope,
                    event_id=event_id,
                )

            authority_current = entity_contents[authority] if authority else ""
            authority_current = (
                _without_managed_backlink(authority_current)
                if authority_current
                else authority_current
            )
            event_in_authority_history = marker in authority_current
            if event_in_authority_history:
                document_content = _with_frontmatter(
                    authority_current,
                    request,
                    today,
                    record.slug,
                )
            else:
                document_content = _knowledge_content(
                    authority_current,
                    entry,
                    request,
                    today,
                    record.slug,
                )
            if authority is not None and authority != document:
                record_project_event = not event_in_authority_history

            pointer_after = (
                authority
                if authority is not None and authority != document
                else pointer
            )
            if pointer_after is not None:
                document_content = _with_managed_backlink(
                    root,
                    document,
                    pointer_after,
                    document_content,
                )
            if document_content != document_current:
                updates[document] = document_content

            if authority is not None and authority != document:
                pointer_content = _managed_pointer_content(
                    root,
                    authority,
                    document,
                )
                if pointer_content != entity_contents[authority]:
                    updates[authority] = pointer_content
        else:
            document_current = _read_text(document)
            if marker in document_current:
                return CaptureResult(
                    changed_paths=(),
                    new_paths=(),
                    skipped=True,
                    health_scope=health_scope,
                    event_id=event_id,
                )
            document_content = _knowledge_content(
                document_current,
                entry,
                request,
                today,
                record.slug,
            )
            if document_content != document_current:
                updates[document] = document_content

        index_current = _read_text(index)
        link = document.relative_to(index.parent).as_posix()
        index_entry = f"- [{request.category}]({link})\n"
        index_content = (
            _entity_index_content(index_current, request.category, index_entry)
            if entity_page
            else _append_once(index_current, index_entry)
        )
        if index_content != index_current:
            updates[index] = index_content

        if request.scope == "project":
            project = _project_directory(root, record)
            status = project / "project-status.md"
            status_current = _read_text(status)
            status_content = _project_status_content(
                status_current,
                request.title,
                today,
                event_id,
            )
            if status_content != status_current:
                updates[status] = status_content

            if record_project_event:
                log = project / "logs" / f"{today:%Y-%m}.md"
                log_current = _read_text(log)
                log_entry = f"- {today.isoformat()}: {request.title}\n{marker}\n"
                log_content = _project_log_content(log_current, log_entry)
                if log_content != log_current:
                    updates[log] = log_content

        for target in updates:
            target.parent.mkdir(parents=True, exist_ok=True)
        transaction_updates = dict(updates)
        final_targets: tuple[Path, ...] = ()
        if request.scope == "project":
            snapshot_updates, pointer = prepare_project_snapshot_updates(
                root,
                record,
                updates,
                operation="capture",
            )
            transaction_updates.update(snapshot_updates)
            final_targets = (pointer,)
        commit_updates(
            root,
            scope,
            "capture",
            transaction_updates,
            final_targets=final_targets,
        )
        return CaptureResult(
            changed_paths=tuple(updates),
            new_paths=(document,) if document_is_new else (),
            skipped=False,
            health_scope=health_scope,
            event_id=event_id,
        )
