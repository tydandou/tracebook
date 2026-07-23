"""Schema-v2 authority pages and deterministic entity lifecycle operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re

from .locking import file_lock
from .project_registry import ProjectRecord, project_lock_name
from .snapshots import prepare_project_snapshot_updates
from .transaction import commit_updates


SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
EVENT = re.compile(r"<!-- tracebook:event:([0-9a-f]{16}) -->")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
CURRENT = re.compile(r"(?ms)^## Current\n\n(.*?)(?=\n## History\n|\Z)")


class EntityError(ValueError):
    pass


@dataclass(frozen=True)
class EntityResult:
    changed_paths: tuple[Path, ...]
    new_paths: tuple[Path, ...]
    skipped: bool
    event_id: str


def _error(field: str, message: str) -> EntityError:
    return EntityError(f"INVALID_REQUEST: {field} {message}")


def _status(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized not in {"current", "pending", "deprecated", "superseded"}:
        raise _error("status", "is unsupported")
    return normalized


def validate_request(request: object) -> None:
    for field in ("operation", "knowledge_id", "scope", "kind", "title", "body"):
        if not isinstance(getattr(request, field, None), str) or not getattr(request, field).strip():
            raise _error(field, "is required")
    if getattr(request, "operation") not in {"create", "revise", "change-status"}:
        raise _error("operation", "is unsupported")
    if SLUG.fullmatch(getattr(request, "knowledge_id")) is None:
        raise _error("knowledge_id", "must be a lowercase hyphenated slug")
    if getattr(request, "scope") not in {"project", "domain", "pattern"}:
        raise _error("scope", "is unsupported")
    if SLUG.fullmatch(getattr(request, "kind")) is None:
        raise _error("kind", "is unsupported")
    title = getattr(request, "title")
    if "\n" in title or "\r" in title:
        raise _error("title", "must be a single line")
    body = getattr(request, "body")
    if re.search(r"(?m)^##[ \t]+(History|Current)[ \t]*$", body):
        raise _error("body", "must not contain reserved section headers")
    if "<!-- tracebook:event:" in body or "<!-- tracebook:last-event:" in body:
        raise _error("body", "must not contain reserved event markers")
    status = _status(getattr(request, "status", "current"))
    evidence = getattr(request, "evidence", ())
    if isinstance(evidence, str) or not isinstance(evidence, (list, tuple)):
        raise _error("evidence", "must be a sequence")
    if status == "current" and not evidence:
        raise _error("evidence", "is required for Current knowledge")
    if getattr(request, "operation") != "create" and not isinstance(getattr(request, "expected_version", None), int):
        raise _error("expected_version", "is required for revise and change-status")
    replacement = getattr(request, "replacement_knowledge_id", None)
    if status == "superseded" and (not isinstance(replacement, str) or SLUG.fullmatch(replacement) is None):
        raise _error("replacement_knowledge_id", "is required for Superseded knowledge")


def entity_path(root: Path, record: ProjectRecord, request: object) -> Path:
    knowledge_id = getattr(request, "knowledge_id")
    if getattr(request, "scope") == "project":
        return root / record.relative_path / "knowledge" / getattr(request, "kind") / f"{knowledge_id}.md"
    base = "02-domain" if getattr(request, "scope") == "domain" else "03-patterns"
    return root / base / "knowledge" / f"{knowledge_id}.md"


def _index_path(root: Path, record: ProjectRecord, scope: str) -> Path:
    return root / (record.relative_path if scope == "project" else "02-domain" if scope == "domain" else "03-patterns") / "index.md"


def _front(content: str) -> dict[str, str]:
    match = FRONTMATTER.match(content)
    if match is None:
        raise _error("entity", "is missing schema-v2 frontmatter")
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip()
    return values


def _event_id(path: Path, request: object) -> str:
    payload = {
        "path": path.as_posix(), "operation": getattr(request, "operation"),
        "knowledge_id": getattr(request, "knowledge_id"), "title": getattr(request, "title"),
        "body": getattr(request, "body"), "evidence": [str(value).strip().replace("\\", "/") for value in getattr(request, "evidence", ())],
        "status": _status(getattr(request, "status", "current")),
        "replacement": getattr(request, "replacement_knowledge_id", None),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def _section(request: object, event_id: str) -> str:
    evidence = "\n".join(f"- `{item}`" for item in getattr(request, "evidence", ()))
    return f"{getattr(request, 'body').strip()}\n\nEvidence:\n{evidence}\n\n<!-- tracebook:event:{event_id} -->"


def _render(record: ProjectRecord, request: object, today: date, version: int, created: str, history: str, event_id: str) -> str:
    status = _status(getattr(request, "status", "current"))
    project = record.identity if getattr(request, "scope") == "project" else "null"
    replacement = getattr(request, "replacement_knowledge_id", None) or "null"
    fields = [
        "---", "schema_version: 2", f"type: {getattr(request, 'kind')}", f"scope: {getattr(request, 'scope')}",
        f"project: {project}", f"knowledge_id: {getattr(request, 'knowledge_id')}", f"title: {getattr(request, 'title').strip()}",
        f"status: {status}", f"version: {version}", f"created: {created}", f"updated: {today.isoformat()}",
        f"replacement_knowledge_id: {replacement}", "---", "", f"# {getattr(request, 'title').strip()}", "", "## Current", "",
        _section(request, event_id), "", "## History", "",
    ]
    return "\n".join(fields) + (history.strip() + "\n" if history.strip() else "")


def _existing_history(content: str, fields: dict[str, str]) -> str:
    current = CURRENT.search(content)
    if current is None:
        raise _error("entity", "is missing a Current section")
    version = fields.get("version")
    updated = fields.get("updated")
    if not version or not updated:
        raise _error("entity", "is missing version metadata")
    existing_history = content.split("## History\n", 1)[1] if "## History\n" in content else ""
    return f"### Version {version} — {updated}\n\n{current.group(1).strip()}\n\n" + existing_history.strip() + "\n"


def _index_content(root: Path, index: Path, page: Path, title: str) -> str:
    current = index.read_text(encoding="utf-8") if index.exists() else "# Knowledge Index\n\n"
    link = page.relative_to(index.parent).as_posix()
    entry = f"- [{title}]({link})"
    return current if entry in current else current.rstrip() + "\n" + entry + "\n"


def _project_status(current: str, request: object, today: date) -> str:
    entry = f"- {today.isoformat()}: {getattr(request, 'operation')} `{getattr(request, 'knowledge_id')}` v{getattr(request, 'title').strip()}"
    return current.rstrip() + "\n" + entry + "\n"


def _log(current: str, request: object, event_id: str, today: date) -> str:
    entry = f"## {today.isoformat()} knowledge\n\n- {getattr(request, 'operation')} `{getattr(request, 'knowledge_id')}` ({event_id})\n"
    return current.rstrip() + "\n\n" + entry


def capture_entity(root: Path, record: ProjectRecord, request: object, today: date) -> EntityResult:
    validate_request(request)
    path = entity_path(root, record, request)
    index = _index_path(root, record, getattr(request, "scope"))
    lock = project_lock_name(record) if getattr(request, "scope") == "project" else getattr(request, "scope")
    with file_lock(root, lock, operation="capture"):
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        event_id = _event_id(path.relative_to(root), request)
        if event_id in EVENT.findall(current):
            return EntityResult((), (), True, event_id)
        exists = bool(current)
        if getattr(request, "operation") == "create" and exists:
            raise _error("knowledge_id", "already exists; use revise")
        if getattr(request, "operation") != "create" and not exists:
            raise _error("knowledge_id", "does not exist; use create")
        if exists:
            fields = _front(current)
            if fields.get("schema_version") != "2" or fields.get("knowledge_id") != getattr(request, "knowledge_id"):
                raise _error("entity", "is not a matching schema-v2 authority")
            version = int(fields["version"])
            if getattr(request, "expected_version") != version:
                raise _error("expected_version", f"conflicts with current version {version}")
            created, history = fields["created"], _existing_history(current, fields)
            version += 1
        else:
            created, history, version = today.isoformat(), "", 1
        if _status(getattr(request, "status", "current")) == "superseded":
            replacement_path = path.with_name(f"{getattr(request, 'replacement_knowledge_id')}.md")
            if replacement_path == path or not replacement_path.exists():
                raise _error("replacement_knowledge_id", "must reference an existing entity in the same collection")
            replacement_status = _front(replacement_path.read_text(encoding="utf-8")).get("status")
            if replacement_status in {"deprecated", "superseded"}:
                raise _error("replacement_knowledge_id", "must reference an active entity")
        rendered = _render(record, request, today, version, created, history, event_id)
        updates = {path: rendered, index: _index_content(root, index, path, getattr(request, "title").strip())}
        if getattr(request, "scope") == "project":
            project = root / record.relative_path
            status = project / "project-status.md"
            log = project / "logs" / f"{today:%Y-%m}.md"
            updates[status] = _project_status(status.read_text(encoding="utf-8") if status.exists() else "# Project Status\n", request, today)
            updates[log] = _log(log.read_text(encoding="utf-8") if log.exists() else "# Project Log\n", request, event_id, today)
        for target in updates:
            target.parent.mkdir(parents=True, exist_ok=True)
        transaction_updates = dict(updates)
        final_targets: tuple[Path, ...] = ()
        if getattr(request, "scope") == "project":
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
            lock,
            "capture",
            transaction_updates,
            final_targets=final_targets,
        )
        return EntityResult(tuple(updates), (path,) if not exists else (), False, event_id)
