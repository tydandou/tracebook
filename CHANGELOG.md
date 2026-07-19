# Changelog

This project follows semantic versioning. Releases are created only after the
matching Git tag is published.

## [1.0.0] - Unreleased

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
