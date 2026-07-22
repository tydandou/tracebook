# Reading Rules

## Core Principle

Every potentially long-lived document uses an entry-index plus child-document
structure. Read indexes, source maps, and status summaries before loading
full documents.

## Default Load Order

1. Business repository `AGENTS.md`, when present.
2. External knowledge-root `AGENTS.md`.
3. `00-global/health/health-status.md`.
4. Current project `index.md`.
5. Current project `project-status.md`.
6. Run Runner `context` with the task wording.
7. Read task-relevant authority pages returned by context.

## Default Do Not Read

Do not read `logs/`, `archive/`, `raw/`, `99-archive/`, or
`00-global/health/logs/` unless tracing, auditing, deep health review, or a
user request requires them.

## Task-Specific Context

- Frontend tasks: source map, modules, APIs, and business rules.
- Backend tasks: source map, architecture, modules, database, and business
  rules.
- Database tasks: database knowledge, business rules, and source maps.
- API tasks: API knowledge, source maps, and business rules.
- Bug fixes: project status, source maps, relevant business documents, and
  only necessary monthly logs.

## Short Entry Documents

Keep `AGENTS.md`, root indexes, project indexes, project status, and health
status under 100 lines when possible. Keep `source-map.md` under 150 lines.

Do not scan or load every entity by default. Context is Current-only unless a
user asks for historical reasoning; use `--include-history` or `--as-of` then.
