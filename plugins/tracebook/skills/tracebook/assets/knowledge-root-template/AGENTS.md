# Tracebook Knowledge Root

This directory is an external project knowledge base. It is not a business
code repository.

## Purpose

Store durable project knowledge, business rules, terminology, code-path maps,
architecture understanding, incident conclusions, cross-project domain
knowledge, and reusable engineering patterns. Use Git for review and Obsidian
for browsing when desired.

## Required Read Order

For a business-project task, read in this order:

1. The current business repository's `AGENTS.md`, when present.
2. This file.
3. `00-global/health/health-status.md`.
4. The current project `01-projects/{project}/index.md`.
5. The current project `project-status.md`, when present.
6. Run the Runner `context` command with the task wording.
7. Only task-relevant authority pages returned by that command.

Do not load complete logs, raw material, archive directories, or `99-archive`
by default.

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

## Default Project Location

Project knowledge belongs in:

```text
{{knowledge_root}}/01-projects/{project-name}
```

## Task End Report

Report business-code changes, knowledge-base changes, health-check results,
new durable knowledge, and unconfirmed assumptions.
