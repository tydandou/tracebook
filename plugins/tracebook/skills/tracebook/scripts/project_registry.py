"""Register Git projects in an external Tracebook knowledge root."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit


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


def _load_registry(path: Path) -> dict[str, ProjectRecord]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    projects = payload.get("projects", {})
    return {
        identity: ProjectRecord(**record)
        for identity, record in projects.items()
    }


def _save_registry(path: Path, records: dict[str, ProjectRecord]) -> None:
    payload = {
        "version": 1,
        "projects": {
            identity: asdict(record)
            for identity, record in sorted(records.items())
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _slug(identity: str, records: dict[str, ProjectRecord]) -> str:
    base = identity.rsplit("/", 1)[-1]
    base = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "project"
    used = {record.slug for record in records.values()}
    if base not in used:
        return base
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{suffix}"


def _write_minimal_project_files(project_dir: Path, record: ProjectRecord) -> None:
    index = project_dir / "index.md"
    if not index.exists():
        index.write_text(
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
            encoding="utf-8",
        )

    status = project_dir / "project-status.md"
    if not status.exists():
        status.write_text(
            "# Project Status\n\n## Current Status\n- Initialized by Tracebook.\n",
            encoding="utf-8",
        )


def ensure_project(knowledge_root: Path, repo: Path) -> ProjectRecord:
    """Register a repository and create only its minimal knowledge documents."""
    root = knowledge_root.resolve()
    projects_root = root / "01-projects"
    if not projects_root.is_dir():
        raise ValueError(f"Knowledge root is missing {projects_root}")

    identity = project_identity(repo)
    path = registry_path(root)
    records = _load_registry(path)
    record = records.get(identity)
    if record is None:
        slug = _slug(identity, records)
        record = ProjectRecord(
            identity=identity,
            slug=slug,
            relative_path=f"01-projects/{slug}",
        )
        records[identity] = record
        _save_registry(path, records)

    project_dir = root / record.relative_path
    project_dir.mkdir(parents=True, exist_ok=True)
    _write_minimal_project_files(project_dir, record)
    return record
