# Changelog

This project follows semantic versioning. Release entries are tagged locally
before the matching Git tag is published.

## [3.2.0] - 2026-07-23

### Added

- Immutable per-project knowledge snapshots and atomic snapshot pointers for
  lock-free, complete context reads.
- `context-read-path` for reading an already activated target without root
  initialization, project registration, health maintenance, transaction
  recovery, or lock-file writes.

### Changed

- Project captures now commit materialized authority pages, snapshot pages, and
  the snapshot pointer in one recoverable project-scoped transaction. The
  pointer is replaced last, so readers observe the prior or next complete
  snapshot rather than a partial multi-file update.
- `resolve` seeds a snapshot for an existing activated project; the Skill now
  uses `preflight` plus `context-read-path` as its normal read path and reserves
  `resolve` for activation and maintenance.

## [3.1.0] - 2026-07-23

### Added

- Read-only `preflight` and `context-read` flows for new or uncertain target
  projects, so reference architecture can be loaded before the target exists
  or is registered.
- Explicit multi-project systems with stable system IDs, member projects, and
  directed API/event relationships for bounded microservice context reads.
- Explicit cross-project context selection, source-project attribution, and a
  `reference` profile limited to architecture, module, and decision knowledge.

### Fixed

- Context retrieval now returns an empty result when no authority page matches
  the query instead of returning unrelated Current entries by lifecycle score.
- Documented and regression-tested the full project registration, related
  project, empty project, iterative capture, and retrieval flow.

## [3.0.0] - 2026-07-22

### Added

- Immutable `project_id` project identity with location and normalized Git
  remote as explicit resolution signals. New non-Git projects are supported.
- Human-readable project knowledge directories using a display-name slug plus
  short ID suffix, and a generated project-name navigation index.

### Fixed

- Exclude generated project logs from Light Check orphan-page and
  missing-source findings.

### Breaking Changes

- Project registry v1 is replaced by registry v2. Existing registry-v1 roots
  are rejected explicitly and are not migrated, moved, or merged automatically.

## [2.1.0] - 2026-07-22

### Changed

- Removed the optional Codex lifecycle Hook implementation. Tracebook is now a
  pure Skill plugin with no Hook commands, stdin protocol handling, or Hook
  trust-review requirement.
- Strengthened the Skill description to instruct supported hosts to invoke it
  before repository work and evaluate the durable-knowledge write gate after
  task completion.

### Compatibility

- External knowledge-root formats, Runner behavior, and Skill workflow rules
  are unchanged. Automatic Skill selection remains host-dependent; users can
  invoke `$tracebook` explicitly at any time.

## [2.0.3] - 2026-07-22

### Fixed

- Pass the lifecycle event explicitly to the Windows PowerShell Hook and use
  the hook working directory for Git detection. The Hook now drains stdin
  without parsing its JSON, so malformed Windows hook input cannot silently
  suppress its context reminder.

### Compatibility

- The Hook remains non-blocking and non-writing, and retains the existing
  `systemMessage` response format. Users upgrading must re-review and trust
  the changed Windows Hook commands.

## [2.0.2] - 2026-07-22

### Added

- Return a human-readable `user_summary` for every capture that actually
  changes knowledge files, so the host can confirm the write immediately.

### Fixed

- Reject missing, null, and blank schema-v2 `operation` values at the Runner
  boundary before they can reach the retired aggregate capture path.

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
