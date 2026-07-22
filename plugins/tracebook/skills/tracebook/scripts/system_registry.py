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
from .storage import atomic_write_text, confined_path


SYSTEM_ID = re.compile(r"sys-[0-9a-f]{32}\Z")
PROJECT_ID = re.compile(r"prj-[0-9a-f]{32}\Z")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


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


def _persist(root: Path, records: dict[str, SystemRecord], changed: set[str], operation: str) -> None:
    for system_id in changed:
        record = records[system_id]
        directory = _validated_path(root, record.relative_path, _registry_path(root))
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write_text(_config_path(root, record), _config_content(record), operation=operation)
        index = directory / "index.md"
        if not index.exists():
            atomic_write_text(index, f"# {record.name}\n\n- System ID: `{record.system_id}`\n", operation=operation)
    atomic_write_text(_registry_path(root), _registry_content(records), operation=operation)


def create_system(root: Path, name: str) -> SystemRecord:
    resolved = root.expanduser().resolve()
    normalized = name.strip()
    if not normalized:
        raise ValueError("System name must not be empty")
    with file_lock(resolved, "systems-registry", operation="system-create"):
        records = _load(resolved)
        system_id = f"sys-{uuid.uuid4().hex}"
        record = SystemRecord(system_id, normalized, _relative_path(system_id, normalized, records))
        records[system_id] = record
        _persist(resolved, records, {system_id}, "system-create")
        return record


def bind_project(root: Path, system_id: str, project_id: str) -> SystemRecord:
    resolved = root.expanduser().resolve()
    known = {record.project_id for record in load_projects(resolved)}
    if project_id not in known:
        raise _error("UNKNOWN_PROJECT", f"Unknown project {project_id}", "system-bind-project")
    with file_lock(resolved, "systems-registry", operation="system-bind-project"):
        records = _load(resolved)
        record = records.get(system_id)
        if record is None:
            raise _error("UNKNOWN_SYSTEM", f"Unknown system {system_id}", "system-bind-project")
        if project_id in record.project_ids:
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
    with file_lock(resolved, "systems-registry", operation="system-relate"):
        records = _load(resolved)
        record = records.get(system_id)
        if record is None:
            raise _error("UNKNOWN_SYSTEM", f"Unknown system {system_id}", "system-relate")
        if source_project_id not in record.project_ids or target_project_id not in record.project_ids:
            raise _error("INVALID_SYSTEM_RELATION", "Both relation projects must belong to the system", "system-relate")
        if relation in record.relations:
            return record
        updated = replace(record, relations=(*record.relations, relation))
        records[system_id] = updated
        _persist(resolved, records, {system_id}, "system-relate")
        return updated
