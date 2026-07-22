# Automatic Creation Rules

When a project directory is missing, create only:

```text
01-projects/{readable-name--id-suffix}/index.md
01-projects/{readable-name--id-suffix}/project-status.md
```

Create architecture, business-rule, source-map, API, database, decision,
log, and synthesis documents only when there is actual content to write.

When long documents cross the split thresholds, create on-demand child
documents such as `source-map/{module}.md`, `business-rules/{domain}.md`,
`api/{module}.md`, and `database/{domain}.md`.

Never create empty shells, never create a project-level `AGENTS.md`, and mark
information that cannot be verified as `Pending`.
