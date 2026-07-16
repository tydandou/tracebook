"""Initialize an external Tracebook knowledge root from bundled templates."""

from __future__ import annotations

from pathlib import Path


DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "assets" / "knowledge-root-template"
)


def ensure_knowledge_root(
    target: Path, template: Path = DEFAULT_TEMPLATE
) -> list[Path]:
    """Copy the bundled root once without overwriting an existing knowledge root."""
    target = target.expanduser()
    if target.exists() and any(target.iterdir()):
        return []

    created: list[Path] = []
    for source in sorted(template.rglob("*")):
        relative = source.relative_to(template)
        destination = target / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_text(encoding="utf-8").replace(
            "{{knowledge_root}}", str(target)
        )
        destination.write_text(content, encoding="utf-8")
        created.append(destination)
    return created
