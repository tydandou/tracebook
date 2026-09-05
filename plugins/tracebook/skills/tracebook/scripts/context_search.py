"""Deterministic schema-v2 Markdown context retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json
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


def _body(section: str) -> str:
    return section.split("\nEvidence:", 1)[0].strip()


@dataclass
class _ResultBudget:
    """Budget compact JSON array contents, excluding fixed envelope/brackets."""

    limit: int
    used: int = 0

    def append(self, target: list, value: object) -> bool:
        size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        size += int(bool(target))
        if self.used + size > self.limit:
            return False
        target.append(value)
        self.used += size
        return True


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

    def payload(self, root: Path, score: int, *, full_content: bool = False) -> dict[str, object]:
        body = _body(self.section)
        excerpt = body.replace("\n", " ")
        payload: dict[str, object] = {
            "knowledge_id": self.fields["knowledge_id"], "version": self.version,
            "kind": self.fields["type"], "title": self.fields["title"],
            "status": self.fields["status"], "score": score,
            # `status` belongs to the authority entity.  It is not a statement
            # that this particular version is still the live version.
            "historical": self.historical,
            "version_state": "historical" if self.historical else "current",
            "latest_version": int(self.fields["version"]),
            "path": self.path.relative_to(root).as_posix(), "evidence": _evidence(self.section),
            "updated": self.updated, "excerpt": excerpt[:500],
            "excerpt_truncated": len(excerpt) > 500,
            "replacement_knowledge_id": (
                self.fields.get("replacement_knowledge_id")
                if self.fields.get("status") == "superseded" else None
            ),
        }
        if full_content:
            payload["body"] = body
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
        # The normal Current-only path does not need to parse every historical
        # section.  This keeps the default read cheap while preserving exact
        # `--include-history` and `--as-of` behavior.
        if include_history or as_of is not None:
            for version, updated, body in HISTORY.findall(content):
                versions.append(Candidate(
                    fields,
                    path,
                    body.strip(),
                    int(version),
                    updated,
                    source_project_id=source.project_id if source else None,
                    source_project_name=source.name if source else None,
                    historical=True,
                ))
        if as_of is not None:
            eligible = [item for item in versions if date.fromisoformat(item.updated) <= as_of]
            if not eligible:
                continue
            chosen = max(eligible, key=lambda item: (item.updated, item.version))
            current.append(chosen)
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
    score = 10 if candidate.fields.get("status") == "current" and not candidate.historical else 0
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


def context(
    root: Path, project: Path, project_id: str, name: str, slug: str, query: str, *,
    projects: tuple[ProjectRecord, ...] | None = None,
    include_history: bool = False, as_of: date | None = None,
    status: str = "current", kind: str | None = None,
    allowed_kinds: tuple[str, ...] | None = None, scope: str = "project",
    max_results: int = 10, max_chars: int = 20000,
    project_knowledge_roots: Mapping[str, Path] | None = None,
    evidence_keys: tuple[str, ...] = (), knowledge_id: str | None = None,
    discover_history: bool = False, full_content: bool = False,
    query_warnings: tuple[str, ...] = (),
) -> dict[str, object]:
    has_query = bool(query.strip())
    can_search = has_query or bool(evidence_keys) or bool(knowledge_id)
    if not can_search and not query_warnings:
        raise ValueError("INVALID_REQUEST: query or evidence-path is required")
    if full_content and not knowledge_id:
        raise ValueError("INVALID_REQUEST: full-content requires knowledge-id")
    if evidence_keys and (scope != "project" or as_of is not None):
        raise ValueError("INVALID_REQUEST: evidence-path supports only project scope at the current snapshot")
    if max_results < 1 or max_chars < 1:
        raise ValueError("INVALID_REQUEST: result limits must be positive")
    selected_projects = projects or (ProjectRecord(project_id, name, str(project.relative_to(root).as_posix())),)
    inspect_history = include_history or discover_history or as_of is not None
    candidates, available_history, warnings = (
        _candidates(root, selected_projects, scope, include_history or discover_history,
                    as_of, project_knowledge_roots)
        if can_search else ([], [], [])
    )
    history_by_path: dict[Path, list[Candidate]] = {}
    for item in available_history:
        history_by_path.setdefault(item.path, []).append(item)
    wanted = set(evidence_keys)
    selected = [
        item for item in candidates
        if (knowledge_id is None or item.fields["knowledge_id"] == knowledge_id)
        and (status == "all" or item.fields["status"] == status)
        and (kind is None or item.fields["type"] == kind)
        and (allowed_kinds is None or item.fields["type"] in allowed_kinds)
    ]
    scored: list[tuple[Candidate, int, bool, Candidate]] = []
    for item in selected:
        evidence_hit = bool(wanted & _evidence_keys(item.section)) if wanted else False
        exact_id = knowledge_id is not None and item.fields["knowledge_id"] == knowledge_id
        direct = exact_id or evidence_hit or (has_query and _has_meaningful_overlap(item, query))
        matched = item
        if not direct:
            # History discovers only an already eligible entity. It never widens
            # status/kind/project filters or earns a Current evidence-path match.
            history_hits = [
                historical for historical in history_by_path.get(item.path, ())
                if discover_history and has_query and _has_meaningful_overlap(historical, query)
            ]
            if not history_hits:
                continue
            matched = max(history_hits, key=lambda hit: (_score(hit, query), hit.updated, hit.version))
        scored.append((item, _score(matched, query) if has_query else 0, evidence_hit, matched))
    ranked = sorted(
        scored,
        key=lambda row: (-int(row[2]), -row[1], _recency_key(row[0].updated),
                         row[0].fields["knowledge_id"], row[0].path.as_posix()),
    )
    budget = _ResultBudget(max_chars)
    payload: list[dict[str, object]] = []
    returned_items: list[Candidate] = []
    char_truncated = False
    for item, score, evidence_hit, matched in ranked[:max_results]:
        value = item.payload(root, score, full_content=full_content)
        value["match_source"] = "selected_version" if matched is item else "history"
        value["matched_version"] = matched.version
        if wanted:
            value["evidence_match"] = evidence_hit
        if not budget.append(payload, value):
            char_truncated = True
            break
        returned_items.append(item)

    omitted_current = [item for item, _, _, _ in ranked[len(payload):]]
    history_for_returned = [
        version for item in returned_items for version in history_by_path.get(item.path, ())
    ]
    history_for_omitted = [
        version for item in omitted_current for version in history_by_path.get(item.path, ())
    ]
    historical: list[dict[str, object]] = []
    if include_history:
        for item in history_for_returned:
            value = item.payload(root, _score(item, query), full_content=full_content)
            if not budget.append(historical, value):
                char_truncated = True
                break
    omitted_history = (
        history_for_returned[len(historical):] + history_for_omitted if include_history else []
    )
    all_warnings = sorted(set(warnings) | set(query_warnings))
    returned_warnings: list[str] = []
    for warning in all_warnings:
        if not budget.append(returned_warnings, warning):
            char_truncated = True
            break

    def omission_sample(items: list[Candidate]) -> tuple[list[dict[str, str]], bool]:
        # A path identifies the collection as well as the ID, including when
        # explicit multi-project or cross-kind reads contain identical IDs.
        unique = {item.path: item for item in items}
        sample: list[dict[str, str]] = []
        for item in list(unique.values())[:10]:
            value = {"knowledge_id": item.fields["knowledge_id"],
                     "path": item.path.relative_to(root).as_posix()}
            if not budget.append(sample, value):
                break
        return sample, len(sample) < len(unique)

    omitted_entities, omitted_samples_truncated = omission_sample(omitted_current)
    history_omitted_entities, history_samples_truncated = omission_sample(omitted_history)
    reasons: list[str] = []
    if len(ranked) > max_results:
        reasons.append("max_results")
    if char_truncated:
        reasons.append("max_chars")
    inspected = inspect_history and can_search
    history_count = len(history_for_returned) + len(history_for_omitted)
    return {
        "schema_version": 1,
        "project": {"project_id": project_id, "name": name, "identity": project_id, "slug": slug},
        "queried_projects": [{"project_id": item.project_id, "name": item.name, "slug": item.slug}
                             for item in selected_projects],
        "query": query,
        "as_of": as_of.isoformat() if as_of is not None else None,
        "current_context": payload,
        "historical_context": historical,
        "warnings": returned_warnings,
        "warning_count": len(all_warnings),
        "omitted_warning_count": len(all_warnings) - len(returned_warnings),
        "truncated": bool(reasons),
        "truncation_reason": reasons,
        "matched_count": len(ranked),
        "returned_count": len(payload) + len(historical),
        "returned_current_count": len(payload),
        "returned_history_count": len(historical),
        "omitted_current_count": len(omitted_current),
        "omitted_history_count": len(omitted_history),
        "omitted_entities": omitted_entities,
        "omitted_samples_truncated": omitted_samples_truncated,
        "history_omitted_entities": history_omitted_entities,
        "history_omitted_samples_truncated": history_samples_truncated,
        "history_inspected": inspected,
        "history_available": bool(history_count) if inspected else None,
        "history_available_count": history_count if inspected else None,
        "history_available_for_returned": len(history_for_returned) if inspected else None,
        "history_available_for_omitted": len(history_for_omitted) if inspected else None,
        "history_discovery": discover_history,
        "full_content": full_content,
        "budget_chars_used": budget.used,
        "budget_scope": "compact_json_array_contents",
    }
