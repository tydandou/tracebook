# Log and Status Rules

Do not use full logs as default task context. Maintain short status summaries
and write detailed history to monthly logs.

- Global summary: `00-global/health/health-status.md`.
- Global health history: `00-global/health/logs/YYYY-MM.md`.
- Project summary: `project-status.md`.
- Project history: `logs/YYYY-MM.md`.

Capture keeps its newest 80 events in a `tracebook:recent-events` marked block
and writes every event to the monthly project log in the same transaction.
Text outside the block, including legacy dated entries and manual notes, stays
unchanged; old pages are not automatically migrated or made smaller. The limit
applies to the generated event count, not the whole file's lines or characters.
Malformed/duplicate markers or unrecognized block content reject capture before
commit rather than discarding text. Keep manual summaries outside the block.

Record only actually completed Light, Regular, or Deep checks in health status.
Keep status files near 100 lines and roll important history into them.
