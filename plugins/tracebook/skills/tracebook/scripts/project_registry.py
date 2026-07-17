"""Register Git projects in an external Tracebook knowledge root."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from urllib.parse import urlsplit

from .errors import TracebookError
from .knowledge_root import validate_external_root
from .locking import file_lock
from .storage import atomic_write_text, confined_path


@dataclass(frozen=True)
class ProjectRecord:
    identity: str
    slug: str
    relative_path: str


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
    """Return the Git root, with a lightweight fallback for fixture repos."""
    resolved = cwd.resolve()
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
    raise ValueError(f"No Git repository found from {cwd}")


def _origin_remote(repo: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "remote.origin.url"],
        capture_output=True,
        check=False,
        text=True,
    )
    value = result.stdout.strip()
    return value or None


def project_identity(repo: Path) -> str:
    """Prefer an origin remote; otherwise derive a stable local identity."""
    root = repository_root(repo)
    remote = _origin_remote(root)
    if remote:
        return normalize_remote(remote)
    digest = hashlib.sha256(str(root).casefold().encode("utf-8")).hexdigest()[:12]
    return f"local/{digest}"


def registry_path(knowledge_root: Path) -> Path:
    return knowledge_root / "registry.json"


def _corrupt_registry(path: Path, message: str) -> TracebookError:
    return TracebookError(
        "CORRUPT_REGISTRY",
        f"Invalid registry {path}: {message}",
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
        or len(relative.parts) < 2
        or relative.parts[0] != "01-projects"
        or ".." in relative.parts
        or relative.as_posix() != relative_path
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

    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "projects"}
        or type(payload["version"]) is not int
        or payload["version"] != 1
        or not isinstance(payload["projects"], dict)
    ):
        raise _corrupt_registry(path, "expected version 1 and a projects object")

    records: dict[str, ProjectRecord] = {}
    for identity, value in payload["projects"].items():
        if (
            not isinstance(identity, str)
            or not identity
            or not isinstance(value, dict)
            or set(value) != {"identity", "slug", "relative_path"}
            or any(
                not isinstance(value[field], str) or not value[field]
                for field in ("identity", "slug", "relative_path")
            )
            or value["identity"] != identity
        ):
            raise _corrupt_registry(path, f"invalid project record {identity!r}")
        _validated_project_path(
            root,
            value["relative_path"],
            registry=path,
        )
        records[identity] = ProjectRecord(**value)
    return records


def _save_registry(path: Path, records: dict[str, ProjectRecord]) -> None:
    payload = {
        "version": 1,
        "projects": {
            identity: asdict(record)
            for identity, record in sorted(records.items())
        },
    }
    atomic_write_text(
        path,
        json.dumps(payload, indent=2) + "\n",
        operation="resolve",
    )


def _slug(identity: str, records: dict[str, ProjectRecord]) -> str:
    base = identity.rsplit("/", 1)[-1]
    base = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "project"
    used = {record.slug for record in records.values()}
    if base not in used:
        return base
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{suffix}"


def _write_minimal_project_file(path: Path, content: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        atomic_write_text(
            path,
            content,
            operation="resolve",
        )
        return
    if not stat.S_ISREG(mode):
        entry_type = "symlink" if stat.S_ISLNK(mode) else "non-regular entry"
        raise TracebookError(
            "INVALID_PROJECT_STATE",
            f"Invalid project state at {path}: expected a regular file, found {entry_type}",
            "resolve",
        )


def _write_minimal_project_files(project_dir: Path, record: ProjectRecord) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    _write_minimal_project_file(
        project_dir / "index.md",
        "\n".join(
            [
                f"# {record.slug}",
                "",
                "## Project Overview",
                f"- Project identity: `{record.identity}`",
                "",
                "## Knowledge Index",
                "",
            ]
        ),
    )

    _write_minimal_project_file(
        project_dir / "project-status.md",
        "# Project Status\n\n## Current Status\n- Initialized by Tracebook.\n",
    )


def ensure_project(knowledge_root: Path, repo: Path) -> ProjectRecord:
    """Register a repository and create only its minimal knowledge documents."""
    repository = repository_root(repo)
    root, repository = validate_external_root(knowledge_root, repository)
    projects_root = root / "01-projects"
    if not projects_root.is_dir():
        raise ValueError(f"Knowledge root is missing {projects_root}")

    identity = project_identity(repository)
    path = registry_path(root)
    with file_lock(root, "registry", operation="resolve"):
        records = _load_registry(path, root)
        record = records.get(identity)
        if record is None:
            slug = _slug(identity, records)
            record = ProjectRecord(
                identity=identity,
                slug=slug,
                relative_path=f"01-projects/{slug}",
            )
            project_dir = _validated_project_path(
                root,
                record.relative_path,
                registry=path,
            )
            records[identity] = record
            _save_registry(path, records)
        else:
            project_dir = _validated_project_path(
                root,
                record.relative_path,
                registry=path,
            )

        _write_minimal_project_files(project_dir, record)
        return record
