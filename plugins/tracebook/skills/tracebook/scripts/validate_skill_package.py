"""Validate the portable Tracebook Skill package without external dependencies."""

from __future__ import annotations

from pathlib import Path
import re
import sys


LOCAL_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
REQUIRED_METADATA = {"name", "description"}
REQUIRED_AGENT_FIELDS = {"interface"}


def _frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    _, separator, remainder = text[4:].partition("\n---\n")
    if not separator:
        return None
    header = text[4:].split("\n---\n", 1)[0]
    metadata: dict[str, str] = {}
    for line in header.splitlines():
        key, delimiter, value = line.partition(":")
        if delimiter:
            metadata[key.strip()] = value.strip()
    return metadata


def validate_skill_package(root: Path) -> list[str]:
    """Return validation errors for a repository-local Codex Skill package."""
    errors: list[str] = []
    root = root.resolve()
    skill_path = root / "SKILL.md"
    if not skill_path.is_file():
        return ["SKILL.md"]

    skill = skill_path.read_text(encoding="utf-8")
    metadata = _frontmatter(skill)
    if metadata is None:
        errors.append("SKILL.md frontmatter")
    else:
        for field in sorted(REQUIRED_METADATA - metadata.keys()):
            errors.append(f"SKILL.md:{field}")

    agent_path = root / "agents" / "openai.yaml"
    if not agent_path.is_file():
        errors.append("agents/openai.yaml")
    else:
        agent_fields = {
            line.partition(":")[0].strip()
            for line in agent_path.read_text(encoding="utf-8").splitlines()
            if ":" in line
        }
        for field in sorted(REQUIRED_AGENT_FIELDS - agent_fields):
            errors.append(f"agents/openai.yaml:{field}")

    for target in LOCAL_LINK.findall(skill):
        path = target.strip().split("#", 1)[0]
        if not path or "://" in path or path.startswith("mailto:"):
            continue
        resolved = (root / path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            errors.append(path)
            continue
        if not resolved.exists():
            errors.append(path)
    return errors


def main() -> int:
    errors = validate_skill_package(Path(__file__).resolve().parents[1])
    if errors:
        for error in errors:
            print(f"Invalid Skill package: {error}", file=sys.stderr)
        return 1
    print("Skill package is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())