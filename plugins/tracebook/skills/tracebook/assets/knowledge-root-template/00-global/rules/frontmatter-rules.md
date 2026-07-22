# Frontmatter Rules

Every Runner-managed durable conclusion is a schema-v2 authority page. Do not
add schema-v2 frontmatter to rules, indexes, status files, logs, or raw material.

```yaml
---
schema_version: 2
type: business-rule
status: current
scope: project
project: github.com/acme/project
knowledge_id: stable-conclusion-id
version: 1
created: YYYY-MM-DD
updated: YYYY-MM-DD
replacement_knowledge_id: null
---
```

`knowledge_id` is immutable lowercase-hyphenated text. Valid statuses are
`current`, `pending`, `deprecated`, and `superseded`. The Runner increments
`version` and maintains the History section; do not hand-edit those fields.
