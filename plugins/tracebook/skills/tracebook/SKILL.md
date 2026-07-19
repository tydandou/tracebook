---
name: tracebook
description: Preserve and use durable external project knowledge for Codex. Use when working on a software project and the task needs business terminology, architecture context, module or code-path knowledge, debugging history, verified engineering conclusions, or a governed write-back after development, debugging, troubleshooting, or code analysis.
---

# Tracebook

Use Tracebook as the external, durable knowledge layer for a coding task. Keep
business code and long-lived project analysis separate.

## Hard Boundaries

- Use `TRACEBOOK_ROOT` when set; otherwise use `~/.tracebook` as the default external knowledge root.
- Do not modify business repositories to install or operate Tracebook.
- Do not discover, import, copy, or modify an existing external knowledge root automatically.
- Do not create a project-level `AGENTS.md` in a knowledge directory.
- Do not store raw chat transcripts, complete logs, or unverified AI assertions
  as durable knowledge.
- Do not run an MCP service, daemon, hook, cloud service, vector database, or
  API-key-dependent workflow.

## Initialize and Resolve Context

1. Set `SKILL_DIR` to the directory containing this `SKILL.md`. Resolve the
   current Git repository root and read its `AGENTS.md` when present.
2. Set the external root to `TRACEBOOK_ROOT` when configured, otherwise
   `~/.tracebook`. Run `$SKILL_DIR/scripts/tracebook_runner.py resolve --root
   <external-root> --cwd <repository-root>` with the current Python interpreter. Translate the
   command syntax for the active shell. Consume the JSON response rather than
   reimplementing root initialization or project registration.
3. The runner creates or repairs only missing external-root template files,
   registers the repository from its normalized Git remote (or a local-path
   fallback), and returns the required `read_paths`.
4. Do not initialize a project directory beyond `index.md` and
   `project-status.md` until there is durable knowledge to write.

## Load Knowledge Before Engineering Work

Read the external root `AGENTS.md`, health status, current project index, and
project status in this order. Then select only documents relevant to the task.
Do not load complete logs, raw material, archive directories, or `99-archive`
without a tracing, audit, deep-health, or explicit-user reason.

Follow [reading rules](references/reading-rules.md) for selection and length
limits. Load these references only when their rule applies:

- [directory rules](references/directory-rules.md)
- [automatic creation rules](references/auto-creation-rules.md)
- [writing rules](references/writing-rules.md)
- [frontmatter rules](references/frontmatter-rules.md)
- [source attribution rules](references/source-attribution-rules.md)
- [index maintenance rules](references/index-maintenance-rules.md)
- [log and status rules](references/log-status-rules.md)
- [knowledge lifecycle rules](references/knowledge-lifecycle-rules.md)
- [synthesis rules](references/synthesis-rules.md)
- [health check rules](references/health-check-rules.md)

## Evaluate the Write Gate After the Task

Do not write knowledge after pure log analysis, temporary Q&A, unverified
inference, or when the user prohibits a write.

Write only verified, durable knowledge: business rules, terminology, scenarios,
module relationships, architecture changes, code paths, API or database
changes, bug root causes, verification conclusions, important risks, and
reusable cross-project patterns.

Classify the destination before writing. Use project documents for
project-specific facts, `02-domain` for reusable business knowledge, and
`03-patterns` for reusable engineering knowledge. Update indexes and status
summaries. Add source references for critical facts; mark incomplete evidence
as `Pending`. Create an explicit JSON capture request and run
`$SKILL_DIR/scripts/tracebook_runner.py capture` with `--root`, `--cwd`, and
`--request`; consume its `changed_paths` and `new_paths`.

The request must declare `write_intent: durable` and `content_kind: knowledge`.
Never submit raw transcripts, complete logs, temporary answers, or an
unverified inference as a capture. Use `status: Current` with an `evidence`
list for confirmed knowledge. Use `status: Pending` only for a durable,
explicitly unresolved item; it may have an empty `evidence` list. Use
`status: Deprecated` or `status: Historical` only when preserving traceability;
the runner routes these entries to an archive. Use `status: Superseded` only
with a `replacement` path to the successor knowledge.

Use `kind` to select the governed destination: project kinds are
`architecture`, `api`, `business-rule`, `database`, `module`, `source-map`,
and `terminology`; project `decision` and `synthesis` use a slug `category`;
`domain` and `pattern` scope use `kind: domain` and `kind: pattern`.
`category` must be a lowercase hyphenated topic, never a path. When
`business-rule`, `api`, `database`, or `source-map` exceeds 300 lines, include
a lowercase hyphenated `topic`; the runner writes the next entry to its child
document. Apply frontmatter and lifecycle labels when required.
## Verify Knowledge Writes

After every successful capture, require `changed_paths`, `new_paths`, and
`health_scope` in its structured JSON. Stop and report an incomplete runner
response if `health_scope` is absent or is not `project`, `domain`, or
`pattern`; do not fall back to the default project scope.

Run `$SKILL_DIR/scripts/tracebook_runner.py check` with the external root as
`--root` and repository root as `--cwd`. Pass every capture `changed_paths`
item as `--changed`, every `new_paths` item as `--new-path`, and the capture
`health_scope` as `--scope`. Pass the current date as `--today` and the
business repository root as `--source-root` for source-map validation. Consume
and report the structured JSON result.

When `check_type: Deep` is returned, do not treat it as a completed Deep check.
Run `$SKILL_DIR/scripts/tracebook_runner.py audit` with the same `--root`,
`--cwd`, `--today`, and `--source-root` values, plus the same scope supplied to
check as `--scope`. Its fact, source, root-cause, and status candidates require
human review before they become durable conclusions. Do not let either command
modify business code.

## Final Task Report

State business-code changes, external-knowledge changes, health-check result,
new durable knowledge, and unconfirmed assumptions.
