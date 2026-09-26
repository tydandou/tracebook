# Log and Status Rules

Logs are never default context. Every growing log needs a short status summary.

- Global health summary: `00-global/health/health-status.md`.
- Global health history: `00-global/health/logs/YYYY-MM.md`.
- Project current state: `project-status.md`.
- Project history: `logs/YYYY-MM.md`.

Use `## Dev`, `## Bug`, and `## Knowledge` headings only when that content
exists. Record only actually performed Light, Regular, or Deep checks in
`health-status.md`. Roll important recent log content into status summaries
and keep summaries near 100 lines.

Capture keeps the newest 80 events in a `tracebook:recent-events` marked block;
every event also goes to the monthly log in the same transaction. Outside text,
including legacy events and manual summaries, is preserved without migration.
The limit bounds generated events, not total page size. Keep manual notes outside
the block; ambiguous markers or unknown block content reject capture before commit.
