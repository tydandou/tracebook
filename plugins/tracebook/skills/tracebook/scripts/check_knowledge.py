"""Read-only health checks for an external Tracebook knowledge root."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re


MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
WIKILINK = re.compile(r"(!)?\[\[([^\]\n]+)\]\]")
SOURCE_PATH = re.compile(r"`([^`\n:]+):L\d+(?:-L\d+)?`")
STATUS_LINE = re.compile(r"^- ([^:]+):\s*(.+)$", re.MULTILINE)


@dataclass
class CheckReport:
    check_type: str
    trigger_reasons: list[str]
    broken_links: list[str]
    ambiguous_wikilinks: list[str]
    orphan_pages: list[str]
    missing_sources: list[str]
    outdated_paths: list[str]
    pending_confirmations: list[str]
    duplicate_pages: list[str]
    log_growth: list[str]
    entity_issues: list[str]

    def to_markdown(self) -> str:
        sections = [
            ("Check Type", [self.check_type]),
            ("Trigger Reason", self.trigger_reasons),
            ("Broken Links", self.broken_links),
            ("Ambiguous Wikilinks", self.ambiguous_wikilinks),
            ("Orphan Pages", self.orphan_pages),
            ("Missing Sources", self.missing_sources),
            ("Outdated Source Map Paths", self.outdated_paths),
            ("Pending Confirmations", self.pending_confirmations),
            ("Schema-v2 Entity Integrity", self.entity_issues),
        ]
        lines = ["## Knowledge Health Check", ""]
        for heading, values in sections:
            lines.extend([f"### {heading}", ""])
            lines.extend(f"- {value}" for value in values) if values else lines.append("- None")
            lines.append("")
        return "\n".join(lines)


@dataclass
class DeepAuditReport:
    fact_candidates: list[str]
    missing_source_paths: list[str]
    root_cause_candidates: list[str]
    status_log_drift: list[str]

    def to_markdown(self) -> str:
        sections = [
            ("Fact Candidates", self.fact_candidates),
            ("Missing Source Paths", self.missing_source_paths),
            ("Root-Cause Candidates", self.root_cause_candidates),
            ("Status Log Drift", self.status_log_drift),
        ]
        lines = ["## Deep Knowledge Audit", ""]
        for heading, values in sections:
            lines.extend([f"### {heading}", ""])
            lines.extend(f"- {value}" for value in values) if values else lines.append("- None")
            lines.append("")
        lines.extend(["### Need Human Review", "", "- Review every candidate against its evidence; this report does not assert business truth.", ""])
        return "\n".join(lines)
def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _status_values(root: Path) -> dict[str, str]:
    path = root / "00-global" / "health" / "health-status.md"
    if not path.exists():
        return {}
    return dict(STATUS_LINE.findall(path.read_text(encoding="utf-8")))


def _number(values: dict[str, str], key: str) -> int:
    try:
        return int(values.get(key, "0"))
    except ValueError:
        return 0


def _last_date(values: dict[str, str], key: str) -> date | None:
    try:
        return date.fromisoformat(values[key])
    except (KeyError, ValueError):
        return None


def _trigger(
    values: dict[str, str], changed_paths: list[Path], now: date
) -> tuple[str, list[str]]:
    names = {path.name for path in changed_paths}
    deep_reasons: list[str] = []
    last_deep = _last_date(values, "Last Deep Check")
    if last_deep and (now - last_deep).days > 30:
        deep_reasons.append("More than 30 days since the last Deep check")
    for path in changed_paths:
        if path.name in {"business-rules.md", "source-map.md", "api.md", "database.md"} and path.exists():
            if len(path.read_text(encoding="utf-8").splitlines()) > 300:
                deep_reasons.append(f"{path.name} exceeds 300 lines")
    if deep_reasons:
        return "Deep", deep_reasons

    regular_reasons: list[str] = []
    last_regular = _last_date(values, "Last Regular Check")
    if last_regular and (now - last_regular).days > 7:
        regular_reasons.append("More than 7 days since the last Regular check")
    thresholds = (
        ("Changes Since Last Regular Check", 10),
        ("New Pages Since Last Regular Check", 5),
        ("Pending Confirmations", 10),
        ("Missing Sources", 10),
    )
    for key, threshold in thresholds:
        if _number(values, key) >= threshold:
            regular_reasons.append(f"{key} >= {threshold}")
    if regular_reasons:
        return "Regular", regular_reasons

    if changed_paths:
        return "Light", ["Knowledge files changed"]
    return "Local", ["No Light, Regular, or Deep trigger"]


def _markdown_files(project_dir: Path) -> list[Path]:
    return sorted(project_dir.rglob("*.md"))


PageContents = dict[Path, str]


def _load_page_contents(project_dir: Path) -> PageContents:
    return {
        page: page.read_text(encoding="utf-8")
        for page in _markdown_files(project_dir)
    }

def _broken_links(root: Path, pages: PageContents) -> list[str]:
    broken: list[str] = []
    for page, content in pages.items():
        for target in MARKDOWN_LINK.findall(content):
            target = target.strip().split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (page.parent / target).resolve().exists():
                broken.append(f"{_relative(root, page)} -> {target}")
    return sorted(set(broken))

def _wikilink_target(raw_target: str) -> str:
    return raw_target.split("|", 1)[0].split("#", 1)[0].strip()


def _is_inside_root(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _wikilink_matches(
    root: Path,
    project_dir: Path,
    page: Path,
    target: str,
    pages: PageContents,
) -> list[Path]:
    target_path = Path(target)
    has_separator = "/" in target or "\\" in target
    is_markdown = target_path.suffix.lower() in {"", ".md"}
    if is_markdown and not has_separator:
        stem = target_path.stem.casefold()
        return [candidate for candidate in pages if candidate.stem.casefold() == stem]

    candidates = [target_path]
    if is_markdown and not target_path.suffix:
        candidates.append(target_path.with_suffix(".md"))

    matches: set[Path] = set()
    for directory in (page.parent, project_dir, root):
        for candidate in candidates:
            resolved = (directory / candidate).resolve()
            if _is_inside_root(root, resolved) and resolved.is_file():
                matches.add(resolved)
    return sorted(matches)


def _broken_wikilinks(
    root: Path, project_dir: Path, pages: PageContents
) -> tuple[list[str], list[str]]:
    broken: list[str] = []
    ambiguous: list[str] = []
    for page, content in pages.items():
        for embedded, raw_target in WIKILINK.findall(content):
            target = _wikilink_target(raw_target)
            if not target:
                continue
            matches = _wikilink_matches(root, project_dir, page, target, pages)
            link = f"{embedded}[[{raw_target}]]"
            if not matches:
                broken.append(f"{_relative(root, page)} -> {link}")
            elif len(matches) > 1 and "/" not in target and "\\" not in target:
                ambiguous.append(
                    f"{_relative(root, page)} -> {link} matches {len(matches)} pages"
                )
    return sorted(set(broken)), sorted(set(ambiguous))

def _orphan_pages(
    root: Path,
    project_dir: Path,
    changed_paths: list[Path],
    pages: PageContents,
) -> list[str]:
    all_text = "\n".join(pages.values())
    exempt = {"index.md", "project-status.md", "source-map.md"}
    orphans: list[str] = []
    for page in changed_paths:
        if (
            page.name in exempt
            or "logs" in page.relative_to(project_dir).parts
            or not page.exists()
            or page.suffix != ".md"
        ):
            continue
        relative_to_project = page.relative_to(project_dir).as_posix()
        if relative_to_project not in all_text:
            orphans.append(_relative(root, page))
    return sorted(set(orphans))

def _missing_sources(
    root: Path, project_dir: Path, changed_paths: list[Path], pages: PageContents
) -> list[str]:
    missing: list[str] = []
    exempt = {"index.md", "project-status.md", "source-map.md"}
    for page in changed_paths:
        if (
            page.name in exempt
            or "logs" in page.relative_to(project_dir).parts
            or not page.exists()
            or page.suffix != ".md"
        ):
            continue
        content = pages.get(page)
        if content is None:
            content = page.read_text(encoding="utf-8")
        body = [line for line in content.splitlines() if line.strip() and not line.startswith("#")]
        has_source = _has_evidence(content)
        is_pending = PENDING_STATUS.search(content) is not None
        if body and not has_source and not is_pending:
            missing.append(_relative(root, page))
    return sorted(set(missing))

def _outdated_paths(
    root: Path, pages: PageContents, source_root: Path | None
) -> list[str]:
    if source_root is None:
        return []
    outdated: list[str] = []
    for source_map, content in pages.items():
        if not source_map.name.startswith("source-map"):
            continue
        for source_path in SOURCE_PATH.findall(content):
            if not (source_root / source_path).is_file():
                outdated.append(f"{_relative(root, source_map)} -> {source_path}")
    return sorted(set(outdated))

def _pending_confirmations(root: Path, pages: PageContents) -> list[str]:
    pending: list[str] = []
    for page, content in pages.items():
        for number, line in enumerate(content.splitlines(), 1):
            if PENDING_STATUS.fullmatch(line):
                pending.append(f"{_relative(root, page)}:L{number}")
    return pending

def _duplicate_pages(root: Path, pages: PageContents) -> list[str]:
    fingerprints: dict[str, Path] = {}
    duplicates: list[str] = []
    for page, content in pages.items():
        relative = page.relative_to(root)
        if page.name in {"index.md", "project-status.md"} or "logs" in relative.parts:
            continue
        lines = [
            line.strip().casefold()
            for line in content.splitlines()
            if line.strip() and not line.startswith("#") and line.strip() != "---"
        ]
        fingerprint = "\n".join(lines)
        if not fingerprint:
            continue
        first = fingerprints.get(fingerprint)
        if first is None:
            fingerprints[fingerprint] = page
        else:
            duplicates.append(f"{_relative(root, first)} <-> {_relative(root, page)}")
    return sorted(duplicates)


ENTITY_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
ENTITY_HISTORY_VERSION = re.compile(r"(?m)^### Version (\d+) — (\d{4}-\d{2}-\d{2})$")
ENTITY_EVENT = re.compile(r"<!-- tracebook:event:[0-9a-f]{16} -->")
ENTITY_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def _entity_fields(content: str) -> dict[str, str] | None:
    match = ENTITY_FRONTMATTER.match(content)
    if match is None:
        return None
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip()
    return values if values.get("schema_version") == "2" else None


def _schema_v2_entity_issues(root: Path, pages: PageContents) -> list[str]:
    issues: list[str] = []
    authorities: dict[tuple[str, str, str, str], Path] = {}
    entities: dict[tuple[str, str, str, str], tuple[Path, dict[str, str], str]] = {}
    for page, content in pages.items():
        fields = _entity_fields(content)
        if fields is None:
            continue
        relative = _relative(root, page)
        required = ("type", "scope", "project", "knowledge_id", "status", "version", "created", "updated")
        missing = [field for field in required if not fields.get(field)]
        knowledge_id = fields.get("knowledge_id", "")
        if missing or ENTITY_SLUG.fullmatch(knowledge_id) is None:
            issues.append(f"{relative}: invalid schema-v2 frontmatter")
            continue
        try:
            version = int(fields["version"])
        except ValueError:
            issues.append(f"{relative}: version is invalid")
            continue
        history = [int(value) for value, _ in ENTITY_HISTORY_VERSION.findall(content)]
        if version < 1 or sorted(history, reverse=True) != list(range(version - 1, 0, -1)):
            issues.append(f"{relative}: version history is not contiguous")
        if not ENTITY_EVENT.findall(content):
            issues.append(f"{relative}: entity has no event marker")
        if fields.get("status") == "current" and not _has_evidence(content):
            issues.append(f"{relative}: Current entity has no evidence")
        key = (fields["scope"], fields["project"], fields["type"], knowledge_id)
        if key in authorities:
            issues.append(f"{_relative(root, authorities[key])} <-> {relative}: duplicate authority")
        else:
            authorities[key] = page
            entities[key] = (page, fields, content)
    for key, (page, fields, _) in entities.items():
        replacement = fields.get("replacement_knowledge_id", "null")
        if fields.get("status") == "superseded":
            replacement_key = (key[0], key[1], key[2], replacement)
            replacement_entity = entities.get(replacement_key)
            if replacement == key[3] or replacement_entity is None:
                issues.append(f"{_relative(root, page)}: replacement is missing or self-referential")
            elif replacement_entity[1].get("status") in {"deprecated", "superseded"}:
                issues.append(f"{_relative(root, page)}: replacement is inactive")
    return sorted(set(issues))

def _log_growth(root: Path, pages: PageContents) -> list[str]:
    growth: list[str] = []
    for log, content in pages.items():
        if "logs" not in log.relative_to(root).parts:
            continue
        lines = len(content.splitlines())
        if lines > 300:
            growth.append(f"{_relative(root, log)}: {lines} lines")
    return growth

FACT_MARKER = re.compile(r"\b\d+(?:\.\d+)?\b|\b[A-Z][A-Z0-9_]{2,}\b")


EVIDENCE_HEADING = re.compile(r"^\s*(?:evidence|sources?):\s*$", re.IGNORECASE)
EVIDENCE_ITEM = re.compile(r"^[-*+]\s+\S")
ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)")
LEVEL_TWO_HEADING = re.compile(r"^ {0,3}##(?:[ \t]+|$)")
PENDING_STATUS = re.compile(
    r"^[ \t]*(?:status:[ \t]*)?pending[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


def _has_evidence(content: str) -> bool:
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if not EVIDENCE_HEADING.fullmatch(line):
            continue
        for candidate in lines[index + 1:]:
            stripped = candidate.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                break
            if EVIDENCE_ITEM.match(stripped):
                return True
    return False

DEEP_EXCLUDED_PAGES = {"index.md", "project-status.md", "health-status.md"}
DEEP_EXCLUDED_DIRECTORIES = {"archive", "logs"}


def _deep_pages(scope_dir: Path) -> list[Path]:
    pages: list[Path] = []
    for page in _markdown_files(scope_dir):
        relative = page.relative_to(scope_dir)
        if page.name in DEEP_EXCLUDED_PAGES:
            continue
        if DEEP_EXCLUDED_DIRECTORIES.intersection(relative.parts):
            continue
        pages.append(page)
    return pages


def _entry_sections(content: str) -> list[list[tuple[int, str]]]:
    sections: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    in_frontmatter = content.startswith("---\n")
    for number, line in enumerate(content.splitlines(), 1):
        if in_frontmatter:
            if number > 1 and line.strip() == "---":
                in_frontmatter = False
            continue
        if LEVEL_TWO_HEADING.match(line) and current:
            sections.append(current)
            current = []
        current.append((number, line))
    if current:
        sections.append(current)
    return sections


def _fact_candidates(root: Path, pages: list[Path]) -> list[str]:
    candidates: list[str] = []
    for page in pages:
        content = page.read_text(encoding="utf-8")
        for section in _entry_sections(content):
            section_content = "\n".join(line for _, line in section)
            if _has_evidence(section_content) or PENDING_STATUS.search(section_content):
                continue
            for number, line in section:
                if ATX_HEADING.match(line) or not line.strip() or line.lower().startswith(("status:", "source:", "evidence:")):
                    continue
                if FACT_MARKER.search(line):
                    candidates.append(f"{_relative(root, page)}:L{number}: factual claim requires evidence review")
    return candidates


def _missing_audit_sources(root: Path, pages: list[Path], source_root: Path | None) -> list[str]:
    if source_root is None:
        return ["Source root was not provided for Deep Audit"]
    missing: list[str] = []
    for page in pages:
        for source_path in SOURCE_PATH.findall(page.read_text(encoding="utf-8")):
            if not (source_root / source_path).is_file():
                missing.append(f"{_relative(root, page)} -> {source_path}")
    return sorted(set(missing))


def _root_cause_candidates(root: Path, pages: list[Path]) -> list[str]:
    candidates: list[str] = []
    for page in pages:
        for number, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            if "root cause" in line.lower() or "根因" in line:
                candidates.append(f"{_relative(root, page)}:L{number}: root-cause claim requires human review")
    return candidates


def _status_log_drift(root: Path, project_dir: Path) -> list[str]:
    status = project_dir / "project-status.md"
    logs = project_dir / "logs"
    if not status.exists() or not logs.exists():
        return []
    return [
        f"{_relative(root, status)} is older than {_relative(project_dir, log)}"
        for log in sorted(logs.glob("*.md"))
        if log.stat().st_mtime > status.stat().st_mtime
    ]


def run_deep_audit(root: Path, project_dir: Path, source_root: Path | None = None) -> DeepAuditReport:
    """Generate evidence-review candidates without asserting business truth."""
    root = root.resolve()
    project_dir = project_dir.resolve()
    source = source_root.resolve() if source_root is not None else None
    pages = _deep_pages(project_dir)
    return DeepAuditReport(
        fact_candidates=_fact_candidates(root, pages),
        missing_source_paths=_missing_audit_sources(root, pages, source),
        root_cause_candidates=_root_cause_candidates(root, pages),
        status_log_drift=_status_log_drift(root, project_dir),
    )
def run_check(
    root: Path,
    project_dir: Path,
    changed_paths: list[Path],
    now: date,
    source_root: Path | None = None,
) -> CheckReport:
    """Inspect external knowledge without writing to the knowledge root."""
    root = root.resolve()
    project_dir = project_dir.resolve()
    changed = [path.resolve() for path in changed_paths]
    check_type, trigger_reasons = _trigger(_status_values(root), changed, now)
    pages = _load_page_contents(project_dir)
    broken_wikilinks, ambiguous_wikilinks = _broken_wikilinks(
        root, project_dir, pages
    )
    return CheckReport(
        check_type=check_type,
        trigger_reasons=trigger_reasons,
        broken_links=sorted(set(_broken_links(root, pages) + broken_wikilinks)),
        ambiguous_wikilinks=ambiguous_wikilinks,
        orphan_pages=_orphan_pages(root, project_dir, changed, pages),
        missing_sources=_missing_sources(root, project_dir, changed, pages),
        outdated_paths=_outdated_paths(root, pages, source_root),
        pending_confirmations=_pending_confirmations(root, pages),
        duplicate_pages=_duplicate_pages(root, pages) if check_type == "Regular" else [],
        log_growth=_log_growth(root, pages) if check_type == "Regular" else [],
        entity_issues=_schema_v2_entity_issues(root, pages),
    )
