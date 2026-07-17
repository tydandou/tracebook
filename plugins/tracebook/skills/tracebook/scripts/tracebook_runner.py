"""Deterministic internal operations used by the Tracebook Skill."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.capture import (
        CaptureRequest,
        CaptureResult,
        capture_knowledge,
        capture_lock_name,
        validate_capture,
    )
    from scripts.check_knowledge import CheckReport, DeepAuditReport, run_check, run_deep_audit
    from scripts.knowledge_root import DEFAULT_TEMPLATE, repair_knowledge_root, validate_external_root
    from scripts.project_registry import ProjectRecord, ensure_project, repository_root
    from scripts.transaction import recover_transactions
else:
    from .capture import (
        CaptureRequest,
        CaptureResult,
        capture_knowledge,
        capture_lock_name,
        validate_capture,
    )
    from .check_knowledge import CheckReport, DeepAuditReport, run_check, run_deep_audit
    from .knowledge_root import DEFAULT_TEMPLATE, repair_knowledge_root, validate_external_root
    from .project_registry import ProjectRecord, ensure_project, repository_root
    from .transaction import recover_transactions


def default_root() -> Path:
    configured = os.environ.get("TRACEBOOK_ROOT", "~/.tracebook").strip()
    return Path(configured or "~/.tracebook").expanduser()


@dataclass(frozen=True)
class InitializeResult:
    root: Path
    created_paths: tuple[Path, ...]


@dataclass(frozen=True)
class ResolvedContext:
    root: Path
    record: ProjectRecord
    read_paths: tuple[Path, ...]


def initialize(root: Path, template: Path = DEFAULT_TEMPLATE) -> InitializeResult:
    """Repair missing template files while preserving existing knowledge."""
    created = repair_knowledge_root(root, template)
    return InitializeResult(
        root=root.expanduser().resolve(),
        created_paths=created,
    )


def resolve(root: Path, cwd: Path) -> ResolvedContext:
    """Initialize a root, register a repository, and return default context."""
    repository = repository_root(cwd)
    resolved_root, repository = validate_external_root(root, repository)
    recover_transactions(resolved_root)
    initialized = initialize(resolved_root)
    record = ensure_project(initialized.root, repository)
    project = initialized.root / record.relative_path
    return ResolvedContext(
        root=initialized.root,
        record=record,
        read_paths=(
            initialized.root / "AGENTS.md",
            initialized.root / "00-global" / "health" / "health-status.md",
            project / "index.md",
            project / "project-status.md",
        ),
    )
def capture(
    context: ResolvedContext, request: CaptureRequest, today: date
) -> CaptureResult:
    """Persist an explicitly classified durable knowledge entry."""
    return capture_knowledge(context.root, context.record, request, today)


@dataclass(frozen=True)
class CheckResult:
    report: CheckReport
    changed_paths: tuple[Path, ...]
    new_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class DeepAuditResult:
    report: DeepAuditReport
    changed_paths: tuple[Path, ...]
    new_paths: tuple[Path, ...] = ()


def _append_once(path: Path, text: str) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if text in current:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(current + text, encoding="utf-8")
    return True


def _set_health_value(content: str, key: str, value: str) -> str:
    pattern = rf"(?m)^- {re.escape(key)}:.*$"
    replacement = f"- {key}: {value}"
    if re.search(pattern, content):
        return re.sub(pattern, replacement, content)
    marker = "## Current Risk Level"
    return content.replace(marker, replacement + "\n\n" + marker)


def _health_number(content: str, key: str) -> int:
    match = re.search(rf"(?m)^- {re.escape(key)}:\s*(\d+)\s*$", content)
    return int(match.group(1)) if match else 0


def _set_risk_level(content: str, risk: str) -> str:
    pattern = r"(?ms)(## Current Risk Level\s*\n\s*).*?(?=\n## |\Z)"
    return re.sub(pattern, rf"\1{risk}", content, count=1)


def _upsert_generated_issues(content: str, issues: list[str]) -> str:
    start = "<!-- tracebook:generated-issues:start -->"
    end = "<!-- tracebook:generated-issues:end -->"
    lines = [start, *(f"- [High] {issue}" for issue in sorted(set(issues))), end]
    block = "\n".join(lines)
    pattern = rf"(?s){re.escape(start)}.*?{re.escape(end)}"
    if re.search(pattern, content):
        return re.sub(pattern, block, content, count=1)
    if "None recorded." in content:
        return content.replace("None recorded.", block)
    return content.replace("## Open Issues\n", "## Open Issues\n\n" + block + "\n", 1)

def check(
    context: ResolvedContext,
    changed_paths: list[Path],
    today: date,
    source_root: Path | None = None,
    new_paths: list[Path] | None = None,
) -> CheckResult:
    """Run and persist actual health checks without touching business code."""
    project = context.root / context.record.relative_path
    report = run_check(context.root, project, changed_paths, today, source_root)
    if report.check_type in {"Local", "Deep"}:
        return CheckResult(report=report, changed_paths=())

    health = context.root / "00-global" / "health" / "health-status.md"
    content = health.read_text(encoding="utf-8")
    content = _set_health_value(content, f"Last {report.check_type} Check", today.isoformat())
    changes = 0 if report.check_type in {"Regular", "Deep"} else _health_number(content, "Changes Since Last Regular Check") + len(set(changed_paths))
    new_page_count = 0 if report.check_type in {"Regular", "Deep"} else _health_number(content, "New Pages Since Last Regular Check") + len(set(new_paths or []))
    content = _set_health_value(content, "Changes Since Last Regular Check", str(changes))
    content = _set_health_value(content, "New Pages Since Last Regular Check", str(new_page_count))
    content = _set_health_value(content, "Pending Confirmations", str(len(report.pending_confirmations)))
    content = _set_health_value(content, "Missing Sources", str(len(report.missing_sources)))
    content = _set_health_value(content, "Broken Links", str(len(report.broken_links)))
    content = _set_health_value(content, "Orphan Pages", str(len(report.orphan_pages)))

    risks = report.broken_links + report.missing_sources + report.outdated_paths
    content = _upsert_generated_issues(content, risks)
    risk_level = "High" if risks else "Medium" if (report.pending_confirmations or report.duplicate_pages or report.log_growth or report.ambiguous_wikilinks) else "Low"
    content = _set_risk_level(content, risk_level)
    health.write_text(content, encoding="utf-8")

    log = context.root / "00-global" / "health" / "logs" / f"{today:%Y-%m}.md"
    _append_once(log, report.to_markdown() + "\n")
    return CheckResult(report=report, changed_paths=(health, log))


def audit(
    context: ResolvedContext, today: date, source_root: Path | None = None
) -> DeepAuditResult:
    """Persist an explicit Deep Audit without changing business repositories."""
    project = context.root / context.record.relative_path
    report = run_deep_audit(context.root, project, source_root)
    health = context.root / "00-global" / "health" / "health-status.md"
    content = health.read_text(encoding="utf-8")
    content = _set_health_value(content, "Last Deep Check", today.isoformat())
    content = _set_health_value(content, "Missing Sources", str(len(report.missing_source_paths)))
    risks = report.missing_source_paths
    content = _upsert_generated_issues(content, risks)
    risk_level = "High" if risks else "Medium" if (report.fact_candidates or report.root_cause_candidates or report.status_log_drift) else "Low"
    content = _set_risk_level(content, risk_level)
    health.write_text(content, encoding="utf-8")

    log = context.root / "00-global" / "health" / "logs" / f"{today:%Y-%m}.md"
    _append_once(log, report.to_markdown() + "\n")
    return DeepAuditResult(report=report, changed_paths=(health, log))
def _parse_date(value: str | None) -> date:
    return date.fromisoformat(value) if value else date.today()


def _context_payload(context: ResolvedContext) -> dict[str, object]:
    return {
        "root": str(context.root),
        "project": {
            "identity": context.record.identity,
            "slug": context.record.slug,
            "relative_path": context.record.relative_path,
        },
        "read_paths": [str(path) for path in context.read_paths],
    }


def _write_payload(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    """Expose the runner without requiring an installed Python package."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    initialize_parser = commands.add_parser("initialize")
    initialize_parser.add_argument("--root")

    for name in ("resolve", "capture", "check", "audit"):
        command = commands.add_parser(name)
        command.add_argument("--root")
        command.add_argument("--cwd", required=True)

    capture_parser = commands.choices["capture"]
    capture_parser.add_argument("--request", required=True)
    capture_parser.add_argument("--today")

    check_parser = commands.choices["check"]
    check_parser.add_argument("--changed", action="append", default=[])
    check_parser.add_argument("--new-path", action="append", default=[])
    check_parser.add_argument("--source-root")
    check_parser.add_argument("--today")

    audit_parser = commands.choices["audit"]
    audit_parser.add_argument("--source-root")
    audit_parser.add_argument("--today")


    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else default_root()
    if args.command == "initialize":
        result = initialize(root)
        _write_payload(
            {"root": str(result.root), "created_paths": [str(path) for path in result.created_paths]}
        )
        return 0

    context = resolve(root, Path(args.cwd))
    if args.command == "resolve":
        _write_payload(_context_payload(context))
        return 0

    if args.command == "audit":
        result = audit(
            context,
            _parse_date(args.today),
            Path(args.source_root) if args.source_root else None,
        )
        _write_payload(
            {
                "changed_paths": [str(path) for path in result.changed_paths],
                "report": result.report.to_markdown(),
            }
        )
        return 0
    if args.command == "capture":
        request_payload = json.loads(Path(args.request).read_text(encoding="utf-8"))
        result = capture(context, CaptureRequest(**request_payload), _parse_date(args.today))
        _write_payload(
            {
                "changed_paths": [str(path) for path in result.changed_paths],
                "new_paths": [str(path) for path in result.new_paths],
                "skipped": result.skipped,
            }
        )
        return 0

    result = check(
        context,
        [Path(path) for path in args.changed],
        _parse_date(args.today),
        Path(args.source_root) if args.source_root else None,
        [Path(path) for path in args.new_path],
    )
    _write_payload(
        {
            "check_type": result.report.check_type,
            "changed_paths": [str(path) for path in result.changed_paths],
            "report": result.report.to_markdown(),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
