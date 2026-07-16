# Frontmatter Rules

Add frontmatter to new cross-project knowledge, patterns, ADRs, synthesis
pages, and other important durable conclusions. Do not require it for rules,
indexes, status files, logs, or raw material.

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

Use `knowledge`, `decision`, `pattern`, `synthesis`, or `reference` for type.
Use `current`, `draft`, `deprecated`, `superseded`, or `unconfirmed` for
status. At minimum include type, status, and creation date.
