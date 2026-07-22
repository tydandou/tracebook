# Changelog

This project follows semantic versioning. Releases are created only after the
matching Git tag is published.

## [2.0.1] - 2026-07-22

### Fixed

- Accept UTF-8 BOM capture request files, including the default UTF-8 output
  produced by Windows PowerShell 5.1.
- Return structured `UNSUPPORTED_SCHEMA` JSON for legacy knowledge roots rather
  than a Python traceback.
- Document the required marketplace replacement sequence when an existing
  Tracebook marketplace must move to a new tagged release.

## [2.0.0] - 2026-07-22

### Added

- Stable `knowledge_id` authority pages with versioned Current and History
  sections while retaining content-event `event_id` idempotence.
- Explicit `create`, `revise`, and `change-status` capture operations with
  optimistic `expected_version` conflict detection.
- Deterministic `context` retrieval with Current-by-default behavior, CJK-aware
  tokenization, evidence-aware scoring, history, and `as-of` queries.

### Breaking Changes

- Knowledge roots now require schema version 2. Existing pre-v2 roots are
  rejected explicitly and are not migrated, imported, or mixed with v2 pages.

## [1.2.1] - 2026-07-22

### Fixed

- Replaced the Windows lifecycle Hook launcher with a native PowerShell Hook,
  so `UserPromptSubmit` and `Stop` no longer depend on a `python` command in
  the user PATH.
- Added executable Windows Hook tests for a PATH without Python, missing Git,
  malformed input, non-Git directories, unknown events, and plugin paths that
  contain spaces.

### Compatibility

- The lifecycle Hook remains non-blocking and non-writing. POSIX Hook behavior,
  the Skill, Runner, and all external knowledge-root formats remain unchanged.
- Codex users must review and trust the changed Hook commands after upgrading.

## [1.2.0] - 2026-07-21

### Added

- Codex `UserPromptSubmit` and `Stop` lifecycle reminders for Git repository
  work. The Hooks never write knowledge, parse transcripts, or block task
  completion.
- Positive and negative trigger cases plus executable Hook behavior tests.
- A documented automatic-workflow design, compatibility contract, and rollback
  path.

### Changed

- Broadened implicit Skill discovery to cover repository analysis, debugging,
  review, code/configuration changes, tests, builds, deployments, CI/CD, and
  incident diagnosis.
- Separated default minimal context loading from conditional durable capture.
- Made the final write gate deterministic with four capture conditions and
  controlled skip reasons.

### Compatibility

- Existing knowledge roots, language preferences, paths, lifecycle values,
  and runner request/response contracts are unchanged.
- Plugin Hooks require Codex trust and can be disabled; enhanced Skill metadata
  remains the fallback.

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
