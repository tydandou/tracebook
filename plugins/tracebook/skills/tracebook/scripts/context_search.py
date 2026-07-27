"""Deterministic schema-v2 Markdown context retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
import unicodedata
from collections.abc import Mapping

from .knowledge_parse import (
    CURRENT_SECTION as CURRENT,
    evidence_items,
    evidence_lookup_key,
    is_file_evidence,
)
from .project_registry import ProjectRecord
from .storage import read_bytes_shared


FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
HISTORY = re.compile(r"(?ms)^### Version (\d+) — (\d{4}-\d{2}-\d{2})\n\n(.*?)(?=^### Version |\Z)")
WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
CJK_RUN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]+")
STOPWORDS = {
    "the", "a", "an", "is", "are", "of", "to", "and", "or", "in", "on", "for",
    "with", "this", "that", "it", "as", "at", "by", "be", "was", "were", "will",
}


def _front(content: str) -> dict[str, str]:
    match = FRONT.match(content)
    if match is None:
        return {}
    return {key.strip(): value.strip() for line in match.group(1).splitlines() if (key := line.partition(":")[0]) and ":" in line for value in [line.partition(":")[2]]}


def _norm(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().replace("\\", "/")


def _recency_key(updated: str) -> tuple[int, ...]:
    """Descending-by-date sort key: newer `updated` sorts first on score ties."""
    try:
        return tuple(-int(part) for part in updated.split("-"))
    except ValueError:
        return (0,)


def _tokens(value: str) -> set[str]:
    normalized = _norm(value)
    words = set(WORD.findall(normalized))
    for run in CJK_RUN.findall(normalized):
        if len(run) == 1:
            words.add(run)
        else:
            words.update(run[index:index + 2] for index in range(len(run) - 1))
    return words


def _evidence(section: str) -> list[str]:
    return evidence_items(section)


def _evidence_keys(section: str) -> set[str]:
    """Lookup keys for local-file evidence in this section (URLs/test:/etc. skipped)."""
    return {evidence_lookup_key(item) for item in _evidence(section) if is_file_evidence(item)}


def _excerpt(section: str) -> str:
    text = section.split("\nEvidence:", 1)[0].strip().replace("\n", " ")
    return text[:500]


@dataclass(frozen=True)
class Candidate:
    fields: dict[str, str]
    path: Path
    section: str
    version: int
    updated: str
    source_project_id: str | None = None
    source_project_name: str | None = None
    historical: bool = False

    def payload(self, root: Path, score: int) -> dict[str, object]:
        payload: dict[str, object] = {
            "knowledge_id": self.fields["knowledge_id"], "version": self.version,
            "kind": self.fields["type"], "title": self.fields["title"],
            "status": self.fields["status"], "score": score,
            "path": self.path.relative_to(root).as_posix(), "evidence": _evidence(self.section),
            "updated": self.updated, "excerpt": _excerpt(self.section),
        }
        if self.source_project_id is not None:
            payload["source_project"] = {
                "project_id": self.source_project_id,
                "name": self.source_project_name or self.source_project_id,
            }
        return payload


def _pages(
    root: Path,
    projects: tuple[ProjectRecord, ...],
    scope: str,
    project_knowledge_roots: Mapping[str, Path] | None = None,
) -> list[tuple[Path, Path, ProjectRecord | None]]:
    selected: list[tuple[Path, Path, ProjectRecord | None]] = []
    if scope in {"project", "all"}:
        for project in projects:
            directory = (project_knowledge_roots or {}).get(
                project.project_id,
                root / project.relative_path / "knowledge",
            )
            if directory.exists():
                selected.extend(
                    (
                        path,
                        root / project.relative_path / "knowledge" / path.relative_to(directory),
                        project,
                    )
                    for path in directory.rglob("*.md")
                )
    if scope in {"domain", "all"}:
        directory = root / "02-domain" / "knowledge"
        selected.extend((path, path, None) for path in directory.glob("*.md") if directory.exists())
    if scope in {"pattern", "all"}:
        directory = root / "03-patterns" / "knowledge"
        selected.extend((path, path, None) for path in directory.glob("*.md") if directory.exists())
    return sorted(selected, key=lambda item: item[1].as_posix())


def _candidates(root: Path, projects: tuple[ProjectRecord, ...], scope: str, include_history: bool, as_of: date | None, project_knowledge_roots: Mapping[str, Path] | None = None) -> tuple[list[Candidate], list[Candidate], list[str]]:
    current: list[Candidate] = []
    history: list[Candidate] = []
    warnings: list[str] = []
    for source_path, path, source in _pages(root, projects, scope, project_knowledge_roots):
        content = read_bytes_shared(source_path).decode("utf-8").replace("\r\n", "\n")
        fields = _front(content)
        required = {"schema_version", "knowledge_id", "type", "title", "status", "version", "updated"}
        if fields.get("schema_version") != "2" or not required <= fields.keys():
            warnings.append(f"{path.relative_to(root).as_posix()}: invalid schema-v2 authority")
            continue
        section = CURRENT.search(content)
        if section is None:
            warnings.append(f"{path.relative_to(root).as_posix()}: missing Current section")
            continue
        versions = [Candidate(fields, path, section.group(1).strip(), int(fields["version"]), fields["updated"], source_project_id=source.project_id if source else None, source_project_name=source.name if source else None)]
        for version, updated, body in HISTORY.findall(content):
            versions.append(Candidate(fields, path, body.strip(), int(version), updated, True, source.project_id if source else None, source.name if source else None))
        if as_of is not None:
            eligible = [item for item in versions if date.fromisoformat(item.updated) <= as_of]
            if not eligible:
                continue
            chosen = max(eligible, key=lambda item: (item.updated, item.version))
            current.append(chosen)
            if include_history:
                history.extend(item for item in eligible if item is not chosen)
        else:
            current.append(versions[0])
            if include_history:
                history.extend(versions[1:])
    return current, history, warnings


def _score(candidate: Candidate, query: str) -> int:
    normalized = _norm(query)
    query_tokens = _tokens(query)
    title_tokens = _tokens(candidate.fields["title"])
    evidence_tokens = _tokens(" ".join(_evidence(candidate.section)))
    score = 10 if candidate.fields.get("status") == "current" else 0
    if normalized == _norm(candidate.fields["knowledge_id"]): score += 100
    score += 12 * len(query_tokens & title_tokens)
    score += 10 * len(query_tokens & evidence_tokens)
    score += 4 * len(query_tokens & _tokens(candidate.section))
    return score


def _has_meaningful_overlap(candidate: Candidate, query: str) -> bool:
    """Require real query overlap; lifecycle base score alone never returns."""
    if _norm(query) == _norm(candidate.fields["knowledge_id"]):
        return True
    query_tokens = _tokens(query)
    effective = query_tokens - STOPWORDS
    strong = (
        _tokens(candidate.fields["title"])
        | _tokens(" ".join(_evidence(candidate.section)))
        | _tokens(candidate.fields["knowledge_id"])
    )
    body = _tokens(candidate.section)
    return bool(effective & strong) or bool(effective & body)


def context(root: Path, project: Path, project_id: str, name: str, slug: str, query: str, *, projects: tuple[ProjectRecord, ...] | None = None, include_history: bool = False, as_of: date | None = None, status: str = "current", kind: str | None = None, allowed_kinds: tuple[str, ...] | None = None, scope: str = "project", max_results: int = 10, max_chars: int = 20000, project_knowledge_roots: Mapping[str, Path] | None = None, evidence_keys: tuple[str, ...] = ()) -> dict[str, object]:
    has_query = bool(query.strip())
    if not has_query and not evidence_keys:
        raise ValueError("INVALID_REQUEST: query or evidence-path is required")
    if evidence_keys and (scope != "project" or as_of is not None):
        raise ValueError("INVALID_REQUEST: evidence-path supports only project scope at the current snapshot")
    if max_results < 1 or max_chars < 1:
        raise ValueError("INVALID_REQUEST: result limits must be positive")
    selected_projects = projects or (ProjectRecord(project_id, name, str(project.relative_to(root).as_posix())),)
    candidates, available_history, warnings = _candidates(
        root,
        selected_projects,
        scope,
        include_history,
        as_of,
        project_knowledge_roots,
    )
    wanted = set(evidence_keys)
    selected = [item for item in candidates if (status == "all" or item.fields["status"] == status) and (kind is None or item.fields["type"] == kind) and (allowed_kinds is None or item.fields["type"] in allowed_kinds)]
    scored: list[tuple[Candidate, int, bool]] = []
    for item in selected:
        evidence_hit = bool(wanted & _evidence_keys(item.section)) if wanted else False
        eligible = evidence_hit or (has_query and _has_meaningful_overlap(item, query))
        if not eligible:
            continue
        scored.append((item, _score(item, query) if has_query else 0, evidence_hit))
    ranked = sorted(
        scored,
        key=lambda triple: (-int(triple[2]), -triple[1], _recency_key(triple[0].updated), triple[0].fields["knowledge_id"]),
    )
    payload: list[dict[str, object]] = []
    used = 0
    for item, score, evidence_hit in ranked[:max_results]:
        value = item.payload(root, score)
        if wanted:
            value["evidence_match"] = evidence_hit
        size = len(str(value))
        if payload and used + size > max_chars: break
        payload.append(value); used += size
    historical: list[dict[str, object]] = []
    if include_history:
        ids = {value["knowledge_id"] for value in payload}
        for item in available_history:
            if item.historical and item.fields["knowledge_id"] in ids:
                historical.append(item.payload(root, _score(item, query)))
    return {"schema_version": 1, "project": {"project_id": project_id, "name": name, "identity": project_id, "slug": slug}, "queried_projects": [{"project_id": item.project_id, "name": item.name, "slug": item.slug} for item in selected_projects], "query": query, "current_context": payload, "historical_context": historical, "warnings": sorted(set(warnings)), "truncated": len(payload) < min(len(ranked), max_results)}
