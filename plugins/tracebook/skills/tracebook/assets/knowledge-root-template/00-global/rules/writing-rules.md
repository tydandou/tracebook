# Writing Rules

1. Structure knowledge; do not paste chat transcripts.
2. Extend an existing relevant document before creating a duplicate.
3. Mark uncertain information as `Pending`.
4. State the evidence for conclusions inferred from code.
5. Put stable project knowledge in project documents.
6. Put current state in `project-status.md`.
7. Put detailed process history in `logs/YYYY-MM.md`.
8. Put important engineering decisions in `decisions/ADR-xxxx.md`.
9. Put cross-project business knowledge in `02-domain`.
10. Put cross-project technical patterns in `03-patterns`.
11. Move deprecated material to a project `archive/` or `99-archive/`.
12. Do not write business code in this knowledge root.
13. Create synthesis pages only for stable, high-value conclusions with
    sources, update time, and invalidation conditions.
14. Label deprecated, superseded, pending, and historical information.
15. Add frontmatter to new important knowledge documents when required.

Place current project status in `project-status.md`; business rules in
`business-rules.md`; terminology in `terminology.md`; module boundaries in
`modules.md`; architecture changes in `architecture.md`; APIs in `api.md`;
database knowledge in `database.md`; code paths in `source-map.md`; and
complex recurring conclusions in `synthesis/{topic}.md`.

## Link Format

Use standard Markdown `[label](path)` links for generated or agent-written
knowledge. Wikilinks are accepted only as compatibility input for imported
material or manual Obsidian edits; do not generate new Wikilinks.