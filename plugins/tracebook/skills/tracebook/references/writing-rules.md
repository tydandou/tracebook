# Writing Rules

Write verified, durable conclusions as schema-v2 authority pages. Do not write
raw conversations, logs, guesses, or ordinary code changes. A knowledge entity
has a stable lowercase-hyphenated `knowledge_id`; the ID does not change when
the title, evidence, body, or lifecycle state changes.

Before writing, use `context` to find an existing entity. Use `create` only
for a new conclusion. Use `revise` or `change-status` with its returned
version for a changed conclusion. Never create a second ID merely to avoid a
version conflict.

Choose scope deliberately:

- `project` for conclusions tied to one repository;
- `domain` for reusable business knowledge; and
- `pattern` for reusable technical practice.

Every Current conclusion needs concrete evidence. Preserve event markers and
the generated `Current`/`History` structure; the runner is the authority for
rendering an entity page. Generated links must use standard Markdown links,
not new Wikilinks.
