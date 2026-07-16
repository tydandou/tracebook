# Writing Rules

Write structured durable knowledge, not raw conversation. Prefer extending an
existing relevant document over creating a duplicate. Put project state in
`project-status.md`, monthly detail in `logs/YYYY-MM.md`, important decisions
in `decisions/ADR-xxxx.md`, project-specific facts in `01-projects`, reusable
business knowledge in `02-domain`, and reusable technical knowledge in
`03-patterns`.

Write only business rules, terminology, scenarios, module relations,
architecture changes, code paths, API or database changes, verified bug root
causes, verification conclusions, important risks, and reusable patterns.
Never write business code in the knowledge root. Move obsolete information to
an archive and label uncertain information `Pending`.

## Link Format

Use standard Markdown `[label](path)` links for all generated or agent-written
knowledge links. Wikilinks may remain in imported material or manual Obsidian
edits as compatibility input; do not generate new Wikilinks in runner-managed
content.