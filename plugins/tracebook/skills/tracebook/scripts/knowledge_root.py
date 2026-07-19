"""Initialize an external Tracebook knowledge root from bundled templates."""

from __future__ import annotations

from pathlib import Path

from .errors import TracebookError
from .locking import file_lock
from .storage import atomic_write_text, confined_path


DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "assets" / "knowledge-root-template"
)


def validate_external_root(root: Path, repository: Path) -> tuple[Path, Path]:
    """Resolve both roots and keep Tracebook storage outside the repository."""
    resolved_root = root.expanduser().resolve()
    resolved_repository = repository.expanduser().resolve()
    if (
        resolved_root == resolved_repository
        or resolved_repository in resolved_root.parents
    ):
        raise TracebookError(
            "ROOT_INSIDE_REPOSITORY",
            (
                f"Knowledge root {resolved_root} must not equal or be contained by "
                f"repository {resolved_repository}"
            ),
            "resolve",
        )
    return resolved_root, resolved_repository


def repair_knowledge_root(
    target: Path, template: Path = DEFAULT_TEMPLATE
) -> tuple[Path, ...]:
    """Atomically restore missing templates without overwriting existing content."""
    target = target.expanduser().resolve()
    template = template.expanduser().resolve()

    created: list[Path] = []
    with file_lock(target, "maintenance", operation="initialize"):
        for source in sorted(template.rglob("*")):
            relative = source.relative_to(template)
            destination = target / relative
            if source.is_dir():
                confined_path(target, destination, operation="initialize").mkdir(
                    parents=True,
                    exist_ok=True,
                )
                continue
            if destination.exists() or destination.is_symlink():
                continue

            destination = confined_path(target, destination, operation="initialize")
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = source.read_text(encoding="utf-8").replace(
                "{{knowledge_root}}", str(target)
            )
            atomic_write_text(destination, content, operation="initialize")
            created.append(destination)
    return tuple(created)


def ensure_knowledge_root(
    target: Path, template: Path = DEFAULT_TEMPLATE
) -> list[Path]:
    """Compatibility wrapper returning the historical list result."""
    return list(repair_knowledge_root(target, template))
