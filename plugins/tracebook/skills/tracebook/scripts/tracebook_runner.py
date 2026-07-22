"""Deterministic internal operations used by the Tracebook Skill."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import date
import json
import os
from pathlib import Path
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
    from scripts.check_knowledge import (
        CheckReport,
        DeepAuditReport,
        _duplicate_pages,
        _load_page_contents,
        _log_growth,
        _trigger,
        run_check,
        run_deep_audit,
    )
    from scripts.context_search import context as build_context
    from scripts.errors import TracebookError, error_payload
    from scripts.health_state import (
        _finish_health_persistence,
        _load_scope_state,
        _persist_audit_under_lock,
        _persist_check_under_lock,
        _scope_lock_name,
        ensure_health_layout,
        rebuild_global_health,
    )
    from scripts.knowledge_root import language_for_root, repair_knowledge_root, validate_external_root
    from scripts.locking import file_lock
    from scripts.project_registry import ProjectRecord, ensure_project, repository_root
    from scripts.transaction import TransactionDiagnostic, inspect_transactions, recover_transactions
else:
    from .capture import (
        CaptureRequest,
        CaptureResult,
        capture_knowledge,
        capture_lock_name,
        validate_capture,
    )
    from .check_knowledge import (
        CheckReport,
        DeepAuditReport,
        _duplicate_pages,
        _load_page_contents,
        _log_growth,
        _trigger,
        run_check,
        run_deep_audit,
    )
    from .context_search import context as build_context
    from .errors import TracebookError, error_payload
    from .health_state import (
        _finish_health_persistence,
        _load_scope_state,
        _persist_audit_under_lock,
        _persist_check_under_lock,
        _scope_lock_name,
        ensure_health_layout,
        rebuild_global_health,
    )
    from .knowledge_root import language_for_root, repair_knowledge_root, validate_external_root
    from .locking import file_lock
    from .project_registry import ProjectRecord, ensure_project, repository_root
    from .transaction import TransactionDiagnostic, inspect_transactions, recover_transactions


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
    knowledge_language: str
    read_paths: tuple[Path, ...]


def initialize(root: Path, template: Path | None = None) -> InitializeResult:
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
    ensure_health_layout(initialized.root)
    with file_lock(
        initialized.root,
        f"project-{record.slug}",
        operation="resolve",
    ):
        ensure_health_layout(initialized.root, record)
    rebuild_global_health(initialized.root)
    project = initialized.root / record.relative_path
    return ResolvedContext(
        root=initialized.root,
        record=record,
        knowledge_language=language_for_root(initialized.root),
        read_paths=(
            initialized.root / "AGENTS.md",
            initialized.root / "00-global" / "health" / "health-status.md",
            project / "index.md",
            project / "project-status.md",
            project / "health-status.md",
        ),
    )
def capture(
    context: ResolvedContext, request: CaptureRequest, today: date
) -> CaptureResult:
    """Persist an explicitly classified durable knowledge entry."""
    return capture_knowledge(context.root, context.record, request, today)


def retrieve_context(
    resolved: ResolvedContext,
    query: str,
    *,
    include_history: bool = False,
    as_of: date | None = None,
    status: str = "current",
    kind: str | None = None,
    scope: str = "project",
    max_results: int = 10,
    max_chars: int = 20000,
) -> dict[str, object]:
    return build_context(
        resolved.root,
        resolved.root / resolved.record.relative_path,
        resolved.record.identity,
        resolved.record.slug,
        query,
        include_history=include_history,
        as_of=as_of,
        status=status,
        kind=kind,
        scope=scope,
        max_results=max_results,
        max_chars=max_chars,
    )


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


def _scope_scan_root(context: ResolvedContext, scope: str) -> Path:
    if scope == "project":
        return context.root / context.record.relative_path
    if scope == "domain":
        return context.root / "02-domain"
    if scope == "pattern":
        return context.root / "03-patterns"
    raise ValueError(f"Unsupported health scope: {scope}")


def _scope_trigger_values(
    context: ResolvedContext,
    scope: str,
    today: date,
) -> dict[str, str]:
    state = _load_scope_state(context.root, context.record, scope, today)
    return {
        "Last Regular Check": (
            state.last_regular.isoformat() if state.last_regular else "Not run"
        ),
        "Last Deep Check": state.last_deep.isoformat() if state.last_deep else "Not run",
        "Changes Since Last Regular Check": str(state.changes_since_regular),
        "New Pages Since Last Regular Check": str(state.new_pages_since_regular),
        "Pending Confirmations": str(state.pending_confirmations),
        "Missing Sources": str(state.missing_sources),
    }


def _run_scoped_check(
    context: ResolvedContext,
    scope: str,
    changed_paths: list[Path],
    today: date,
    source_root: Path | None,
) -> CheckReport:
    scan_root = _scope_scan_root(context, scope)
    check_type, trigger_reasons = _trigger(
        _scope_trigger_values(context, scope, today),
        changed_paths,
        today,
    )
    report = run_check(
        context.root,
        scan_root,
        changed_paths,
        today,
        source_root,
    )
    duplicate_pages: list[str] = []
    log_growth: list[str] = []
    if check_type == "Regular":
        pages = _load_page_contents(scan_root.resolve())
        duplicate_pages = _duplicate_pages(context.root.resolve(), pages)
        log_growth = _log_growth(context.root.resolve(), pages)
    return replace(
        report,
        check_type=check_type,
        trigger_reasons=trigger_reasons,
        duplicate_pages=duplicate_pages,
        log_growth=log_growth,
    )

def check(
    context: ResolvedContext,
    changed_paths: list[Path],
    today: date,
    source_root: Path | None = None,
    new_paths: list[Path] | None = None,
    scope: str = "project",
) -> CheckResult:
    """Run and persist actual health checks without touching business code."""
    selected_new_paths = new_paths or []
    with file_lock(
        context.root,
        _scope_lock_name(context.record, scope),
        operation="check",
    ):
        report = _run_scoped_check(
            context,
            scope,
            changed_paths,
            today,
            source_root,
        )
        committed = _persist_check_under_lock(
            context.root,
            context.record,
            scope,
            report,
            changed_paths,
            selected_new_paths,
            today,
        )
    persisted = _finish_health_persistence(context.root, committed)
    return CheckResult(
        report=report,
        changed_paths=persisted,
    )


def audit(
    context: ResolvedContext,
    today: date,
    source_root: Path | None = None,
    scope: str = "project",
) -> DeepAuditResult:
    """Persist an explicit Deep Audit without changing business repositories."""
    with file_lock(
        context.root,
        _scope_lock_name(context.record, scope),
        operation="audit",
    ):
        report = run_deep_audit(
            context.root,
            _scope_scan_root(context, scope),
            source_root,
        )
        committed = _persist_audit_under_lock(
            context.root,
            context.record,
            scope,
            report,
            today,
        )
    persisted = _finish_health_persistence(context.root, committed)
    return DeepAuditResult(report=report, changed_paths=persisted)
def _parse_date(value: str | None) -> date:
    return date.fromisoformat(value) if value else date.today()


def _context_payload(context: ResolvedContext) -> dict[str, object]:
    return {
        "root": str(context.root),
        "knowledge_language": context.knowledge_language,
        "project": {
            "identity": context.record.identity,
            "slug": context.record.slug,
            "relative_path": context.record.relative_path,
        },
        "read_paths": [str(path) for path in context.read_paths],
    }


def _write_payload(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _user_summary(
    context: ResolvedContext,
    request: CaptureRequest,
    result: CaptureResult,
) -> str | None:
    """Return a safe, user-facing confirmation only for an actual write."""
    if result.skipped or not result.changed_paths:
        return None

    verbs = {
        "create": "created",
        "revise": "revised",
        "change-status": "changed status for",
    }
    location = (
        f"project `{context.record.slug}`"
        if request.scope == "project"
        else f"{request.scope} scope"
    )
    return (
        f"Tracebook: {verbs[request.operation]} `{request.knowledge_id}` "
        f"({location}, kind `{request.kind}`)."
    )


def _transaction_payload(diagnostic: TransactionDiagnostic) -> dict[str, object]:
    return {
        "transaction_id": diagnostic.transaction_id,
        "operation": diagnostic.operation,
        "scope": diagnostic.scope,
        "state": diagnostic.state,
        "disposition": diagnostic.disposition,
        "issues": [
            {
                "code": issue.code,
                "message": issue.message,
                "target": str(issue.target) if issue.target is not None else None,
            }
            for issue in diagnostic.issues
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Expose the runner without requiring an installed Python package."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    initialize_parser = commands.add_parser("initialize")
    initialize_parser.add_argument("--root")

    transactions_parser = commands.add_parser("transactions")
    transactions_parser.add_argument("--root")

    recovery_parser = commands.add_parser("recover-transactions")
    recovery_parser.add_argument("--root")

    for name in ("resolve", "capture", "check", "audit", "context"):
        command = commands.add_parser(name)
        command.add_argument("--root")
        command.add_argument("--cwd", required=True)

    capture_parser = commands.choices["capture"]
    capture_parser.add_argument("--request", required=True)
    capture_parser.add_argument("--today")

    context_parser = commands.choices["context"]
    context_parser.add_argument("--query", required=True)
    context_parser.add_argument("--include-history", action="store_true")
    context_parser.add_argument("--as-of")
    context_parser.add_argument("--status", default="current")
    context_parser.add_argument("--kind")
    context_parser.add_argument("--scope", choices=("project", "domain", "pattern", "all"), default="project")
    context_parser.add_argument("--max-results", type=int, default=10)
    context_parser.add_argument("--max-chars", type=int, default=20000)

    check_parser = commands.choices["check"]
    check_parser.add_argument("--changed", action="append", default=[])
    check_parser.add_argument("--new-path", action="append", default=[])
    check_parser.add_argument("--source-root")
    check_parser.add_argument("--today")
    check_parser.add_argument(
        "--scope", choices=("project", "domain", "pattern"), default="project"
    )

    audit_parser = commands.choices["audit"]
    audit_parser.add_argument("--source-root")
    audit_parser.add_argument("--today")
    audit_parser.add_argument(
        "--scope", choices=("project", "domain", "pattern"), default="project"
    )


    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else default_root()
    if args.command == "initialize":
        try:
            result = initialize(root)
        except TracebookError as error:
            _write_payload(error_payload(error))
            return 2
        _write_payload(
            {"root": str(result.root), "created_paths": [str(path) for path in result.created_paths]}
        )
        return 0

    if args.command == "transactions":
        inspected_root = root.expanduser().resolve()
        _write_payload(
            {
                "root": str(inspected_root),
                "transactions": [
                    _transaction_payload(diagnostic)
                    for diagnostic in inspect_transactions(inspected_root)
                ],
            }
        )
        return 0

    if args.command == "recover-transactions":
        recovered = recover_transactions(root.expanduser())
        _write_payload({"recovered_paths": [str(path) for path in recovered]})
        return 0

    try:
        context = resolve(root, Path(args.cwd))
    except TracebookError as error:
        _write_payload(error_payload(error))
        return 2
    if args.command == "resolve":
        _write_payload(_context_payload(context))
        return 0

    if args.command == "context":
        try:
            _write_payload(retrieve_context(
                context, args.query, include_history=args.include_history,
                as_of=_parse_date(args.as_of) if args.as_of else None,
                status=args.status, kind=args.kind, scope=args.scope,
                max_results=args.max_results, max_chars=args.max_chars,
            ))
            return 0
        except ValueError as error:
            _write_payload({"error": str(error)})
            return 2

    if args.command == "audit":
        result = audit(
            context,
            _parse_date(args.today),
            Path(args.source_root) if args.source_root else None,
            args.scope,
        )
        _write_payload(
            {
                "changed_paths": [str(path) for path in result.changed_paths],
                "report": result.report.to_markdown(),
            }
        )
        return 0
    if args.command == "capture":
        try:
            request_payload = json.loads(
                Path(args.request).read_text(encoding="utf-8-sig")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            _write_payload({"error": f"INVALID_REQUEST: request file is unreadable: {error}"})
            return 2
        if not isinstance(request_payload, dict):
            _write_payload({"error": "INVALID_REQUEST: request must be a JSON object"})
            return 2
        required = {"operation", "knowledge_id"}
        missing = sorted(required - request_payload.keys())
        if missing:
            _write_payload({"error": f"INVALID_REQUEST: schema-v2 capture requires {', '.join(missing)}"})
            return 2
        operation = request_payload["operation"]
        if not isinstance(operation, str) or not operation.strip():
            _write_payload(
                {"error": "INVALID_REQUEST: schema-v2 capture requires a non-empty operation"}
            )
            return 2
        try:
            request = CaptureRequest(**request_payload)
            result = capture(context, request, _parse_date(args.today))
        except ValueError as error:
            _write_payload({"error": str(error)})
            return 2
        response = {
            "changed_paths": [str(path) for path in result.changed_paths],
            "new_paths": [str(path) for path in result.new_paths],
            "skipped": result.skipped,
            "health_scope": result.health_scope,
            "event_id": result.event_id,
        }
        user_summary = _user_summary(context, request, result)
        if user_summary is not None:
            response["user_summary"] = user_summary
        _write_payload(response)
        return 0

    result = check(
        context,
        [Path(path) for path in args.changed],
        _parse_date(args.today),
        Path(args.source_root) if args.source_root else None,
        [Path(path) for path in args.new_path],
        args.scope,
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
