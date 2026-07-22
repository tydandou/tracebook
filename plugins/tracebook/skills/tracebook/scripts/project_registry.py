"""Register externally stored projects by stable project IDs."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import unicodedata
from urllib.parse import urlsplit
import uuid

from .errors import TracebookError
from .knowledge_root import language_for_root, validate_external_root
from .locking import file_lock
from .storage import atomic_write_text, confined_path


_PROJECT_ID = re.compile(r"prj-[0-9a-f]{32}")
_PROJECT_INDEX_START = "<!-- tracebook:projects:start -->"
_PROJECT_INDEX_END = "<!-- tracebook:projects:end -->"


@dataclass(frozen=True)
class ProjectRecord:
    """One stable project and the local signals that resolve to it."""

    project_id: str
    name: str
    relative_path: str
    locations: tuple[str, ...] = ()
    remotes: tuple[str, ...] = ()

    @property
    def identity(self) -> str:
        """Compatibility name for callers that need the project owner key."""
        return self.project_id

    @property
    def slug(self) -> str:
        """Compatibility name for the stable, human-readable project directory."""
        return PurePosixPath(self.relative_path).name


def normalize_remote(remote: str) -> str:
    """Normalize common Git remote forms to a host/path identity."""
    value = remote.strip()
    if not value:
        raise ValueError("Git remote must not be empty")

    if "://" in value:
        parsed = urlsplit(value)
        host = parsed.hostname
        path = parsed.path
    elif ":" in value and "/" in value.split(":", 1)[1]:
        host, path = value.split(":", 1)
        host = host.rsplit("@", 1)[-1]
    else:
        host, _, path = value.partition("/")

    if not host or not path:
        raise ValueError(f"Unsupported Git remote: {remote}")

    normalized_path = path.strip("/")
    if normalized_path.endswith(".git"):
        normalized_path = normalized_path[:-4]
    if not normalized_path:
        raise ValueError(f"Unsupported Git remote: {remote}")
    return f"{host.lower()}/{normalized_path}"


def repository_root(cwd: Path) -> Path:
    """Return a Git root when available, otherwise the requested local root."""
    resolved = cwd.expanduser().resolve()
    result = subprocess.run(
        ["git", "-C", str(resolved), "rev-parse", "--show-toplevel"],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip()).resolve()

    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return resolved


def _origin_remote(repo: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "remote.origin.url"],
        capture_output=True,
        check=False,
        text=True,
    )
    value = result.stdout.strip()
    return normalize_remote(value) if value else None


def project_identity(repo: Path) -> str:
    """Return the legacy diagnostic identity; project_id is the actual key."""
    root = repository_root(repo)
    remote = _origin_remote(root)
    if remote:
        return remote
    digest = hashlib.sha256(str(root).casefold().encode("utf-8")).hexdigest()[:12]
    return f"local/{digest}"


def project_lock_name(record: ProjectRecord) -> str:
    """Return an ASCII-safe lock key derived solely from the stable project ID."""
    digest = hashlib.sha256(record.project_id.encode("utf-8")).hexdigest()
    return f"project-{digest}"


def registry_path(knowledge_root: Path) -> Path:
    return knowledge_root / "registry.json"


def project_config_path(root: Path, record: ProjectRecord) -> Path:
    return root / record.relative_path / "project.json"


def _corrupt_registry(path: Path, message: str) -> TracebookError:
    return TracebookError(
        "CORRUPT_REGISTRY",
        f"Invalid registry {path}: {message}",
        "resolve",
    )


def _upgrade_required(path: Path) -> TracebookError:
    return TracebookError(
        "REGISTRY_UPGRADE_REQUIRED",
        f"Registry {path} uses the unsupported v1 project identity format; use a new knowledge root.",
        "resolve",
    )


def _validated_project_path(
    root: Path,
    relative_path: str,
    *,
    registry: Path,
) -> Path:
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or len(relative.parts) != 2
        or relative.parts[0] != "01-projects"
        or ".." in relative.parts
        or relative.as_posix() != relative_path
        or not _is_storage_name(relative.parts[1])
    ):
        raise _corrupt_registry(
            registry,
            f"unconfined project relative_path {relative_path!r}",
        )
    try:
        projects_root = confined_path(
            root,
            root / "01-projects",
            operation="resolve",
        )
        return confined_path(
            projects_root,
            root.joinpath(*relative.parts),
            operation="resolve",
        )
    except TracebookError:
        raise _corrupt_registry(
            registry,
            f"unconfined project relative_path {relative_path!r}",
        ) from None


def _is_storage_name(value: str) -> bool:
    """Allow portable readable labels, including non-Latin letters, in one path segment."""
    return (
        bool(value)
        and value[0].isalnum()
        and value[-1].isalnum()
        and value == value.casefold()
        and all(character.isalnum() or character == "-" for character in value)
    )


def _display_slug(name: str) -> str:
    """Create a readable, portable directory label without making it an identity."""
    normalized = unicodedata.normalize("NFKC", name).strip().casefold()
    label = "".join(character if character.isalnum() else "-" for character in normalized)
    label = re.sub(r"-+", "-", label).strip("-")[:64].rstrip("-")
    return label or "project"


def _new_relative_path(project_id: str, name: str, records: dict[str, ProjectRecord]) -> str:
    """Keep the display label readable while extending the suffix only on collision."""
    used = {record.relative_path for record in records.values()}
    suffix = project_id.removeprefix("prj-")
    label = _display_slug(name)
    for length in range(8, len(suffix) + 1, 4):
        candidate = f"01-projects/{label}--{suffix[:length]}"
        if candidate not in used:
            return candidate
    raise ValueError("Could not allocate a unique project storage path")


def _canonical_location(value: object, *, registry: Path) -> tuple[str, str]:
    if isinstance(value, Path):
        path = value.expanduser()
    elif isinstance(value, str) and value.strip():
        path = Path(value).expanduser()
    else:
        raise _corrupt_registry(registry, "project location must be a non-empty string")
    if not path.is_absolute():
        raise _corrupt_registry(registry, f"project location must be absolute: {value!r}")
    resolved = path.resolve()
    text = str(resolved)
    return text, os.path.normcase(text)


def _validated_locations(value: object, *, registry: Path) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _corrupt_registry(registry, "project locations must be a list")
    locations: list[str] = []
    seen: set[str] = set()
    for item in value:
        text, key = _canonical_location(item, registry=registry)
        if key in seen:
            raise _corrupt_registry(registry, f"duplicate project location {text!r}")
        seen.add(key)
        locations.append(text)
    return tuple(locations)


def _validated_remotes(value: object, *, registry: Path) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _corrupt_registry(registry, "project remotes must be a list")
    remotes: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise _corrupt_registry(registry, "project remote must be a string")
        try:
            remote = normalize_remote(item)
        except ValueError as error:
            raise _corrupt_registry(registry, str(error)) from None
        if remote in seen:
            raise _corrupt_registry(registry, f"duplicate project remote {remote!r}")
        seen.add(remote)
        remotes.append(remote)
    return tuple(remotes)


def _load_project_config(
    root: Path,
    project_id: str,
    relative_path: str,
    *,
    registry: Path,
) -> ProjectRecord:
    project_dir = _validated_project_path(root, relative_path, registry=registry)
    path = project_dir / "project.json"
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        raise _corrupt_registry(registry, f"missing project configuration {path}") from None
    if not stat.S_ISREG(mode):
        raise _corrupt_registry(registry, f"project configuration is not a regular file: {path}")
    try:
        payload = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _corrupt_registry(registry, f"invalid project configuration {path}: {error}") from None
    if not isinstance(payload, dict) or set(payload) != {
        "version",
        "project_id",
        "name",
        "locations",
        "remotes",
    }:
        raise _corrupt_registry(registry, f"invalid project configuration fields in {path}")
    if payload["version"] != 1 or payload["project_id"] != project_id:
        raise _corrupt_registry(registry, f"invalid project configuration identity in {path}")
    if not isinstance(payload["name"], str) or not payload["name"].strip():
        raise _corrupt_registry(registry, f"invalid project name in {path}")
    return ProjectRecord(
        project_id=project_id,
        name=payload["name"].strip(),
        relative_path=relative_path,
        locations=_validated_locations(payload["locations"], registry=registry),
        remotes=_validated_remotes(payload["remotes"], registry=registry),
    )


def _validate_unique_signals(records: dict[str, ProjectRecord], *, registry: Path) -> None:
    locations: dict[str, str] = {}
    remotes: dict[str, str] = {}
    for project_id, record in records.items():
        for location in record.locations:
            _, key = _canonical_location(location, registry=registry)
            owner = locations.setdefault(key, project_id)
            if owner != project_id:
                raise _corrupt_registry(registry, f"location {location!r} belongs to both {owner} and {project_id}")
        for remote in record.remotes:
            owner = remotes.setdefault(remote, project_id)
            if owner != project_id:
                raise _corrupt_registry(registry, f"remote {remote!r} belongs to both {owner} and {project_id}")


def _load_registry(path: Path, root: Path) -> dict[str, ProjectRecord]:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return {}
    if not stat.S_ISREG(mode):
        entry_type = "symlink" if stat.S_ISLNK(mode) else "non-regular entry"
        raise _corrupt_registry(path, f"expected a regular file, found {entry_type}")
    try:
        payload = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _corrupt_registry(path, str(error)) from None
    if not isinstance(payload, dict) or not isinstance(payload.get("version"), int):
        raise _corrupt_registry(path, "expected a versioned registry object")
    if payload["version"] == 1:
        raise _upgrade_required(path)
    if payload["version"] != 2 or set(payload) != {"version", "projects"} or not isinstance(payload["projects"], dict):
        raise _corrupt_registry(path, "expected version 2 and a projects object")

    records: dict[str, ProjectRecord] = {}
    for project_id, value in payload["projects"].items():
        if (
            not isinstance(project_id, str)
            or not project_id
            or not isinstance(value, dict)
            or set(value) != {"relative_path"}
            or not isinstance(value["relative_path"], str)
        ):
            raise _corrupt_registry(path, f"invalid project record {project_id!r}")
        records[project_id] = _load_project_config(
            root,
            project_id,
            value["relative_path"],
            registry=path,
        )
    _validate_unique_signals(records, registry=path)
    return records


def load_projects(knowledge_root: Path) -> tuple[ProjectRecord, ...]:
    """Return registered projects without registering a path or repairing the root."""
    root = knowledge_root.expanduser().resolve()
    records = _load_registry(registry_path(root), root)
    return tuple(sorted(records.values(), key=lambda item: (item.name.casefold(), item.project_id)))


def registered_project(knowledge_root: Path, repo: Path) -> ProjectRecord | None:
    """Resolve an already registered project without changing the knowledge root."""
    location = repository_root(repo)
    root, location = validate_external_root(knowledge_root, location)
    path = registry_path(root)
    records = _load_registry(path, root)
    location_text, location_key = _canonical_location(location, registry=path)
    remote = _origin_remote(location)
    locations, remotes = _signal_indexes(records, registry=path)
    by_location = locations.get(location_key)
    by_remote = remotes.get(remote) if remote else None
    if by_location and by_remote and by_location.project_id != by_remote.project_id:
        raise _identity_conflict(location_text, by_location, remote or "", by_remote)
    return by_location or by_remote


def find_projects(knowledge_root: Path, query: str) -> tuple[ProjectRecord, ...]:
    """Find registered projects by exact ID or a deterministic display/signal match."""
    needle = query.strip().casefold()
    if not needle:
        raise ValueError("Project query must not be empty")
    records = load_projects(knowledge_root)
    exact = [record for record in records if record.project_id.casefold() == needle]
    if exact:
        return tuple(exact)
    matched = [
        record
        for record in records
        if needle in record.name.casefold()
        or any(needle in location.casefold() for location in record.locations)
        or any(needle in remote.casefold() for remote in record.remotes)
    ]
    return tuple(matched)


def _registry_content(records: dict[str, ProjectRecord]) -> str:
    payload = {
        "version": 2,
        "projects": {
            project_id: {"relative_path": record.relative_path}
            for project_id, record in sorted(records.items())
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def _project_config_content(record: ProjectRecord) -> str:
    payload = {
        "version": 1,
        "project_id": record.project_id,
        "name": record.name,
        "locations": list(record.locations),
        "remotes": list(record.remotes),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _persist_records(
    root: Path,
    path: Path,
    records: dict[str, ProjectRecord],
    changed: set[str],
    *,
    operation: str,
) -> None:
    # Registry is the visibility boundary: write complete project configurations
    # first, then atomically publish the registry that references them. A crash
    # can leave an unreferenced configuration, but never a registry entry whose
    # configuration is absent. Keeping this outside transaction recovery also
    # preserves concurrent resolve behavior under the registry lock.
    for project_id in changed:
        record = records[project_id]
        project_dir = _validated_project_path(root, record.relative_path, registry=path)
        project_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            project_config_path(root, record),
            _project_config_content(record),
            operation=operation,
        )
    atomic_write_text(path, _registry_content(records), operation=operation)


def _save_registry(path: Path, records: dict[str, ProjectRecord]) -> None:
    """Compatibility helper for tests and maintenance code with v2 records."""
    atomic_write_text(path, _registry_content(records), operation="resolve")


def _new_project_id(records: dict[str, ProjectRecord]) -> str:
    while True:
        candidate = f"prj-{uuid.uuid4().hex}"
        if candidate not in records:
            return candidate


def _write_minimal_project_file(path: Path, content: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        atomic_write_text(path, content, operation="resolve")
        return
    if not stat.S_ISREG(mode):
        entry_type = "symlink" if stat.S_ISLNK(mode) else "non-regular entry"
        raise TracebookError(
            "INVALID_PROJECT_STATE",
            f"Invalid project state at {path}: expected a regular file, found {entry_type}",
            "resolve",
        )


def _write_minimal_project_files(root: Path, record: ProjectRecord, language: str) -> None:
    project_dir = _validated_project_path(root, record.relative_path, registry=registry_path(root))
    project_dir.mkdir(parents=True, exist_ok=True)
    overview = "项目概览" if language == "zh" else "Project Overview"
    knowledge_index = "知识索引" if language == "zh" else "Knowledge Index"
    status_title = "项目状态" if language == "zh" else "Project Status"
    current_status = "当前状态" if language == "zh" else "Current Status"
    initialized = "由 Tracebook 初始化。" if language == "zh" else "Initialized by Tracebook."
    _write_minimal_project_file(
        project_dir / "index.md",
        "\n".join(
            [
                f"# {record.name}",
                "",
                f"## {overview}",
                f"- Project ID: `{record.project_id}`",
                "",
                f"## {knowledge_index}",
                "",
            ]
        ),
    )
    _write_minimal_project_file(
        project_dir / "project-status.md",
        f"# {status_title}\n\n## {current_status}\n- {initialized}\n",
    )


def _projects_index_content(current: str, records: dict[str, ProjectRecord]) -> str:
    """Render a generated project navigation block without disturbing user content."""
    def label(name: str) -> str:
        return name.replace("\\", "\\\\").replace("]", "\\]")

    entries = [
        f"- [{label(record.name)}]({record.slug}/index.md) — `{record.project_id}`"
        for record in sorted(
            records.values(), key=lambda item: (item.name.casefold(), item.project_id)
        )
    ]
    block = "\n".join([_PROJECT_INDEX_START, *entries, _PROJECT_INDEX_END])
    expression = re.compile(
        rf"{re.escape(_PROJECT_INDEX_START)}.*?{re.escape(_PROJECT_INDEX_END)}",
        re.DOTALL,
    )
    if expression.search(current):
        return expression.sub(block, current).rstrip("\n") + "\n"
    return current.rstrip("\n") + "\n\n" + block + "\n"


def _update_projects_index(root: Path, records: dict[str, ProjectRecord], language: str) -> None:
    path = root / "01-projects" / "index.md"
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        title = "项目知识索引" if language == "zh" else "Projects Index"
        current = f"# {title}\n"
    else:
        if not stat.S_ISREG(mode):
            entry_type = "symlink" if stat.S_ISLNK(mode) else "non-regular entry"
            raise TracebookError(
                "INVALID_PROJECT_STATE",
                f"Invalid project index at {path}: expected a regular file, found {entry_type}",
                "resolve",
            )
        current = path.read_text(encoding="utf-8")
    updated = _projects_index_content(current, records)
    if updated != current:
        atomic_write_text(path, updated, operation="resolve")


def _refresh_project_index_name(root: Path, record: ProjectRecord, previous_name: str) -> None:
    """Update only the generated heading; preserve a manually customized page."""
    path = root / record.relative_path / "index.md"
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISREG(mode):
        entry_type = "symlink" if stat.S_ISLNK(mode) else "non-regular entry"
        raise TracebookError(
            "INVALID_PROJECT_STATE",
            f"Invalid project state at {path}: expected a regular file, found {entry_type}",
            "project-update",
        )
    current = path.read_text(encoding="utf-8")
    expected = f"# {previous_name}\n"
    if current.startswith(expected):
        atomic_write_text(
            path,
            f"# {record.name}\n{current[len(expected):]}",
            operation="project-update",
        )


def _signal_indexes(records: dict[str, ProjectRecord], *, registry: Path) -> tuple[dict[str, ProjectRecord], dict[str, ProjectRecord]]:
    locations: dict[str, ProjectRecord] = {}
    remotes: dict[str, ProjectRecord] = {}
    for record in records.values():
        for location in record.locations:
            _, key = _canonical_location(location, registry=registry)
            locations[key] = record
        for remote in record.remotes:
            remotes[remote] = record
    return locations, remotes


def _identity_conflict(location: str, left: ProjectRecord, remote: str, right: ProjectRecord) -> TracebookError:
    return TracebookError(
        "PROJECT_IDENTITY_CONFLICT",
        f"Location {location!r} resolves to {left.project_id}, but remote {remote!r} resolves to {right.project_id}",
        "resolve",
    )


def ensure_project(knowledge_root: Path, repo: Path) -> ProjectRecord:
    """Resolve or create a project from its location and optional origin remote."""
    location = repository_root(repo)
    root, location = validate_external_root(knowledge_root, location)
    projects_root = root / "01-projects"
    if not projects_root.is_dir():
        raise ValueError(f"Knowledge root is missing {projects_root}")
    location_text, location_key = _canonical_location(location, registry=registry_path(root))
    remote = _origin_remote(location)
    path = registry_path(root)

    with file_lock(root, "registry", operation="resolve"):
        records = _load_registry(path, root)
        locations, remotes = _signal_indexes(records, registry=path)
        by_location = locations.get(location_key)
        by_remote = remotes.get(remote) if remote else None
        if by_location and by_remote and by_location.project_id != by_remote.project_id:
            raise _identity_conflict(location_text, by_location, remote or "", by_remote)

        record = by_location or by_remote
        changed: set[str] = set()
        if record is None:
            project_id = _new_project_id(records)
            record = ProjectRecord(
                project_id=project_id,
                name=location.name or "project",
                relative_path=_new_relative_path(project_id, location.name or "project", records),
                locations=(location_text,),
                remotes=(remote,) if remote else (),
            )
            records[project_id] = record
            changed.add(project_id)
        else:
            next_locations = record.locations
            next_remotes = record.remotes
            if location_text not in next_locations:
                next_locations = (*next_locations, location_text)
            if remote and remote not in next_remotes:
                next_remotes = (*next_remotes, remote)
            updated = replace(record, locations=next_locations, remotes=next_remotes)
            if updated != record:
                record = updated
                records[record.project_id] = record
                changed.add(record.project_id)

        if changed:
            _persist_records(root, path, records, changed, operation="resolve")
        _write_minimal_project_files(root, record, language_for_root(root))
        _update_projects_index(root, records, language_for_root(root))
        return record


def update_project(
    knowledge_root: Path,
    project_id: str,
    *,
    name: str | None = None,
    locations: tuple[str, ...] | None = None,
) -> ProjectRecord:
    """Explicitly update a project's display name or complete location set."""
    root = knowledge_root.expanduser().resolve()
    path = registry_path(root)
    with file_lock(root, "registry", operation="project-update"):
        records = _load_registry(path, root)
        record = records.get(project_id)
        if record is None:
            raise TracebookError("UNKNOWN_PROJECT", f"Unknown project {project_id}", "project-update")
        next_name = record.name if name is None else name.strip()
        if not next_name:
            raise ValueError("Project name must not be empty")
        next_locations = record.locations
        if locations is not None:
            normalized = tuple(_canonical_location(value, registry=path)[0] for value in locations)
            if not normalized:
                raise ValueError("Project must keep at least one location")
            if len({os.path.normcase(value) for value in normalized}) != len(normalized):
                raise ValueError("Project locations must be unique")
            next_locations = normalized
        updated = replace(record, name=next_name, locations=next_locations)
        if updated == record:
            return record
        others = dict(records)
        others[project_id] = updated
        _validate_unique_signals(others, registry=path)
        _persist_records(root, path, others, {project_id}, operation="project-update")
        if updated.name != record.name:
            _refresh_project_index_name(root, updated, record.name)
            _update_projects_index(root, others, language_for_root(root))
        return updated


def bind_remote(knowledge_root: Path, project_id: str, remote: str) -> ProjectRecord:
    """Explicitly bind a normalized remote to one stable project."""
    try:
        normalized_remote = normalize_remote(remote)
    except ValueError:
        raise
    root = knowledge_root.expanduser().resolve()
    path = registry_path(root)
    with file_lock(root, "registry", operation="project-bind-remote"):
        records = _load_registry(path, root)
        record = records.get(project_id)
        if record is None:
            raise TracebookError("UNKNOWN_PROJECT", f"Unknown project {project_id}", "project-bind-remote")
        for other in records.values():
            if normalized_remote in other.remotes and other.project_id != project_id:
                raise TracebookError(
                    "PROJECT_IDENTITY_CONFLICT",
                    f"Remote {normalized_remote!r} already belongs to {other.project_id}",
                    "project-bind-remote",
                )
        if normalized_remote in record.remotes:
            return record
        updated = replace(record, remotes=(*record.remotes, normalized_remote))
        records[project_id] = updated
        _persist_records(root, path, records, {project_id}, operation="project-bind-remote")
        return updated
