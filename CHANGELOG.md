# Changelog

This project follows semantic versioning. Releases are created only after the
matching Git tag is published.

## [1.1.1] - 2026-07-20

### Fixed

- Clarified the Codex recovery path when a plugin has been removed but its
  `tracebook` marketplace source is absent from the active Codex profile.
- Documented separate tagged-release and local-clone recovery commands so a
  missing marketplace source is restored before `tracebook@tracebook` is
  installed.

## [1.1.0] - 2026-07-20

### Added

- Manual per-root language selection through optional
  `.tracebook-state/config.json`: English remains the default and `zh` selects
  Chinese templates for future created or repaired knowledge documents.
- A complete Chinese knowledge-root template set, Chinese project bootstrap
  pages, and `knowledge_language` in the resolve payload for Agent workflows.
- Read-only pending-transaction diagnostics and an explicit safe recovery
  command, without automatic discard, quarantine, or overwrite of changed
  knowledge.

### Changed

- Regular health checks now recognize `Pending` only as a structured status,
  avoiding prose-substring false positives.
- The Skill now requires a final write-gate outcome and documents
  content-event idempotence instead of title-based overwrites.

### Compatibility

- Existing knowledge is never translated, rewritten, moved, or deleted by a
  language preference change. Paths, Markdown links, lifecycle values, event
  identifiers, evidence references, and health machine fields remain stable.

## [1.0.0] - 2026-07-19

### Added

- A Codex Skill for durable, traceable engineering knowledge stored outside the
  business repository.
- Markdown knowledge templates for project, domain, pattern, raw-material, and
  archive areas, with indexes, lifecycle metadata, source attribution, status
  summaries, logs, and health rules.
- A local runner that resolves Git project identity, initializes missing
  knowledge structure, captures governed durable knowledge, and performs
  local, Light, Regular, and explicit Deep health checks.
- Markdown as the canonical generated link format, with Wikilink compatibility
  auditing for manual Obsidian use.
- Local-only operation with configurable `TRACEBOOK_ROOT`, plus documented local
  validation for the Skill package, Python compilation, tests, and whitespace.

### Not Included

- Migration, discovery, import, copying, or modification of an existing
  external knowledge root.
- An MCP server, background daemon, cloud sync service, API key, vector
  database, or hook.
- Automatic assertion that business facts are correct; Deep audit findings are
  candidates that require evidence and human review.
- Business-repository changes required to install or operate Tracebook.
