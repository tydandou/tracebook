# Reading Rules

## Core Principle

Use an entry-index plus child-document structure for every potentially growing
knowledge area. Read indexes, source maps, status summaries, and targeted
search results before loading full documents.

## Required Read Order

1. Current business repository `AGENTS.md`, when present.
2. External knowledge-root `AGENTS.md`.
3. `00-global/health/health-status.md`.
4. Current project `index.md`.
5. Current project `project-status.md`, when present.
6. Only task-relevant entry and child documents.

## Default Exclusions

Do not read `logs/`, `archive/`, `raw/`, `99-archive/`, or
`00-global/health/logs/` by default. Read them only for tracing, audit, deep
health review, or an explicit user request.

## Task-Based Selection

- Frontend: source maps, modules, APIs, and business rules.
- Backend: source maps, architecture, modules, database, and business rules.
- Database: database knowledge, business rules, and source maps.
- API: API knowledge, source maps, and business rules.
- Bug fixing: project status, source maps, relevant business documents, and
  necessary monthly logs.

## Size Limits

Keep `AGENTS.md`, root and project indexes, project status, and health status
near 100 lines. Keep source maps near 150 lines. Split source maps, business
rules, APIs, and database documents after 300 lines. Roll growing history into
monthly logs and preserve short status summaries.
