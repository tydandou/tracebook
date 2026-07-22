---
name: tracebook
description: Use automatically for software-repository work including analysis, debugging, review, code or configuration changes, tests, builds, deployments, CI/CD, and incident diagnosis. Resolve and read minimal external project knowledge before nontrivial work; before replying, capture and check only new, verified, durable conclusions. Skip general Q&A, non-project work, raw-log summaries, unverified inference, and capture when the user explicitly disables writes.
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
- Do not run an MCP service, daemon, cloud service, vector database, or
  API-key-dependent workflow. Plugin lifecycle hooks may inject this Skill's
  read/write-gate reminders, but they must never write knowledge themselves.

## Initialize and Resolve Context

1. Set `SKILL_DIR` to the directory containing this `SKILL.md`. Resolve the
   current Git repository root and read its `AGENTS.md` when present.
2. Set the external root to `TRACEBOOK_ROOT` when configured, otherwise
   `~/.tracebook`. Run `$SKILL_DIR/scripts/tracebook_runner.py resolve --root
   <external-root> --cwd <repository-root>` with the current Python interpreter. Translate the
   command syntax for the active shell. Consume the JSON response rather than
   reimplementing root initialization or project registration.
3. New roots are initialized as schema version 2. A pre-existing root without
   the schema-v2 marker is rejected explicitly: never migrate, infer IDs for,
   or mix legacy knowledge pages with schema-v2 authority pages.
4. The runner creates or repairs only missing external-root template files,
   registers the repository from its normalized Git remote (or a local-path
   fallback), and returns the required `read_paths` plus `knowledge_language`.
5. Do not initialize a project directory beyond `index.md` and
   `project-status.md` until there is durable knowledge to write.
6. If `resolve` refuses transaction recovery, do not edit
   `.tracebook-state` manually. Run
   `$SKILL_DIR/scripts/tracebook_runner.py transactions --root <external-root>`
   first. This diagnostic command is read-only and reports whether each
   transaction is recoverable or blocked. Run `recover-transactions` only for
   an explicit safe roll-forward; it never discards, quarantines, or overwrites
   a changed target.
7. Use the returned `knowledge_language` for future human-readable knowledge
   content. `zh` means write new explanatory prose in Chinese; `en` means
   English. Do not translate or rewrite existing entries merely because the
   root preference changed. Keep paths, Markdown links, lifecycle values,
   evidence references, and structured JSON fields unchanged.

## Load Knowledge Before Engineering Work

For nontrivial software-repository work, default to this read phase even when
the user did not explicitly request Tracebook. Read the external root
`AGENTS.md`, health status, current project index, and
project status in this order. Then select only documents relevant to the task.
Do not load complete logs, raw material, archive directories, or `99-archive`
without a tracing, audit, deep-health, or explicit-user reason. After the
minimal read set, call `tracebook_runner.py context --query <task text>` and
read only the returned schema-v2 authority pages. Context failure must be
reported and may fall back to index navigation; do not pretend a structured
search succeeded.

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

Every engineering task must evaluate the write gate before the final response.
The final report must state a capture and health result when verified durable
knowledge was written. Routine work with no durable conclusion needs no skip
message; explain a skipped capture only when the user asks, capture fails, or
an important unverified/conflicting conclusion remains.

Do not write knowledge after pure log analysis, temporary Q&A, unverified
inference, or when the user prohibits a write. Treat tests and logs as evidence,
not durable knowledge by themselves. A root cause supported by logs plus source,
configuration, reproduction, or another stable source may pass the gate; never
capture complete raw logs.

Capture only when the conclusion is new or materially changed, verified,
useful after the conversation, and has a governed destination. If any condition
fails, do not capture it. An explicit no-write request disables capture, not
relevant read-only context loading.

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

The request must declare `operation` and a stable lowercase-hyphenated
`knowledge_id`. Use `create`
only for a missing entity. Use `revise` or `change-status` with
`expected_version` for an existing entity; title, body, evidence, and lifecycle
changes retain the original ID. `event_id` remains content-event idempotence,
not entity identity. The runner renders one Markdown authority page per entity
with a Current section and versioned History.
Never submit raw transcripts, complete logs, temporary answers, or an
unverified inference as a capture. Use `status: current` with an `evidence`
list for confirmed knowledge. Use `status: pending` only for a durable,
explicitly unresolved item; it may have an empty `evidence` list. Use
`status: deprecated` for information that no longer applies. Use
`status: superseded` only with a `replacement_knowledge_id` for an existing
active successor knowledge entity.

The same entity event is idempotent. A changed body, evidence, title, or
lifecycle state requires an explicit revise/status operation and preserves the
prior version in History. Do not use a repeated title as an implicit overwrite.

Use a lowercase-hyphenated `kind` to select the governed destination; project
kinds include `architecture`, `api`, `business-rule`, `database`, `module`,
`source-map`, `terminology`, `decision`, `incident`, and `change`. `domain`
and `pattern` scopes also use a stable kind. `category`, when present, is only
a classification and never a path.
Entity paths are derived from scope, kind, and `knowledge_id`; do not create
aggregate pages or use a topic split to route schema-v2 knowledge. Apply
frontmatter and lifecycle labels when required.
## Verify Knowledge Writes

After every successful capture, require `changed_paths`, `new_paths`, and
`health_scope` in its structured JSON. Stop and report an incomplete runner
response if `health_scope` is absent or is not `project`, `domain`, or
`pattern`; do not fall back to the default project scope.

When a non-skipped capture with changed paths returns `user_summary`, display
it to the user verbatim in the next user-facing message. Do not defer it to
the Final Task Report, paraphrase it, or omit it: this confirms a file write
that has already occurred on the user's system.

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
