from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path, PurePosixPath
import re
import stat

from .errors import TracebookError
from .locking import file_lock
from .project_registry import ProjectRecord, _load_registry, registry_path
from .storage import confined_path, sha256_bytes, sha256_file
from .transaction import commit_updates


_AGGREGATE_START = "<!-- tracebook:health-aggregate:start -->"
_AGGREGATE_END = "<!-- tracebook:health-aggregate:end -->"
_ISSUES_START = "<!-- tracebook:generated-issues:start -->"
_ISSUES_END = "<!-- tracebook:generated-issues:end -->"
_MIGRATION_MANIFEST = ".tracebook-state/migrations/health-v1.json"
_LEGACY_SOURCE = "00-global/health/health-status.md"
_LEGACY_ARCHIVE = "00-global/health/archive/health-status-pre-v1.md"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PROJECT_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

_TEXT_FIELDS = (
    ("Scope", "scope"),
    ("Identity", "identity"),
)
_DATE_FIELDS = (
    ("Last Light Check", "last_light"),
    ("Last Regular Check", "last_regular"),
    ("Last Deep Check", "last_deep"),
)
_COUNT_FIELDS = (
    ("Changes Since Last Regular Check", "changes_since_regular"),
    ("New Pages Since Last Regular Check", "new_pages_since_regular"),
    ("Pending Confirmations", "pending_confirmations"),
    ("Missing Sources", "missing_sources"),
    ("Broken Links", "broken_links"),
    ("Orphan Pages", "orphan_pages"),
)


@dataclass
class HealthState:
    scope: str
    identity: str
    last_light: date | None = None
    last_regular: date | None = None
    last_deep: date | None = None
    changes_since_regular: int = 0
    new_pages_since_regular: int = 0
    pending_confirmations: int = 0
    missing_sources: int = 0
    broken_links: int = 0
    orphan_pages: int = 0
    risk_level: str = "Unknown"
    issues: tuple[str, ...] = ()


def _review_required(message: str, operation: str) -> TracebookError:
    return TracebookError(
        "HEALTH_MIGRATION_REVIEW_REQUIRED",
        message,
        operation,
    )


def _relative_path(root: Path, value: str, *, operation: str) -> Path:
    relative = PurePosixPath(value)
    if (
        not value
        or relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != value
    ):
        raise TracebookError(
            "PATH_OUTSIDE_ROOT",
            f"Health path {value!r} is not a confined relative POSIX path",
            operation,
        )
    return confined_path(
        root,
        root.joinpath(*relative.parts),
        operation=operation,
    )


def _project_slug(identity: str) -> str:
    if not isinstance(identity, str) or _PROJECT_SLUG.fullmatch(identity) is None:
        raise TracebookError(
            "PATH_OUTSIDE_ROOT",
            f"Project health identity {identity!r} is not one portable slug",
            "health",
        )
    return identity


def health_path(root: Path, scope: str, identity: str) -> Path:
    resolved_root = root.resolve()
    if scope == "project":
        relative = f"01-projects/{_project_slug(identity)}/health-status.md"
    elif scope in {"domain", "pattern"} and identity == scope:
        relative = f"00-global/health/scopes/{scope}-status.md"
    else:
        raise ValueError(f"Unsupported health scope/identity: {scope}/{identity}")
    return _relative_path(resolved_root, relative, operation="health")


def health_log_path(root: Path, scope: str, identity: str, month: date) -> Path:
    resolved_root = root.resolve()
    if scope == "project":
        relative = (
            f"01-projects/{_project_slug(identity)}/health-logs/{month:%Y-%m}.md"
        )
    elif scope in {"domain", "pattern"} and identity == scope:
        relative = f"00-global/health/logs/{scope}/{month:%Y-%m}.md"
    else:
        raise ValueError(f"Unsupported health scope/identity: {scope}/{identity}")
    return _relative_path(resolved_root, relative, operation="health")


def _managed_value(content: str, label: str) -> str | None:
    match = re.search(rf"(?m)^- {re.escape(label)}:\s*(.*?)[ \t]*$", content)
    return match.group(1) if match else None


def _parse_date(value: str | None) -> date | None:
    if value in {None, "", "Not run"}:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_count(value: str | None) -> int:
    if value is None or re.fullmatch(r"\d+", value) is None:
        return 0
    return int(value)


def _risk_level(content: str) -> str:
    match = re.search(
        r"(?m)^## Current Risk Level[ \t]*\n+([^\n]+?)[ \t]*$",
        content,
    )
    return match.group(1).strip() if match else "Unknown"


def _generated_issues(content: str) -> tuple[str, ...]:
    match = re.search(
        rf"(?s){re.escape(_ISSUES_START)}(.*?){re.escape(_ISSUES_END)}",
        content,
    )
    if match is None:
        return ()
    issues: list[str] = []
    for line in match.group(1).splitlines():
        if line.startswith("- "):
            issues.append(line[2:])
    return tuple(issues)


def load_health_state(path: Path) -> HealthState:
    content = path.read_text(encoding="utf-8")
    values: dict[str, object] = {}
    for label, field in _TEXT_FIELDS:
        values[field] = _managed_value(content, label) or ""
    for label, field in _DATE_FIELDS:
        values[field] = _parse_date(_managed_value(content, label))
    for label, field in _COUNT_FIELDS:
        values[field] = _parse_count(_managed_value(content, label))
    values["risk_level"] = _risk_level(content)
    values["issues"] = _generated_issues(content)
    return HealthState(**values)


def _date_text(value: date | None) -> str:
    return value.isoformat() if value is not None else "Not run"


def _fresh_health_page(state: HealthState) -> str:
    return "\n".join(
        [
            "# Scoped Knowledge Health",
            "",
            "## Current Status",
            "",
            f"- Scope: {state.scope}",
            f"- Identity: {state.identity}",
            f"- Last Light Check: {_date_text(state.last_light)}",
            f"- Last Regular Check: {_date_text(state.last_regular)}",
            f"- Last Deep Check: {_date_text(state.last_deep)}",
            f"- Changes Since Last Regular Check: {state.changes_since_regular}",
            f"- New Pages Since Last Regular Check: {state.new_pages_since_regular}",
            f"- Pending Confirmations: {state.pending_confirmations}",
            f"- Missing Sources: {state.missing_sources}",
            f"- Broken Links: {state.broken_links}",
            f"- Orphan Pages: {state.orphan_pages}",
            "",
            "## Current Risk Level",
            "",
            state.risk_level,
            "",
            "## Open Issues",
            "",
            _ISSUES_START,
            *(f"- {issue}" for issue in state.issues),
            _ISSUES_END,
            "",
        ]
    )


def _replace_managed_value(content: str, label: str, value: str) -> str:
    pattern = rf"(?m)^- {re.escape(label)}:.*$"
    replacement = f"- {label}: {value}"
    if re.search(pattern, content):
        return re.sub(pattern, lambda _: replacement, content, count=1)
    return content


def render_health_state(
    state: HealthState,
    existing_content: str | None = None,
) -> str:
    if existing_content is None:
        return _fresh_health_page(state)

    content = existing_content
    rendered_values: tuple[tuple[str, str], ...] = (
        ("Scope", state.scope),
        ("Identity", state.identity),
        ("Last Light Check", _date_text(state.last_light)),
        ("Last Regular Check", _date_text(state.last_regular)),
        ("Last Deep Check", _date_text(state.last_deep)),
        ("Changes Since Last Regular Check", str(state.changes_since_regular)),
        ("New Pages Since Last Regular Check", str(state.new_pages_since_regular)),
        ("Pending Confirmations", str(state.pending_confirmations)),
        ("Missing Sources", str(state.missing_sources)),
        ("Broken Links", str(state.broken_links)),
        ("Orphan Pages", str(state.orphan_pages)),
    )
    for label, value in rendered_values:
        content = _replace_managed_value(content, label, value)

    risk_pattern = r"(?m)(^## Current Risk Level[ \t]*\n+)([^\n]+?)[ \t]*$"
    if re.search(risk_pattern, content):
        content = re.sub(
            risk_pattern,
            lambda match: f"{match.group(1)}{state.risk_level}",
            content,
            count=1,
        )

    issues = "\n".join(
        [_ISSUES_START, *(f"- {issue}" for issue in state.issues), _ISSUES_END]
    )
    issue_pattern = rf"(?s){re.escape(_ISSUES_START)}.*?{re.escape(_ISSUES_END)}"
    if re.search(issue_pattern, content):
        content = re.sub(issue_pattern, lambda _: issues, content, count=1)
    elif "## Open Issues" in content:
        content = content.replace("## Open Issues", f"## Open Issues\n\n{issues}", 1)
    return content


def _registered_projects(root: Path) -> tuple[ProjectRecord, ...]:
    records = _load_registry(registry_path(root), root)
    return tuple(records[identity] for identity in sorted(records))


def _default_states(projects: tuple[ProjectRecord, ...]) -> tuple[HealthState, ...]:
    return (
        HealthState(scope="domain", identity="domain"),
        HealthState(scope="pattern", identity="pattern"),
        *(HealthState(scope="project", identity=record.identity) for record in projects),
    )


def _state_path(root: Path, state: HealthState, projects: tuple[ProjectRecord, ...]) -> Path:
    if state.scope != "project":
        return health_path(root, state.scope, state.identity)
    record = next(record for record in projects if record.identity == state.identity)
    return health_path(root, "project", record.slug)


def _loaded_states(root: Path, projects: tuple[ProjectRecord, ...]) -> tuple[HealthState, ...]:
    states: list[HealthState] = []
    for default in _default_states(projects):
        path = _state_path(root, default, projects)
        states.append(load_health_state(path) if path.is_file() else default)
    return tuple(states)


def _aggregate_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _render_aggregate(states: tuple[HealthState, ...]) -> str:
    lines = [
        "# Knowledge Health Status",
        "",
        "## Current Status",
        "",
        "- Last Light Check: Not run",
        "- Last Regular Check: Not run",
        "- Last Deep Check: Not run",
        "- Changes Since Last Regular Check: 0",
        "- New Pages Since Last Regular Check: 0",
        "- Pending Confirmations: 0",
        "- Missing Sources: 0",
        "- Broken Links: 0",
        "- Orphan Pages: 0",
        "",
        "## Current Risk Level",
        "",
        "Unknown",
        "",
        "## Open Issues",
        "",
        _ISSUES_START,
        _ISSUES_END,
        "",
        "## Scope Summary",
        "",
        _AGGREGATE_START,
        "| Scope | Identity | Last Light | Last Regular | Last Deep | Changes | New Pages | Pending | Missing | Broken | Orphans | Risk | Issues |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for state in states:
        values = (
            state.scope,
            state.identity,
            _date_text(state.last_light),
            _date_text(state.last_regular),
            _date_text(state.last_deep),
            str(state.changes_since_regular),
            str(state.new_pages_since_regular),
            str(state.pending_confirmations),
            str(state.missing_sources),
            str(state.broken_links),
            str(state.orphan_pages),
            state.risk_level,
            "; ".join(state.issues) or "None",
        )
        lines.append("| " + " | ".join(_aggregate_cell(value) for value in values) + " |")
    lines.extend([_AGGREGATE_END, ""])
    return "\n".join(lines)


def _ensure_parent_directories(paths: tuple[Path, ...]) -> None:
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)


def _migration_manifest(created: dict[Path, str], root: Path) -> str:
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "initial_sha256": sha256_bytes(content.encode("utf-8")),
        }
        for path, content in sorted(
            created.items(),
            key=lambda item: item[0].relative_to(root).as_posix(),
        )
    ]
    payload = {
        "version": 1,
        "source": _LEGACY_SOURCE,
        "archive": _LEGACY_ARCHIVE,
        "created": entries,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _regular_file(path: Path, *, operation: str) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(mode):
        raise _review_required(f"Expected a regular health file at {path}", operation)
    return True


def _ensure_layout_under_maintenance(root: Path) -> tuple[Path, ...]:
    projects = _registered_projects(root)
    source = _relative_path(root, _LEGACY_SOURCE, operation="health-migration")
    archive = _relative_path(root, _LEGACY_ARCHIVE, operation="health-migration")
    manifest_path = _relative_path(
        root,
        _MIGRATION_MANIFEST,
        operation="health-migration",
    )
    source_exists = _regular_file(source, operation="health-migration")
    source_bytes = source.read_bytes() if source_exists else b""
    is_legacy = source_exists and _AGGREGATE_START.encode("utf-8") not in source_bytes

    defaults = _default_states(projects)
    created: dict[Path, str] = {}
    for state in defaults:
        path = _state_path(root, state, projects)
        if not _regular_file(path, operation="health-migration"):
            created[path] = render_health_state(state)

    states = tuple(
        load_health_state(_state_path(root, default, projects))
        if _state_path(root, default, projects).is_file()
        else default
        for default in defaults
    )
    aggregate = _render_aggregate(states)

    if is_legacy:
        if manifest_path.exists() or manifest_path.is_symlink():
            raise _review_required(
                f"Refusing to overwrite existing migration manifest {manifest_path}",
                "health-migration",
            )
        archive_exists = _regular_file(archive, operation="health-migration")
        if archive_exists and archive.read_bytes() != source_bytes:
            raise _review_required(
                f"Refusing to overwrite inconsistent legacy archive {archive}",
                "health-migration",
            )
        try:
            legacy_content = source_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise _review_required(
                f"Legacy health source is not UTF-8: {source}: {error}",
                "health-migration",
            ) from None
        if not archive_exists:
            created[archive] = legacy_content
        updates = dict(created)
        updates[source] = aggregate
        updates[manifest_path] = _migration_manifest(created, root)
        _ensure_parent_directories(tuple(updates))
        return commit_updates(
            root,
            "health-aggregate",
            "health-migration",
            updates,
        )

    updates = dict(created)
    if not source_exists:
        updates[source] = aggregate
    _ensure_parent_directories(tuple(updates))
    transaction_scope = "health-aggregate" if source in updates else "health-layout"
    return commit_updates(root, transaction_scope, "health-layout", updates)


def ensure_health_layout(
    root: Path,
    project: ProjectRecord | None = None,
) -> tuple[Path, ...]:
    resolved_root = root.resolve()
    if project is not None:
        expected_relative = PurePosixPath(project.relative_path)
        if (
            len(expected_relative.parts) != 2
            or expected_relative.parts[0] != "01-projects"
            or expected_relative.parts[1] != project.slug
        ):
            raise TracebookError(
                "PATH_OUTSIDE_ROOT",
                f"Project health record path is not confined: {project.relative_path}",
                "resolve",
            )
        path = health_path(resolved_root, "project", project.slug)
        if _regular_file(path, operation="resolve"):
            return ()
        content = render_health_state(
            HealthState(scope="project", identity=project.identity)
        )
        _ensure_parent_directories((path,))
        return commit_updates(
            resolved_root,
            f"project-{project.slug}",
            "resolve",
            {path: content},
        )

    with file_lock(resolved_root, "maintenance", operation="health-migration"):
        with file_lock(
            resolved_root,
            "health-aggregate",
            operation="health-migration",
        ):
            return _ensure_layout_under_maintenance(resolved_root)


def rebuild_global_health(root: Path) -> Path:
    resolved_root = root.resolve()
    with file_lock(resolved_root, "health-aggregate", operation="resolve"):
        target = _relative_path(resolved_root, _LEGACY_SOURCE, operation="resolve")
        manifest_path = _relative_path(
            resolved_root,
            _MIGRATION_MANIFEST,
            operation="resolve",
        )
        if target.is_file():
            current = target.read_bytes()
            if (
                _AGGREGATE_START.encode("utf-8") not in current
                and not manifest_path.exists()
            ):
                return target
        projects = _registered_projects(resolved_root)
        content = _render_aggregate(_loaded_states(resolved_root, projects))
        if target.is_file() and target.read_text(encoding="utf-8") == content:
            return target
        _ensure_parent_directories((target,))
        commit_updates(
            resolved_root,
            "health-aggregate",
            "resolve",
            {target: content},
        )
        return target


def _validated_manifest(root: Path, path: Path) -> tuple[Path, Path, tuple[tuple[Path, str], ...]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _review_required(f"Invalid health migration manifest {path}: {error}", "rollback") from None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "source", "archive", "created"}
        or payload["version"] != 1
        or payload["source"] != _LEGACY_SOURCE
        or payload["archive"] != _LEGACY_ARCHIVE
        or not isinstance(payload["created"], list)
    ):
        raise _review_required(f"Invalid health migration manifest {path}", "rollback")
    source = _relative_path(root, payload["source"], operation="rollback")
    archive = _relative_path(root, payload["archive"], operation="rollback")
    created: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for entry in payload["created"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "initial_sha256"}
            or not isinstance(entry["path"], str)
            or not isinstance(entry["initial_sha256"], str)
            or _SHA256.fullmatch(entry["initial_sha256"]) is None
        ):
            raise _review_required(f"Invalid created entry in {path}", "rollback")
        relative = PurePosixPath(entry["path"])
        allowed_namespace = entry["path"] in {
            "00-global/health/scopes/domain-status.md",
            "00-global/health/scopes/pattern-status.md",
        }
        allowed_archive = entry["path"] == _LEGACY_ARCHIVE
        allowed_project = (
            len(relative.parts) == 3
            and relative.parts[0] == "01-projects"
            and relative.parts[1] not in {"", ".", ".."}
            and relative.parts[2] == "health-status.md"
        )
        if not (allowed_archive or allowed_namespace or allowed_project):
            raise _review_required(
                f"Refusing unrecognized migration-created path {entry['path']}",
                "rollback",
            )
        target = _relative_path(root, entry["path"], operation="rollback")
        if target in seen:
            raise _review_required(f"Duplicate migration-created path {target}", "rollback")
        seen.add(target)
        created.append((target, entry["initial_sha256"]))
    return source, archive, tuple(created)


def rollback_health_migration(root: Path) -> tuple[Path, ...]:
    resolved_root = root.resolve()
    manifest_path = _relative_path(
        resolved_root,
        _MIGRATION_MANIFEST,
        operation="rollback",
    )
    with file_lock(resolved_root, "maintenance", operation="rollback"):
        with file_lock(
            resolved_root,
            "health-aggregate",
            operation="rollback",
        ):
            if not manifest_path.exists():
                return ()
            source, archive, created = _validated_manifest(resolved_root, manifest_path)
            if not _regular_file(archive, operation="rollback"):
                raise _review_required(f"Legacy health archive is missing: {archive}", "rollback")
            for target, expected_hash in created:
                current_hash = sha256_file(target)
                if current_hash is not None and current_hash != expected_hash:
                    raise _review_required(
                        f"Migration-created health page requires review: {target}",
                        "rollback",
                    )

            archive_bytes = archive.read_bytes()
            try:
                legacy_content = archive_bytes.decode("utf-8")
            except UnicodeDecodeError as error:
                raise _review_required(
                    f"Legacy health archive is not UTF-8: {archive}: {error}",
                    "rollback",
                ) from None
            _ensure_parent_directories((source,))
            commit_updates(
                resolved_root,
                "health-aggregate",
                "rollback",
                {source: legacy_content},
            )

            for target, expected_hash in created:
                if sha256_file(target) == expected_hash:
                    target.unlink()
            manifest_path.unlink()
            return tuple(target for target, _ in created)
