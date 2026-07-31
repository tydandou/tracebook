# Changelog

This project follows semantic versioning. Release entries are tagged locally
before the matching Git tag is published.

## [Unreleased]

## [4.0.3] - 2026-08-01

### Changed

- A refused `superseded` capture now says why. A missing successor names the
  directory that was searched — `no \`settlement-window\` in project scope kind
  \`decision\`` — and a self-reference reports `must differ from knowledge_id`
  rather than sharing one message with the missing case. The previous wording,
  "must reference an existing entity in the same collection", did not reveal
  that for project scope the successor has to share the entity's `kind`.
- `SKILL.md` and `references/knowledge-lifecycle-rules.md` define what a
  collection is and record that the supersede constraint differs by scope:
  project entities are stored under `knowledge/<kind>/` and can only be
  superseded within one kind, while domain and pattern entities sit in a flat
  per-scope directory that accepts any kind. The asymmetry follows from the path
  layout rather than from a rule about what may replace what, and both scopes
  now have tests so neither can change silently. Both files also note that a
  successor of a different project kind is usually a different fact, making
  `deprecated` — which needs no replacement pointer — the right operation.
- `SKILL.md` and `references/knowledge-lifecycle-rules.md` state when a revise
  is warranted: a material conclusion, evidence, title, or lifecycle change.
  Evidence repairs remain versioned when a source moves, a health finding is
  resolved, or support changes materially; formatting-only churn does not.
- Both files also state that a direction not yet authorized for implementation
  is never the main entity's current version: it belongs in its own entity with
  `status: pending`, moved to `deprecated` when dropped. Recorded as Current, it
  costs an extra version as soon as it is overturned and leaves a proposal in
  History that never described the system.

### Fixed

- Historical results from an explicit project or system read now retain the
  actual source project's stable ID and name. Positional construction had put
  the boolean historical flag into `source_project.project_id`, returning
  `true` instead of the project ID for prior versions.
- `superseded` capture now accepts only a matching schema-v2 replacement whose
  status is `current`; a `pending` proposal can no longer retire confirmed
  knowledge. Non-Superseded entities reject stray replacement pointers.
- Domain and pattern replacement health validation now follows their flat
  per-scope storage identity, matching capture behavior for cross-kind
  successors instead of reporting a valid replacement as missing.
- Capture validates a Superseded replacement before creating the authority
  collection, so a rejected request leaves no empty directory behind.

## [4.0.2] - 2026-07-30

### Added

- New `references/retrieval-timing-rules.md` states when to retrieve again after
  the opening read: whenever the work yields a new retrieval key — a file path,
  class or function name, `knowledge_id`, table name, error code, or config key
  that was not in hand at the last query. It documents deterministic local
  retrieval, log/stack-trace evidence reverse lookup, and the rule that current
  source evidence outranks a conflicting stored conclusion.

### Fixed

- A project's knowledge index no longer accumulates one entry per title. Entries
  are keyed on the entity's stable storage link — project paths contain kind while
  domain/pattern paths use scope and `knowledge_id` — rather than on the rendered
  `- [title](link)` line, so a revise that changes the
  title updates the existing entry instead of appending a second one. A write to
  an entity also collapses duplicates earlier releases left for that link.
  Observed before this fix: a project with 4 knowledge files listed 9 entries,
  three naming titles its authority pages no longer carried.
- `check` reports an index that links one entity page more than once, under
  `Schema-v2 Entity Integrity`. `_duplicate_pages` skips `index.md` by design, so
  this accumulation was invisible to every health check. The check resolves the
  link and verifies schema-v2 frontmatter, so repeated links to an ordinary
  Markdown page are not misreported as duplicate entities.
- A registered system is now reachable by browsing. `04-systems/index.md` gains a
  generated navigation block listing each system with its id, and a system's own
  page lists its member projects and directed relations, rebuilt from its record
  on every `system-create` / `system-bind-project` / `system-relate`. Both are
  keyed on stable ids, and hand-written content outside the generated block is
  preserved. Previously the directory existed with nothing linking to it. The
  system id stays outside the generated block, so rebuilding a page written
  before the block existed does not leave two copies of it.
- System metadata commands validate every config and navigation target before
  their first authority write, then commit changed files through the existing
  registry-scope recoverable transaction. An invalid system page or total index
  can no longer make a command report failure after silently persisting a member
  or relation. Metadata operations use the fixed `registry -> systems-registry`
  lock order. After acquiring the registry lock, a new metadata command now
  rejects an unfinished transaction in that scope with
  `TRANSACTION_RECOVERY_REQUIRED`; this prevents a later command from changing
  prepared targets and turning a recoverable crash into a blocked transaction.
  Lock-free inspection also deduplicates transaction IDs, rechecks entries that
  disappear during diagnosis, and confirms unknown-scope findings with a second
  snapshot, so concurrent initialization is not misreported as corruption while
  persistent orphaned or invalid state remains blocked.
- Repeating an existing `system-bind-project` or `system-relate` now reconciles
  missing or stale generated navigation instead of returning before maintenance.
  `project-update --name` refreshes every member system page in the same
  registry-scope transaction, so project display-name changes do not leave stale
  system navigation.

### Changed

- Both knowledge-root `AGENTS.md` templates now send the reader to the root
  `index.md` as step 3 of the required read order, and replace the
  project-only "default location" section with one covering all four
  destinations — `01-projects`, `02-domain`, `03-patterns`, and `04-systems`
  (noting that systems are maintained by command, never by hand) — plus
  `99-archive`. `02-domain`, `03-patterns`, and `04-systems` appeared nowhere in
  either template before, even though the root `index.md` links all of them.
  `00-global/agent-workflow.md` joins the rule-file list. The root path is now
  stated on its own line rather than concatenated into a project path, which also
  ends the mixed `D:\root/01-projects/...` separators.
  **Existing knowledge roots are unaffected**: `initialize` never overwrites an
  existing file. Delete `AGENTS.md` and re-run `initialize`, or edit it by hand.
- The Chinese knowledge-root `AGENTS.md` template now matches the English one.
  It carries the same required read order, rule-file list, knowledge destination
  guidance, and task-end report. Both templates name `context-read-path`, state
  that the opening read is not the only retrieval, and clarify that the
  no-complete-logs rule bounds knowledge-root content rather than a log supplied
  for analysis. Repository `AGENTS.md` remains conditional on the file existing.
- The write gate now leads with what passes — a root cause backed by logs **plus**
  source, configuration, or reproduction — instead of burying it under the
  prohibition on log-only conclusions. The instruction not to load complete logs
  now explicitly bounds reads out of the knowledge root, not task input.

## [4.0.1] - 2026-07-28

### Added

- `preflight` reports a registered project's `systems` membership, listing each
  system's id, name, member projects, and recorded relations. Without it a
  caller could not tell whether a task spans a recorded system, which is what
  `context --system-id` requires. The field is omitted when the project belongs
  to no system.
- `check` reports `system_relation_candidate` (advisory) when a project's
  Current evidence resolves into another registered project's working tree and
  no system relation joins them. Attribution uses the deepest registered
  location, so a project nested inside another does not flag for citing its own
  sources. Shared topic words are deliberately not a signal.
- `SKILL.md` and the cross-project reading rules now state when to register a
  system relation — both projects already registered, a stable delivery
  dependency rather than a passing reference, and an unambiguous direction and
  kind — with copyable `system-create` / `system-bind-project` /
  `system-relate` commands. These three commands were previously absent from the
  skill, so relations were only ever created when a user asked for them by name.
  The skill also states that a relation makes a cross-project read possible
  without widening the default project scope, so a task spanning system members
  must pass `context --system-id`.
- `SKILL.md` opens with a Quick Start block holding runnable `preflight`,
  `context-read-path`, and `capture` commands, and shows `check` as a command
  rather than a prose parameter list. Capture is demonstrated only through
  stdin (`--request -`); `--request <path>` is documented as a parenthetical so
  a temporary request file is no longer presented as an equal option. Behavior
  is unchanged — both forms were already supported and still are.
- `SKILL.md` documents the `source_outside_root` review candidate, which the
  engine and its tests already implemented but the skill never mentioned.

### Changed

- `transactions` now also reports transactions that have published an intent but
  have no manifest yet, instead of skipping them. These get the new
  `writer-or-crash` disposition and `staging` state: a read-only diagnosis takes
  no lock, so it cannot distinguish an active writer from a crash before commit —
  only recovery can, under the scope lock. A staging directory with no intent at
  all predates the intent protocol and is still reported `cleanup-ready`; an
  intent that does not match its own transaction id is reported `invalid`,
  matching what recovery does with it. A caller that exhaustively matches on
  `disposition` will see the new value.

### Fixed

- Corrected the documented contract for `--evidence-path`. The 4.0.0 entry below
  and `SKILL.md` said it "returns only knowledge whose `## Current` section lists
  that file", which was inaccurate whenever `--query` was also supplied. The
  released behavior is unchanged: evidence matches are marked
  `evidence_match: true` and ranked first; without `--query` the result set
  contains those matches only; with `--query`, query hits are also returned
  marked `evidence_match: false`, so callers filter on that field for the
  reverse-lookup set alone.

## [4.0.0] - 2026-07-27

The major version is required because this release enforces previously
advisory capture-input boundaries.

### Added

- Evidence reverse query: `context-read-path`/`context-read` accept repeatable
  `--evidence-path` (repo-relative or project-absolute). Returns only knowledge
  whose `## Current` section lists that file as formal evidence
  (`evidence_match: true`), never a prose mention or a History reference.
  Exactly one project at the current snapshot only. `context-read` resolves a
  project-absolute path against the selected project's registered locations.
- Knowledge review candidates: with `--source-root`, `check` reports Current
  knowledge whose evidence files are missing (`source_missing`, strong) or
  changed after the knowledge was last updated (`source_mtime_newer`,
  advisory). `--review-after-days N` adds a `review_age_exceeded` advisory.
  These are review prompts and never change a knowledge status automatically.
  A stored evidence path that resolves outside `--source-root` is reported as
  `source_outside_root` (strong) without probing the external target.
- `capture --request -` reads the JSON request from stdin, so no temporary
  request file has to be created. `--request <path>` remains supported for
  pre-existing files outside governed trees.

### Changed

- Write-gate guidance is now per atomic knowledge item, not per whole task: a
  task's verified facts are each captured even when a separate, unverified
  dependency remains, which is captured as its own `status: pending` item.
  `pending` means a confirmed-but-unresolved item (known risk / awaited
  acceptance), not an evidence-poor guess.
- A capture request that includes the output-only `event_id` field now returns
  a specific hint instead of a bare "unknown fields" error.
- Health check report (`to_markdown`) now renders the `Duplicate Pages`,
  `Log Growth`, and `Review Candidates` sections that were previously computed
  but omitted.
- Retrieval ranking: on a score tie, the more recently updated knowledge now
  sorts first (was oldest-first).
- Risk level: a `source_missing` review candidate raises the scope risk level
  to High; advisory candidates raise it to Medium. Existing projects with
  missing evidence files may move from Low/Medium to High on the next check.
- Snapshot storage is now bounded: after each project capture the store keeps
  at most 10 valid versions including the live snapshot. Pruning atomically
  retires an old directory before deletion; a lock-free reader whose resolved
  root is retired retries from the current pointer instead of returning partial
  or empty context.

### Breaking Changes

- Removed the retired capture request fields `category`, `topic`, and
  `replacement`. They were accepted and then discarded by every code path;
  they are now rejected as unknown fields. A caller still sending any of them
  receives `INVALID_REQUEST` where the request previously succeeded.
- A capture request file resolving inside the knowledge root or the business
  repository is rejected with `INVALID_REQUEST`. Pipe the request through stdin
  with `--request -`, or use a pre-existing file outside both governed trees.

### Fixed

- Transaction recovery no longer deletes an active writer's manifestless
  staging directory. Writers publish a scope-bound internal intent before the
  transaction directory becomes visible; recovery waits for that scope and
  rechecks state before cleanup. Internal intent/manifest reads allow a
  concurrent Windows delete and normalize vanished paths to `FileNotFoundError`.
  First-use lock files are atomically published fully initialized, so competing
  processes no longer write the empty file before acquiring its byte lock. CLI,
  knowledge schemas, lock-free reads, and cross-project parallelism are unchanged.
- Capture gate rejections no longer carry a doubled `INVALID_REQUEST:` prefix.
  The gate's messages are already coded, so the runner passes them through
  instead of prefixing them a second time. A caller matching on the error code
  now sees one prefix.
- Chinese task-sentence retrieval: the tokenizer no longer builds bigrams across
  punctuation and word boundaries, so multi-clause queries recall the right
  entities.
- CRLF-saved authority pages are normalized on read and no longer silently drop
  out of retrieval results.
- Stopword-only queries (e.g. "the a is of to") now return no results instead
  of arbitrary pages.
- `project-status.md` records the numeric knowledge version (`v1`) instead of
  the title text.
- Windows snapshot durability tests no longer fail on 8.3 short-path
  comparisons, restoring verification of the pointer-last-commit and
  crash/recover guarantees.
- Runner responses are written as UTF-8 bytes instead of through the console's
  locale codepage, so CJK titles and queries no longer reach the caller as
  non-UTF-8 JSON on a non-UTF-8 Windows console.
- A snapshot-pruning failure can no longer surface as a capture error: pruning
  runs after the write is durable, and every step is now contained.

## [3.3.2] - 2026-07-24

### Removed

- Legacy aggregate-document capture path: the schema-v2 entity path
  (`knowledge_entity.py`) is now the only write path. The CLI already required
  `operation` and `knowledge_id` since v3.3.0, so the legacy path was
  unreachable through normal usage.

## [3.3.1] - 2026-07-23

### Added

- `preflight` now returns `blocked`/`blocked_reason`/`required_action` so
  that unregistered targets carry a machine-readable next step instead of a
  silent empty result. The `required_action.argv` array lets the agent execute
  `resolve` without guessing the Python executable, runner location, or root
  path.

## [3.3.0] - 2026-07-23

### Added

- Non-blocking identity advisory: `resolve` and `preflight` surface an
  `identity_advisory` when a project has a local-path identity with no Git
  remote, naming the project so its location can be updated if the directory
  moves. It never blocks and never guesses.

### Fixed

- The evidence gate now also covers the schema-v2 durable write path, so a
  `current` capture cannot bypass the source-evidence requirement.
- Context search scoring no longer matches on bare substrings; layered scoring
  plus a meaningful-overlap gate remove spurious low-relevance results.
- Windows reads snapshot pages with shared access and a bounded retry, so a
  concurrent writer no longer causes transient read failures.
- Transaction recovery cleans orphaned staged directories that have no manifest.

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
