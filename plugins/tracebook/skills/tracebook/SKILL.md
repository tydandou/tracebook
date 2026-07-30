---
name: tracebook
description: MUST invoke before any software-development work in the session. This includes analysis, scaffolding a new project, debugging, review, code changes, tests, builds, deploys, CI/CD, and incidents. It applies to work outside the current repository too. Loads external project knowledge context first. After task completion, evaluates the write gate for durable knowledge capture. Skip only for general Q&A or non-project conversations.
---

# Tracebook

Use Tracebook as the external, durable knowledge layer for a coding task. Keep
business code and long-lived project analysis separate.

## Quick Start

Copy these commands. `SKILL_DIR` holds this `SKILL.md`; `ROOT` is
`TRACEBOOK_ROOT` when set, else `~/.tracebook`; `CWD` is the target project root
(its Git root when available), not necessarily your shell's cwd.

```bash
# 1. Before any work: read-only check. If it returns blocked:true, run the
#    command in required_action.argv, then continue with step 2.
python "$SKILL_DIR/scripts/tracebook_runner.py" preflight --root "$ROOT" --cwd "$CWD"

# 2. Load task context (lock-free read). Add --evidence-path <file> to find
#    knowledge backed by a specific source file.
python "$SKILL_DIR/scripts/tracebook_runner.py" context-read-path \
  --root "$ROOT" --cwd "$CWD" --query "<task text>"

# 3. After the task, once per knowledge item that passes the write gate.
#    Pipe the request through stdin; never write a temporary request file.
python "$SKILL_DIR/scripts/tracebook_runner.py" capture \
  --root "$ROOT" --cwd "$CWD" --request - --today "$(date +%F)" <<'JSON'
{
  "operation": "create",
  "knowledge_id": "refund-retry-policy",
  "scope": "project",
  "kind": "decision",
  "title": "Refund retry policy",
  "body": "Refunds retry at most twice, 3s timeout each.",
  "evidence": ["src/order/RefundController.java:L87"]
}
JSON
```

Then verify the write with `check` (see Verify Knowledge Writes). The block above
settles only which command to run; the sections below govern when each step
applies and what may be captured.

## Hard Boundaries

- Use `TRACEBOOK_ROOT` when set; otherwise use `~/.tracebook` as the default external knowledge root.
- Do not modify business repositories to install or operate Tracebook.
- Do not discover, import, copy, or modify an existing external knowledge root automatically.
- Do not create a project-level `AGENTS.md` in a knowledge directory.
- Do not store raw chat transcripts, complete logs, or unverified AI assertions
  as durable knowledge.
- Do not run an MCP service, daemon, cloud service, vector database, or
  API-key-dependent workflow.

## Initialize and Resolve Context

1. Set `SKILL_DIR` to the directory containing this `SKILL.md`. Identify the
   intended target path, not merely the agent's current working directory.
   For an existing project, resolve its Git root when available and read its
   `AGENTS.md` when present. For a new or uncertain target, first run
   `$SKILL_DIR/scripts/tracebook_runner.py preflight --root <external-root>
   --cwd <intended-target>` before creating files. `preflight` is read-only:
   it must not initialize a root or register a project.
2. Set the external root to `TRACEBOOK_ROOT` when configured, otherwise
   `~/.tracebook`. Run `$SKILL_DIR/scripts/tracebook_runner.py preflight --root
   <external-root> --cwd <project-root>` first. For an already registered
   project, load task context with `context-read-path --root <external-root>
   --cwd <project-root> --query <task text>`. This is the normal lock-free read
   path: it does not initialize, register, repair health, recover transactions,
   or create lock files.
   If `preflight` returns `blocked: true`, execute the command in
   `required_action.argv`, then run `context-read-path` before beginning
   software-development work.
3. Run `$SKILL_DIR/scripts/tracebook_runner.py resolve --root <external-root>
   --cwd <project-root>` only to activate an unregistered project, repair a
   root, seed a legacy project's first snapshot, or before a write/health
   operation that requires maintenance permission. `resolve` may acquire locks
   and modify the external knowledge root; do not present it as a read command.
4. New roots are initialized as schema version 2. A pre-existing root without
   the schema-v2 marker is rejected explicitly: never migrate, infer IDs for,
   or mix legacy knowledge pages with schema-v2 authority pages.
5. The runner creates or repairs only missing external-root template files,
   resolves the project from its registered location and optional normalized
   Git remote, and returns the required `read_paths` plus `knowledge_language`.
6. Do not initialize a project directory beyond `index.md` and
   `project-status.md` until there is durable knowledge to write.
7. If `resolve` refuses transaction recovery, do not edit
   `.tracebook-state` manually. Run
   `$SKILL_DIR/scripts/tracebook_runner.py transactions --root <external-root>`
   first. This diagnostic command is read-only and reports whether each
   transaction is recoverable or blocked. Run `recover-transactions` only for
   an explicit safe roll-forward; it never discards, quarantines, or overwrites
   a changed target.
8. Use the returned `knowledge_language` for future human-readable knowledge
   content. `zh` means write new explanatory prose in Chinese; `en` means
   English. Do not translate or rewrite existing entries merely because the
   root preference changed. Keep paths, Markdown links, lifecycle values,
   evidence references, and structured JSON fields unchanged.

Do not decide that knowledge is irrelevant before the preflight/read phase.
An empty structured result is valid; skipping Tracebook because the target is
new, outside the current repository, or of uncertain relevance is not valid.

## Load Knowledge Before Engineering Work

For nontrivial software-repository work, default to this read phase even when
the user did not explicitly request Tracebook. Read the external root
`AGENTS.md`, health status, current project index, and
project status in this order. Then select only documents relevant to the task.
Do not load the knowledge root's own complete logs, raw material, archive
directories, or `99-archive` without a tracing, audit, deep-health, or
explicit-user reason. This bounds what is read out of the knowledge base; a log
the user supplies for analysis is task input and is unaffected. After the
minimal read set, call `tracebook_runner.py context-read-path --cwd
<project-root> --query <task text>` and read only the returned schema-v2
authority pages. It returns the last committed project snapshot without
blocking on a same-project writer. A `PROJECT_ACTIVATION_REQUIRED` response
means the target has not been registered and must be activated with `resolve`
before project context can be read. Context failure must be reported and may
fall back to index navigation; do not pretend a structured search succeeded.
Retrieval matches literal tokens (CJK bigrams, whole English words) with no
stemming or synonyms, so prefer words that actually appear in the knowledge —
if a query returns nothing, retry with terms from the project index or an exact
`knowledge_id` rather than a paraphrase.

To find knowledge from a source file — a path in a stack trace or a log the user
supplied — pass `--evidence-path <repo-relative-or-project-absolute path>`,
repeating it per file, with or without `--query`. Entities listing that file as
formal `## Current` evidence are marked `evidence_match: true` and ranked first;
a prose mention or a History reference never earns that mark. It requires exactly
one project at the current snapshot, so `--scope domain/pattern/all` and `--as-of`
are rejected, and at least one of `--query` or `--evidence-path` must be non-empty.

The opening read is not the only retrieval. Query again whenever you judge it
useful, most often once a new file path, identifier, or `knowledge_id` is in
hand, and treat a retrieved conclusion that contradicts a log or the current
source as a finding rather than as truth. Follow
[retrieval timing rules](references/retrieval-timing-rules.md).

## Read Related Projects Deliberately

The active project is the default and only automatic project scope. Do not scan
all registered projects. When the user explicitly names another project, first
run `project-search --root <external-root> --query <name-or-id>`, then pass the
selected stable IDs through repeated `context --project-id <project-id>`
arguments. When the request is about a registered microservice system, use
`context --system-id <system-id>`; it selects only that system's recorded
members. Context results identify their source project.

Use `--profile reference` only when the user asks to reuse an existing
project's architecture for a new project. Before that target is activated, use
`context-read --root <external-root> --project-id <source-project-id>
--profile reference --query <task text>`; it has no `--cwd` and must not
initialize or register the target. It returns architecture, module, and
decision knowledge from explicitly selected source projects and excludes
file-level source maps, incidents, and routine change history. Never infer a
reference source from the current workspace alone.

If a user says only "related services" and no system is registered, search for
candidate projects and ask for a source project or system before expanding the
read scope. Follow [cross-project reading rules](references/cross-project-reading-rules.md).

`preflight` reports a registered project's `systems` membership, including the
other member projects and their recorded relations. When the task spans members
of that system, read with `context --system-id <system-id>` rather than the
default project scope: a system relation makes the cross-project read possible,
it does not widen the default scope automatically.

## Register a System Relation When the Link Is Structural

Create the relation yourself, without waiting for the user to ask for it, when
all three hold:

1. both projects are already registered (`preflight` or `project-search`
   confirms this — never register a project just to relate it);
2. the link is a stable delivery dependency, not a passing reference. A task
   that captured durable knowledge into both projects is the strongest signal;
   a `check` report may also raise `system_relation_candidate` when one
   project's evidence points into the other's repository;
3. the direction and the relation kind are unambiguous from the task, because
   the runner does not validate `--kind` — you are asserting the semantics.

If any of the three fails, do nothing: do not create a system, do not ask, and
do not guess a relation. Incidental mentions, one-off debugging, and a
documentation example that merely names another repository are not relations.

```bash
SYS=$(python "$SKILL_DIR/scripts/tracebook_runner.py" system-create \
  --root "$ROOT" --name "<system name>" \
  | python -c "import sys,json;print(json.load(sys.stdin)['system']['system_id'])")

for P in "<project-id-a>" "<project-id-b>"; do
  python "$SKILL_DIR/scripts/tracebook_runner.py" system-bind-project \
    --root "$ROOT" --system-id "$SYS" --project-id "$P"
done

# One call per direction; state both when each side constrains the other.
python "$SKILL_DIR/scripts/tracebook_runner.py" system-relate --root "$ROOT" \
  --system-id "$SYS" --source-project-id "<project-id-a>" \
  --target-project-id "<project-id-b>" --kind designs
python "$SKILL_DIR/scripts/tracebook_runner.py" system-relate --root "$ROOT" \
  --system-id "$SYS" --source-project-id "<project-id-b>" \
  --target-project-id "<project-id-a>" --kind implements
```

Report the system name and both relations in the final task report: this is a
durable structural change to the knowledge base.

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
- [cross-project reading rules](references/cross-project-reading-rules.md)
- [retrieval timing rules](references/retrieval-timing-rules.md)

## Evaluate the Write Gate After the Task

Every engineering task must evaluate the write gate before the final response.
The final report must state a capture and health result when verified durable
knowledge was written. Routine work with no durable conclusion needs no skip
message; explain a skipped capture only when the user asks, capture fails, or
an important unverified/conflicting conclusion remains.

Treat tests and logs as evidence, not durable knowledge by themselves. A root
cause backed by logs **plus** source, configuration, or reproduction does pass
the gate: a defect investigation that read the code to locate the fault normally
qualifies, and that conclusion is worth keeping. What fails is a conclusion
resting on logs alone, temporary Q&A, unverified inference, or when the user
prohibits a write. Never capture raw logs as the knowledge itself.

Evaluate the write gate per atomic knowledge item, never per whole task. A task
that produces several independent facts commits each that is new or
materially changed, useful after the conversation, and has a governed
destination — one `capture` call each. Never let one unverified item block the capture of an
already-verified item. Skip an item only when it cannot be split further and its
core conclusion has no evidence. An explicit no-write request disables capture,
not relevant read-only context loading.

An implemented-but-not-yet-accepted change is durable knowledge: capture the
fact that the code or configuration was changed with `status: current`, and
state its verification status and uncovered scope explicitly. Do not write it as
"risk fully closed". Capture a long-lived, clearly unresolved risk as its own
entity with `status: pending`. Do not withhold the confirmed facts because a
dependency — often third-party — cannot yet be confirmed; record that dependency
as a separate `pending` item instead.

Write only verified, durable knowledge: business rules, terminology, scenarios,
module relationships, architecture changes, code paths, API or database
changes, bug root causes, verification conclusions, important risks, and
reusable cross-project patterns.

Classify the destination before writing. Use project documents for
project-specific facts, `02-domain` for reusable business knowledge, and
`03-patterns` for reusable engineering knowledge. Update indexes and status
summaries. Add source references for critical facts; mark incomplete evidence
as `Pending`. Pipe an explicit JSON capture request through stdin as shown in
Quick Start, and consume the response's `changed_paths` and `new_paths`. Never
write a temporary request file. (`--request <path>` stays supported for a
pre-existing file outside both governed trees; a path resolving inside the
knowledge root or the business repository is rejected with `INVALID_REQUEST`.)

Each entity body should make explicit: the conclusion as a concrete fact with no
inference mixed in; the evidence located in source, config, logs, tests, or a
Git diff; the verification status (static / runtime / end-to-end / pending); the
scope of services and entry points the conclusion applies to; and only the open
items directly tied to that entity. Prefer "code changed, SIT acceptance
pending, gateway network isolation unverified" over "security fix fully closed".

The request must declare `operation` and a stable lowercase-hyphenated
`knowledge_id`. Use `create`
only for a missing entity. Use `revise` or `change-status` with
`expected_version` for an existing entity; title, body, evidence, and lifecycle
changes retain the original ID. `event_id` remains content-event idempotence,
not entity identity. The runner renders one Markdown authority page per entity
with a Current section and versioned History. `event_id` is output only: the
runner generates it and echoes it in the capture response and as a
`<!-- tracebook:event:... -->` page marker. Never copy it back into a capture
request — an `event_id` field is rejected as unknown.
Never submit raw transcripts, complete logs, temporary answers, or an
unverified inference as a capture. Use `status: current` with an `evidence`
list for confirmed knowledge. Use `status: pending` for a durable item that is
confirmed to exist but not yet verified or resolved — a known open risk or
awaited acceptance, not an evidence-poor guess; it may have an empty `evidence`
list. Use
`status: deprecated` for information that no longer applies. Use
`status: superseded` only with a `replacement_knowledge_id` for an existing
active successor knowledge entity.

The same entity event is idempotent. A changed body, evidence, title, or
lifecycle state requires an explicit revise/status operation and preserves the
prior version in History. Do not use a repeated title as an implicit overwrite.

Use a lowercase-hyphenated `kind` to select the governed destination; project
kinds include `architecture`, `api`, `business-rule`, `database`, `module`,
`source-map`, `terminology`, `decision`, `incident`, and `change`. `domain`
and `pattern` scopes also use a stable kind. Retired request fields such as
`category`, `topic`, and `replacement` are rejected; use `kind` and
`replacement_knowledge_id` as the schema-v2 contract defines.
Project entity paths are derived from scope, kind, and `knowledge_id`; domain
and pattern paths use scope plus `knowledge_id`, while `kind` remains governed
metadata. Do not create aggregate pages or use a topic split to route schema-v2 knowledge. Apply
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

Then run `check`, repeating `--changed` for every capture `changed_paths` item
and `--new-path` for every `new_paths` item, and consume its structured JSON:

```bash
python "$SKILL_DIR/scripts/tracebook_runner.py" check --root "$ROOT" --cwd "$CWD" \
  --source-root "$CWD" --today "$(date +%F)" --scope "<health_scope>" \
  --changed "<changed_paths item>" --new-path "<new_paths item>"
```

With `--source-root`, the report's `Review Candidates` section flags Current
knowledge whose evidence files are missing (`source_missing`, strong), changed
after the knowledge was last updated (`source_mtime_newer`, advisory), or
resolve outside the source root (`source_outside_root`, strong). Add
`--review-after-days N` (N > 0) to also flag knowledge not updated in N days
(`review_age_exceeded`, advisory). These are review prompts, not proof a fact is
wrong — verify against evidence before changing any status.

When `check_type: Deep` is returned, do not treat it as a completed Deep check.
Run `$SKILL_DIR/scripts/tracebook_runner.py audit` with the same `--root`,
`--cwd`, `--today`, and `--source-root` values, plus the same scope supplied to
check as `--scope`. Its fact, source, root-cause, and status candidates require
human review before they become durable conclusions. Do not let either command
modify business code.

## Final Task Report

State business-code changes, external-knowledge changes, health-check result,
new durable knowledge, and unconfirmed assumptions.
