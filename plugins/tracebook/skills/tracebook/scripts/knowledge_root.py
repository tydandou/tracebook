"""Initialize an external Tracebook knowledge root from bundled templates."""

from __future__ import annotations

import json
from pathlib import Path
import stat

from .errors import TracebookError
from .locking import file_lock
from .storage import atomic_write_text, confined_path


DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "assets" / "knowledge-root-template"
)
CHINESE_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "assets" / "knowledge-root-template-zh"
)
_LANGUAGE_CONFIG = Path(".tracebook-state") / "config.json"
_SUPPORTED_LANGUAGES = {"en", "zh"}


def _invalid_language_config(root: Path, message: str) -> TracebookError:
    return TracebookError(
        "INVALID_LANGUAGE_CONFIG",
        f"Invalid language config at {root / _LANGUAGE_CONFIG}: {message}",
        "initialize",
    )


def language_for_root(root: Path) -> str:
    """Return the manual root language selection without creating any files."""
    resolved_root = root.expanduser().resolve()
    config = resolved_root / _LANGUAGE_CONFIG
    try:
        mode = config.lstat().st_mode
    except FileNotFoundError:
        return "en"
    if not stat.S_ISREG(mode):
        raise _invalid_language_config(resolved_root, "expected a regular file")
    try:
        payload = json.loads(config.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _invalid_language_config(resolved_root, str(error)) from None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "knowledge_language"}
        or payload["version"] != 1
        or payload["knowledge_language"] not in _SUPPORTED_LANGUAGES
    ):
        raise _invalid_language_config(
            resolved_root,
            'expected {"version": 1, "knowledge_language": "en" | "zh"}',
        )
    return payload["knowledge_language"]


def template_for_root(root: Path) -> Path:
    return CHINESE_TEMPLATE if language_for_root(root) == "zh" else DEFAULT_TEMPLATE


def _template_sources(root: Path, template: Path | None) -> dict[Path, Path]:
    if template is not None:
        selected = template.expanduser().resolve()
        return {source.relative_to(selected): source for source in selected.rglob("*")}

    sources = {
        source.relative_to(DEFAULT_TEMPLATE): source
        for source in DEFAULT_TEMPLATE.rglob("*")
    }
    if language_for_root(root) == "zh":
        sources.update(
            {
                source.relative_to(CHINESE_TEMPLATE): source
                for source in CHINESE_TEMPLATE.rglob("*")
            }
        )
    return sources


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
    target: Path, template: Path | None = None
) -> tuple[Path, ...]:
    """Atomically restore missing templates without overwriting existing content."""
    target = target.expanduser().resolve()
    sources = _template_sources(target, template)

    created: list[Path] = []
    with file_lock(target, "maintenance", operation="initialize"):
        for relative, source in sorted(sources.items()):
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
    target: Path, template: Path | None = None
) -> list[Path]:
    """Compatibility wrapper returning the historical list result."""
    return list(repair_knowledge_root(target, template))
