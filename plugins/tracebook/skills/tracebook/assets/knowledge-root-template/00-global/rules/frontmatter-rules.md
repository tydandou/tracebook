# Frontmatter Rules

Use frontmatter for cross-project domain knowledge, patterns, ADRs, synthesis
pages, and other high-value durable conclusions. Do not require it for rules,
entry indexes, status files, logs, or raw material.

```yaml
---
type: knowledge
status: current
scope: global
owner_project: project-name
source: code-review
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: []
---
```

Valid `type` values are `knowledge`, `decision`, `pattern`, `synthesis`, and
`reference`. Valid `status` values are `current`, `draft`, `deprecated`,
`superseded`, and `unconfirmed`. At minimum, new frontmatter includes `type`,
`status`, and `created`. Update `updated` when content changes.
