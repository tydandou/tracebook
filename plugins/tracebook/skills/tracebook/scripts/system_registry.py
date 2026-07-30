"""Register explicit multi-project systems and their directed relationships."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import unicodedata
import uuid

from .errors import TracebookError
from .locking import file_lock
from .project_registry import load_projects
from .storage import confined_path
from .transaction import commit_updates, require_clean_transaction_scope


SYSTEM_ID = re.compile(r"sys-[0-9a-f]{32}\Z")
PROJECT_ID = re.compile(r"prj-[0-9a-f]{32}\Z")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_SYSTEMS_INDEX_START = "<!-- tracebook:systems:start -->"
_SYSTEMS_INDEX_END = "<!-- tracebook:systems:end -->"
_SYSTEM_PAGE_START = "<!-- tracebook:system:start -->"
_SYSTEM_PAGE_END = "<!-- tracebook:system:end -->"


@dataclass(frozen=True)
class SystemRelation:
    source_project_id: str
    target_project_id: str
    kind: str


@dataclass(frozen=True)
class SystemRecord:
    system_id: str
    name: str
    relative_path: str
    project_ids: tuple[str, ...] = ()
    relations: tuple[SystemRelation, ...] = ()

    @property
    def slug(self) -> str:
        return PurePosixPath(self.relative_path).name


def system_lock_name(record: SystemRecord) -> str:
    return "system-" + hashlib.sha256(record.system_id.encode("utf-8")).hexdigest()


def _error(code: str, message: str, operation: str = "system") -> TracebookError:
    return TracebookError(code, message, operation)


def _registry_path(root: Path) -> Path:
    return root / "04-systems" / "registry.json"


def _config_path(root: Path, record: SystemRecord) -> Path:
    return root / record.relative_path / "system.json"


def _label(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).strip().casefold()
    value = "".join(char if char.isalnum() else "-" for char in normalized)
    return re.sub(r"-+", "-", value).strip("-")[:64].rstrip("-") or "system"


def _relative_path(system_id: str, name: str, records: dict[str, SystemRecord]) -> str:
    used = {record.relative_path for record in records.values()}
    label = _label(name)
    suffix = system_id.removeprefix("sys-")
    for length in range(8, len(suffix) + 1, 4):
        candidate = f"04-systems/{label}--{suffix[:length]}"
        if candidate not in used:
            return candidate
    raise ValueError("Could not allocate a unique system storage path")


def _validated_path(root: Path, relative_path: str, registry: Path) -> Path:
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or len(relative.parts) != 2
        or relative.parts[0] != "04-systems"
        or ".." in relative.parts
        or relative.as_posix() != relative_path
    ):
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid system path {relative_path!r}")
    try:
        systems_root = confined_path(root, root / "04-systems", operation="system")
        return confined_path(systems_root, root.joinpath(*relative.parts), operation="system")
    except TracebookError:
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid system path {relative_path!r}") from None


def _relation(payload: object, system_id: str) -> SystemRelation:
    if not isinstance(payload, dict) or set(payload) != {"source_project_id", "target_project_id", "kind"}:
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid relation in {system_id}")
    source, target, kind = payload.values()
    if (
        not isinstance(source, str)
        or not isinstance(target, str)
        or not isinstance(kind, str)
        or PROJECT_ID.fullmatch(source) is None
        or PROJECT_ID.fullmatch(target) is None
        or SLUG.fullmatch(kind) is None
        or source == target
    ):
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid relation in {system_id}")
    return SystemRelation(source, target, kind)


def _load_config(root: Path, system_id: str, relative_path: str, registry: Path) -> SystemRecord:
    path = _validated_path(root, relative_path, registry) / "system.json"
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise _error("CORRUPT_SYSTEM_REGISTRY", f"System config is not a regular file: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Missing system config: {path}") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid system config {path}: {error}") from None
    if not isinstance(payload, dict) or set(payload) != {"version", "system_id", "name", "project_ids", "relations"}:
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid system config fields in {path}")
    if payload["version"] != 1 or payload["system_id"] != system_id or not isinstance(payload["name"], str) or not payload["name"].strip():
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid system identity in {path}")
    projects = payload["project_ids"]
    if not isinstance(projects, list) or any(not isinstance(value, str) or PROJECT_ID.fullmatch(value) is None for value in projects) or len(set(projects)) != len(projects):
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid system projects in {path}")
    if not isinstance(payload["relations"], list):
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid system relations in {path}")
    relations = tuple(_relation(value, system_id) for value in payload["relations"])
    if len(set(relations)) != len(relations):
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid system relations in {path}")
    if any(relation.source_project_id not in projects or relation.target_project_id not in projects for relation in relations):
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Relation references a project outside {system_id}")
    return SystemRecord(system_id, payload["name"].strip(), relative_path, tuple(projects), relations)


def _load(root: Path) -> dict[str, SystemRecord]:
    path = _registry_path(root)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return {}
    if not stat.S_ISREG(mode):
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"System registry is not a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid system registry {path}: {error}") from None
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("systems"), dict) or set(payload) != {"version", "systems"}:
        raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid system registry {path}")
    records: dict[str, SystemRecord] = {}
    for system_id, value in payload["systems"].items():
        if not isinstance(system_id, str) or SYSTEM_ID.fullmatch(system_id) is None or not isinstance(value, dict) or set(value) != {"relative_path"} or not isinstance(value["relative_path"], str):
            raise _error("CORRUPT_SYSTEM_REGISTRY", f"Invalid system registry entry {system_id!r}")
        records[system_id] = _load_config(root, system_id, value["relative_path"], path)
    return records


def load_systems(root: Path) -> tuple[SystemRecord, ...]:
    records = _load(root.expanduser().resolve())
    return tuple(sorted(records.values(), key=lambda item: (item.name.casefold(), item.system_id)))


def get_system(root: Path, system_id: str) -> SystemRecord:
    record = _load(root.expanduser().resolve()).get(system_id)
    if record is None:
        raise _error("UNKNOWN_SYSTEM", f"Unknown system {system_id}", "system")
    return record


def _registry_content(records: dict[str, SystemRecord]) -> str:
    return json.dumps({"version": 1, "systems": {key: {"relative_path": value.relative_path} for key, value in sorted(records.items())}}, indent=2) + "\n"


def _config_content(record: SystemRecord) -> str:
    return json.dumps({"version": 1, "system_id": record.system_id, "name": record.name, "project_ids": list(record.project_ids), "relations": [{"source_project_id": value.source_project_id, "target_project_id": value.target_project_id, "kind": value.kind} for value in record.relations]}, ensure_ascii=False, indent=2) + "\n"


def _generated_block(start: str, end: str, entries: list[str], current: str) -> str:
    """Replace a generated navigation block, leaving hand-written content alone."""
    block = "\n".join([start, *entries, end])
    expression = re.compile(rf"{re.escape(start)}.*?{re.escape(end)}", re.DOTALL)
    if expression.search(current):
        return expression.sub(lambda _: block, current).rstrip("\n") + "\n"
    return current.rstrip("\n") + "\n\n" + block + "\n"


def _regular_text(
    path: Path,
    *,
    operation: str,
    missing: str | None,
) -> str | None:
    """Read one generated/authority target without following non-regular entries."""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return missing
    if not stat.S_ISREG(mode):
        entry_type = "symlink" if stat.S_ISLNK(mode) else "non-regular entry"
        raise _error(
            "INVALID_SYSTEM_STATE",
            f"Invalid system state at {path}: expected a regular file, found {entry_type}",
            operation,
        )
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise _error(
            "INVALID_SYSTEM_STATE",
            f"Invalid UTF-8 system state at {path}: {error}",
            operation,
        ) from None


def _system_page_content(current: str, record: SystemRecord, names: dict[str, str]) -> str:
    """Render a system's members and relations from its own record.

    Keyed on `system_id` and `project_id` rather than on display names, which a
    later rename may change.
    """
    def label(value: str) -> str:
        return value.replace("\\", "\\\\").replace("]", "\\]")

    entries = ["## Members"]
    entries += [
        f"- {label(names.get(project_id, project_id))} — `{project_id}`"
        for project_id in sorted(record.project_ids, key=lambda value: (names.get(value, value).casefold(), value))
    ] or ["- None"]
    entries += ["", "## Relations"]
    entries += [
        f"- {label(names.get(relation.source_project_id, relation.source_project_id))} "
        f"--{label(relation.kind)}--> "
        f"{label(names.get(relation.target_project_id, relation.target_project_id))}"
        for relation in sorted(
            record.relations,
            key=lambda value: (value.source_project_id, value.target_project_id, value.kind),
        )
    ] or ["- None"]
    return _generated_block(_SYSTEM_PAGE_START, _SYSTEM_PAGE_END, entries, current)


def _systems_index_content(current: str, records: dict[str, SystemRecord]) -> str:
    def label(name: str) -> str:
        return name.replace("\\", "\\\\").replace("]", "\\]")

    entries = [
        f"- [{label(record.name)}]({record.slug}/index.md) — `{record.system_id}`"
        for record in sorted(
            records.values(), key=lambda item: (item.name.casefold(), item.system_id)
        )
    ]
    return _generated_block(_SYSTEMS_INDEX_START, _SYSTEMS_INDEX_END, entries, current)


def _systems_index_update(
    root: Path,
    records: dict[str, SystemRecord],
    operation: str,
) -> tuple[Path, str, str]:
    path = root / "04-systems" / "index.md"
    current = _regular_text(
        path,
        operation=operation,
        missing="# Systems Index\n",
    )
    assert current is not None
    return path, current, _systems_index_content(current, records)


def _persist(root: Path, records: dict[str, SystemRecord], changed: set[str], operation: str) -> None:
    names = {record.project_id: record.name for record in load_projects(root)}
    updates: dict[Path, str] = {}
    directories: list[Path] = []
    for system_id in changed:
        record = records[system_id]
        directory = _validated_path(root, record.relative_path, _registry_path(root))
        directories.append(directory)
        config = _config_path(root, record)
        current_config = _regular_text(config, operation=operation, missing=None)
        updated_config = _config_content(record)
        if current_config != updated_config:
            updates[config] = updated_config
        index = directory / "index.md"
        current = _regular_text(
            index,
            operation=operation,
            missing=f"# {record.name}\n\n- System ID: `{record.system_id}`\n",
        )
        assert current is not None
        updated = _system_page_content(current, record, names)
        if updated != current:
            updates[index] = updated

    registry = _registry_path(root)
    current_registry = _regular_text(registry, operation=operation, missing=None)
    updated_registry = _registry_content(records)
    if current_registry != updated_registry:
        updates[registry] = updated_registry

    systems_index, current_index, updated_index = _systems_index_update(
        root, records, operation
    )
    if current_index != updated_index:
        updates[systems_index] = updated_index

    # All target reads and type checks happen before the first filesystem write.
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    final_targets = (registry,) if registry in updates else ()
    commit_updates(
        root,
        "registry",
        operation,
        updates,
        final_targets=final_targets,
    )


def project_name_navigation_updates(
    root: Path,
    project_id: str,
    names: dict[str, str],
    operation: str,
) -> dict[Path, str]:
    """Return derived system-page updates after a project display-name change.

    The caller holds both the registry and systems-registry locks and commits the
    returned pages in the same registry-scope transaction as the project update.
    """
    records = _load(root)
    updates: dict[Path, str] = {}
    for record in records.values():
        if project_id not in record.project_ids:
            continue
        directory = _validated_path(root, record.relative_path, _registry_path(root))
        index = directory / "index.md"
        current = _regular_text(
            index,
            operation=operation,
            missing=f"# {record.name}\n\n- System ID: `{record.system_id}`\n",
        )
        assert current is not None
        updated = _system_page_content(current, record, names)
        if updated != current:
            updates[index] = updated
    return updates


def create_system(root: Path, name: str) -> SystemRecord:
    resolved = root.expanduser().resolve()
    normalized = name.strip()
    if not normalized:
        raise ValueError("System name must not be empty")
    with file_lock(resolved, "registry", operation="system-create"):
        require_clean_transaction_scope(resolved, "registry", "system-create")
        with file_lock(resolved, "systems-registry", operation="system-create"):
            records = _load(resolved)
            system_id = f"sys-{uuid.uuid4().hex}"
            record = SystemRecord(system_id, normalized, _relative_path(system_id, normalized, records))
            records[system_id] = record
            _persist(resolved, records, {system_id}, "system-create")
            return record


def bind_project(root: Path, system_id: str, project_id: str) -> SystemRecord:
    resolved = root.expanduser().resolve()
    with file_lock(resolved, "registry", operation="system-bind-project"):
        require_clean_transaction_scope(
            resolved, "registry", "system-bind-project"
        )
        known = {record.project_id for record in load_projects(resolved)}
        if project_id not in known:
            raise _error("UNKNOWN_PROJECT", f"Unknown project {project_id}", "system-bind-project")
        with file_lock(resolved, "systems-registry", operation="system-bind-project"):
            records = _load(resolved)
            record = records.get(system_id)
            if record is None:
                raise _error("UNKNOWN_SYSTEM", f"Unknown system {system_id}", "system-bind-project")
            if project_id in record.project_ids:
                _persist(resolved, records, {system_id}, "system-bind-project")
                return record
            updated = replace(record, project_ids=(*record.project_ids, project_id))
            records[system_id] = updated
            _persist(resolved, records, {system_id}, "system-bind-project")
            return updated


def add_relation(root: Path, system_id: str, source_project_id: str, target_project_id: str, kind: str) -> SystemRecord:
    resolved = root.expanduser().resolve()
    if SLUG.fullmatch(kind) is None:
        raise ValueError("Relation kind must be a lowercase hyphenated slug")
    relation = SystemRelation(source_project_id, target_project_id, kind)
    if source_project_id == target_project_id:
        raise ValueError("A system relation must connect two different projects")
    with file_lock(resolved, "registry", operation="system-relate"):
        require_clean_transaction_scope(resolved, "registry", "system-relate")
        with file_lock(resolved, "systems-registry", operation="system-relate"):
            records = _load(resolved)
            record = records.get(system_id)
            if record is None:
                raise _error("UNKNOWN_SYSTEM", f"Unknown system {system_id}", "system-relate")
            if source_project_id not in record.project_ids or target_project_id not in record.project_ids:
                raise _error("INVALID_SYSTEM_RELATION", "Both relation projects must belong to the system", "system-relate")
            if relation in record.relations:
                _persist(resolved, records, {system_id}, "system-relate")
                return record
            updated = replace(record, relations=(*record.relations, relation))
            records[system_id] = updated
            _persist(resolved, records, {system_id}, "system-relate")
            return updated
