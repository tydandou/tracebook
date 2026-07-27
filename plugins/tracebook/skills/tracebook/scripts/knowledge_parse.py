"""Shared evidence-path parsing.

Two deliberately separate entry points so the query side can relax rules the
capture side must keep strict:

- ``is_file_evidence`` / ``evidence_lookup_key`` — normalize an already-relative
  source path into a comparison key (used when indexing stored evidence and by
  the strict capture gate; never accepts absolute paths on its own).
- ``parse_query_evidence`` — the lenient query entry: it may relativize a
  project-internal absolute path before producing a lookup key, and returns a
  warning instead of a key when the path is not a local file or falls outside
  the project.

``current_evidence_paths`` reads the ``## Current`` evidence block, so retrieval
(`context_search`) and health review (`check_knowledge`) decide "which local
files back this knowledge" through one implementation rather than two copies of
the same regexes and prefix list.

The capture gate in ``capture.py`` deliberately does NOT share this module: it
must reject every absolute path, and reusing the lenient normalization here
would widen what may be written.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
import unicodedata


LINE_SUFFIX = re.compile(r":L\d+(?:-L\d+)?$")
DRIVE_PREFIX = re.compile(r"^[a-zA-Z]:")
SCHEME_OR_DRIVE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
NON_FILE_PREFIXES = ("http://", "https://", "test:", "command:", "human:")
CURRENT_SECTION = re.compile(r"(?ms)^## Current\n\n(.*?)(?=\n## History\n|\Z)")
EVIDENCE_BLOCK = re.compile(r"(?ms)^Evidence:\n((?:- `[^`]+`\n?)+)")


def is_file_evidence(value: str) -> bool:
    """True when the evidence entry names a local file (not URL/test/command/human)."""
    stripped = value.strip()
    return bool(stripped) and not stripped.startswith(NON_FILE_PREFIXES)


def evidence_lookup_key(relative_path: str) -> str:
    """Comparison key for an already-relative source path.

    NFKC + backslash->slash + stripped ``:Lnn`` suffix. Case-insensitive on
    Windows, case-preserving on POSIX, matching each platform's filesystem.
    """
    normalized = unicodedata.normalize("NFKC", relative_path).replace("\\", "/")
    normalized = LINE_SUFFIX.sub("", normalized).strip("/")
    return normalized.casefold() if os.name == "nt" else normalized


def is_absolute_evidence_path(value: str) -> bool:
    """Whether a query-side evidence value uses POSIX or drive absolute syntax."""
    cleaned = LINE_SUFFIX.sub(
        "", unicodedata.normalize("NFKC", value.strip()).replace("\\", "/")
    )
    return cleaned.startswith("/") or DRIVE_PREFIX.match(cleaned) is not None


def evidence_items(section: str) -> list[str]:
    """Raw evidence entries listed in an authority-page section, in page order."""
    match = EVIDENCE_BLOCK.search(section)
    return re.findall(r"`([^`]+)`", match.group(1)) if match else []


def stored_evidence_path(value: str) -> str | None:
    """Return a safe normalized repository-relative stored evidence path.

    Authority pages may be edited by hand, so stored values are not trusted just
    because the capture API normally validates them. Query parsing has a separate
    lenient entry point for project-internal absolute paths; persisted evidence
    must remain relative and confined.
    """
    if not is_file_evidence(value):
        return None
    normalized = unicodedata.normalize("NFKC", value.strip()).replace("\\", "/")
    normalized = LINE_SUFFIX.sub("", normalized)
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or SCHEME_OR_DRIVE.match(normalized)
        or any(part in {".", ".."} for part in path.parts)
    ):
        return None
    return path.as_posix()


def invalid_current_file_evidence(content: str) -> list[str]:
    """Local-looking Current evidence entries that violate stored-path rules."""
    section = CURRENT_SECTION.search(content)
    if section is None:
        return []
    return [
        item
        for item in evidence_items(section.group(1))
        if is_file_evidence(item) and stored_evidence_path(item) is None
    ]


def current_evidence_paths(content: str) -> list[str]:
    """Local source paths backing the entity's ``## Current`` conclusion.

    Slash-normalized and stripped of the ``:Lnn`` suffix so the result can be
    joined onto a source root; URL/test/command/human entries are dropped.
    History sections are excluded — only the live conclusion's evidence counts.
    """
    section = CURRENT_SECTION.search(content)
    if section is None:
        return []
    return [
        parsed
        for item in evidence_items(section.group(1))
        if (parsed := stored_evidence_path(item)) is not None
    ]


def parse_query_evidence(
    value: str, *, source_root: Path | None
) -> tuple[str | None, str | None]:
    """Lenient query-side parse. Returns ``(lookup_key, warning)``.

    A relative path becomes a key directly. An absolute path is relativized
    against ``source_root`` when it lies inside it; otherwise it yields a
    warning and no key (no filename fuzzy matching).
    """
    stripped = value.strip()
    if not stripped:
        return None, None
    if not is_file_evidence(stripped):
        return None, f"evidence-path is not a local file reference: {value}"
    cleaned = LINE_SUFFIX.sub("", stripped).replace("\\", "/")
    if is_absolute_evidence_path(cleaned):
        if source_root is None:
            return None, f"absolute evidence-path has no project source root: {value}"
        try:
            relative = Path(cleaned).resolve().relative_to(source_root.resolve())
        except (ValueError, OSError):
            return None, f"absolute evidence-path is outside the project: {value}"
        cleaned = relative.as_posix()
    return evidence_lookup_key(cleaned), None
