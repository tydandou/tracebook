# Index Maintenance Rules

Update the current project `index.md` whenever a project knowledge document is
created. Update `project-status.md` when project state changes. Update source
maps when adding code-path knowledge. Update the appropriate `02-domain` or
`03-patterns` entry when adding cross-project knowledge.

Health checks must flag a document as an orphan when it is not referenced by an
entry index, source map, project status, or relevant parent document.
