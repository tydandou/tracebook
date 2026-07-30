# Tracebook Knowledge Root

This directory is an external project knowledge base. It is not a business
code repository.

## Purpose

Store durable project knowledge, business rules, terminology, code-path maps,
architecture understanding, incident conclusions, cross-project domain
knowledge, and reusable engineering patterns.

## Required Read Order

For a business-project task, read in this order:

1. The current business repository's `AGENTS.md`, when present.
2. This file.
3. This root's `index.md` — the entry point to its six sections.
4. `00-global/health/health-status.md`.
5. The current project path returned by the resolver, then its `index.md`.
6. The current project `project-status.md`.
7. Run the Runner's `context-read-path` with the task wording — step 2 of the
   Skill's Quick Start. If `preflight` returned `blocked: true`, execute its
   `required_action.argv` first, then return to this step.
8. Only task-relevant authority pages returned by that command.

The opening read is not the only retrieval. When the work yields a new file path,
identifier, or `knowledge_id`, query again; judging it useful is reason enough.

Do not load complete logs, raw material, archive directories, or `99-archive`
by default. That bounds this knowledge base's own content; a log the user
supplies for analysis is task input and is unaffected.

## Core Rules

- Read source and context before writing knowledge.
- Keep business code and long-lived knowledge in separate repositories.
- Create missing project knowledge directories and their minimum documents
  automatically; never create a project-level `AGENTS.md`.
- Write only durable, evidence-backed conclusions. Mark uncertainty as
  `Pending`.
- Create schema-v2 authority pages with stable `knowledge_id`; revise an
  existing ID rather than creating a duplicate for an updated conclusion.
- Default retrieval is Current-only. Request history only for an explicit
  historical question or an `as-of` reconstruction.
- Do not store raw chat transcripts or unverified AI inferences as facts.
- Maintain entry indexes and run local checks after knowledge writes.

## Rule Files

- `00-global/agent-workflow.md`
- `00-global/rules/reading-rules.md`
- `00-global/rules/directory-rules.md`
- `00-global/rules/auto-creation-rules.md`
- `00-global/rules/writing-rules.md`
- `00-global/rules/frontmatter-rules.md`
- `00-global/rules/source-attribution-rules.md`
- `00-global/rules/index-maintenance-rules.md`
- `00-global/rules/log-status-rules.md`
- `00-global/rules/knowledge-lifecycle-rules.md`
- `00-global/rules/synthesis-rules.md`
- `00-global/health/health-check-rules.md`

## Where Knowledge Belongs

Classify by reuse scope before writing:

- `01-projects/{readable-name--id-suffix}` — project-specific facts. The
  directory name is the project's name slug plus a stable ID suffix; its full
  identity lives in that directory's `project.json`.
- `02-domain` — business knowledge reusable across projects (terminology,
  rules, processes, scenarios).
- `03-patterns` — engineering knowledge reusable across projects (practices,
  design patterns, verification conclusions).
- `04-systems` — multi-project membership and directed service relations.
  **Never create by hand**: `system-create`, `system-bind-project`, and
  `system-relate` maintain it.
- `99-archive` — deprecated and superseded knowledge, kept for traceability.

This root's absolute path: `{{knowledge_root}}`.

## Task End Report

Report business-code changes, knowledge-base changes, health-check results,
new durable knowledge, and unconfirmed assumptions.
