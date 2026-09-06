# Tracebook

<p align="center">
  <img src="assets/tracebook-hero.svg" alt="Tracebook — memory that survives the chat" width="100%">
</p>

<p align="center">
  <a href="https://github.com/tydandou/tracebook/actions/workflows/ci.yml"><img src="https://github.com/tydandou/tracebook/actions/workflows/ci.yml/badge.svg?branch=master" alt="CI"></a>
  <a href="https://github.com/tydandou/tracebook/releases/latest"><img src="https://img.shields.io/github/v/release/tydandou/tracebook" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/tydandou/tracebook" alt="Apache-2.0 license"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10 or newer">
</p>

<p align="center"><strong>A local, evidence-backed memory layer for coding agents.</strong></p>

<p align="center">
  <a href="https://tydandou.github.io/tracebook/">Website</a> ·
  <a href="#install-in-two-commands">Install</a> ·
  <a href="#one-task-two-sessions">30-second tour</a> ·
  <a href="https://tydandou.github.io/tracebook/demo/">Live demo</a> ·
  <a href="https://tydandou.github.io/tracebook/#compare">Compare</a> ·
  <a href="README.zh-CN.md">简体中文</a>
</p>

Your coding agent should not rediscover the same architecture, incident root
cause, or business rule every time a chat starts. Tracebook loads only relevant
project knowledge before repository work, then preserves only conclusions that
are verified, durable, and backed by evidence.

It is a pure Agent Skill for Codex, Claude Code, and other Open Agent Skills
hosts: **no server, database, daemon, lifecycle hook, API key, or file written
to your business repositories.** Knowledge stays as inspectable Markdown under
`~/.tracebook`.

The current release is **stable and feature-complete for its documented scope**.
Project activation, focused retrieval, evidence-gated capture, lifecycle history,
cross-project systems, crash-safe transactions, recovery, and health checks are
implemented and verified in CI on Python 3.10 and 3.13 across Ubuntu and Windows.
You can use Tracebook for regular project work without operating any supporting
service.

## Install in two commands

Requires Python 3.10 or newer. Install the current stable release, then start a
new agent session:

**Codex**

```text
codex plugin marketplace add tydandou/tracebook --ref v4.0.8
codex plugin add tracebook@tracebook
```

**Claude Code**

```text
claude plugin marketplace add tydandou/tracebook
claude plugin install tracebook@tracebook
```

That is the complete runtime setup. See [Install](#install) for local
development, updates, recovery, and other Open Agent Skills hosts.

## One task, two sessions

```text
Session 1
> Diagnose the refund retry bug and verify the root cause.

Tracebook  →  the agent verifies the finding against source and tests
           →  the durable conclusion is captured with its evidence

Session 2, days later
> Change the refund retry policy without breaking existing behavior.

Tracebook  →  the relevant current conclusion is loaded before editing
           →  the agent starts from verified context instead of rediscovery
```

Capture is not a transcript dump. A stored authority page has a stable identity,
status, version history, and source evidence:

```markdown
---
knowledge_id: refund-retry-policy
status: current
version: 2
---

## Current

Refunds retry at most twice with a 3-second timeout.

Evidence:
- `src/order/RefundController.java:L87`
```

If a task produces no verified, reusable conclusion, Tracebook writes nothing.

For executable proof, run the
[isolated cross-session demo](https://tydandou.github.io/tracebook/demo/):

```text
python demo/cross_session_demo.py
```

It uses the real runner with a temporary business repository and a separate
temporary knowledge root, verifies the capture, recalls it in a second simulated
session, and removes the temporary environment on exit.

## The difference

| Without Tracebook | With Tracebook |
| --- | --- |
| Each new session reopens the same files | Relevant conclusions are loaded before work |
| Important context disappears with the chat | Durable knowledge lives outside the chat and repository |
| A stale note can look authoritative | Lifecycle states and history make change explicit |
| Memory systems add services or repo files | Local Markdown; no service and zero business-repo writes |
| Cross-project context is copied manually | Stable project IDs and explicit system relations bound retrieval |

Tracebook is most useful for long-lived repositories, recurring incident work,
multi-repository systems, and teams that need to inspect why an agent believes a
project fact. It is intentionally not a semantic search service or an automatic
dump of everything an agent sees.

If this is a problem you want solved, [star Tracebook](https://github.com/tydandou/tracebook)
to follow its development and help other coding-agent users discover it.

## Why Tracebook

Important engineering context is easily scattered across conversations,
incidents, source files, and personal notes. Tracebook keeps that context in a
governed Markdown knowledge root with evidence, lifecycle status, indexes, and
health history. Agents can read only the relevant context, while people retain
an inspectable record of what was captured and why.

The knowledge root stays separate from business code. That separation lets
multiple business repositories use one local knowledge system without
installing files or services into those repositories.

### Measured leverage

Because capture is evidence-gated, each stored conclusion declares the source
an agent would otherwise re-read to re-derive it. Reusing that conclusion is
typically cheaper than re-exploring its cited source — the more scattered
source a conclusion condenses, the larger the saving.

This is per-hit leverage, not a guaranteed whole-project win: net savings also
depend on how often knowledge is reused versus the one-time capture cost.

## Features

- Project, domain, and pattern scopes for repository-specific facts, reusable
  business knowledge, and reusable engineering practice.
- Evidence-backed capture with `Current`, `Pending`, `Deprecated`,
  `Superseded`, and `Historical` lifecycle states.
- Deterministic project resolution, governed writes, index/status/log updates,
  and structured JSON results.
- Immutable per-project knowledge snapshots with atomic pointers, so normal
  context reads do not acquire locks and concurrent work on different projects
  remains isolated.
- Immutable project IDs with local paths and normalized Git remotes resolving to
  the same project, so clones of one remote share knowledge while unrelated
  projects remain isolated.
- Local, Light, Regular, and explicit Deep health behavior, with Deep findings
  kept as review candidates rather than automatic facts.
- Portable generated Markdown links plus Wikilink auditing for compatibility
  with manually edited Obsidian knowledge.
- Broad implicit Skill triggers for repository analysis, debugging, review,
  implementation, tests, and release work. Durable capture remains
  evidence-gated rather than automatic.
- Local storage with a strict zero-write boundary for the business repository.

## Requirements

- Project resolution accepts any local directory. Git is optional: clones with
  the same `origin` resolve to one project, while non-Git directories resolve
  through their externally stored project locations.
- Python syntax used by the source requires Python 3.10 or newer. The release
  CI matrix is configured for Python 3.10 and 3.13 on Ubuntu and Windows; the
  local full verification environment is Python 3.13.12 on Windows.
- For marketplace installation, use Codex or Claude Code. The documented
  command shapes were checked with Codex CLI 0.144.1 and Claude Code 2.1.138;
  those versions are evidence, not declared minimum versions.
- For another Open Agent Skills host, follow its documented method to install
  the complete Skill directory. The same Python runtime requirement applies.

PowerShell transport compatibility is stated by evidence level:

- Windows PowerShell 5.1 is release-tested through a real native-command
  pipeline; v4.0.6 local validation used 5.1.26100.9168.
- PowerShell 7.x is covered by the Windows CI `pwsh` smoke job, which prints the
  exact hosted-runner version. v4.0.6 local validation also used 7.6.5. The
  helper uses only long-stable PowerShell syntax plus .NET UTF-8, Base64, and
  SHA-256 APIs, so 7.4, 7.5, and 7.6 are within its compatibility contract;
  this is not a claim that every patch release runs in every CI build.
- PowerShell 8 and later cannot be claimed as tested before release. Because
  the native pipeline receives ASCII only and the helper has no 7.x-specific
  dependency, forward compatibility is expected, but an upgrade must rerun the
  PowerShell transport smoke test before that engine is marked verified.

## Install

The `4.0.8` release is available as the `v4.0.8` tag. Use the tagged
installation commands for the stable release, or use the local development
loading instructions when working from a clone.

### Codex

Install the tagged release:

```text
codex plugin marketplace add tydandou/tracebook --ref v4.0.8
codex plugin add tracebook@tracebook
```

For local development, clone the repository and add its local marketplace:

```text
git clone https://github.com/tydandou/tracebook.git
cd tracebook
codex plugin marketplace add .
codex plugin add tracebook@tracebook
```

Start a new Codex session after installation.

Tracebook is a pure Skill plugin: it has no lifecycle Hooks and therefore
requires no `/hooks` trust review. Its Skill description instructs the host to
invoke it before repository engineering work and evaluate its write gate after
task completion. You can always invoke `$tracebook` explicitly.

### Update or recover a Codex installation

Removing a plugin never touches its knowledge root. If
`codex plugin add tracebook@tracebook` reports the plugin was not found, the
`tracebook` marketplace source is absent from the active profile —
`codex plugin marketplace list` confirms it. Re-add the source, then install:

```text
codex plugin marketplace add tydandou/tracebook --ref v4.0.8
codex plugin add tracebook@tracebook
```

To move to a different tagged source, replace the marketplace first:

```text
codex plugin remove tracebook@tracebook
codex plugin marketplace remove tracebook
codex plugin marketplace add tydandou/tracebook --ref v4.0.8
codex plugin add tracebook@tracebook
```

For a local clone, `git pull --ff-only` then re-run the two local commands
above.

### Claude Code

```text
claude plugin marketplace add tydandou/tracebook
claude plugin install tracebook@tracebook
```

For local development from a clone, load the plugin directory directly:

```text
git clone https://github.com/tydandou/tracebook.git
cd tracebook
claude --plugin-dir ./plugins/tracebook
```

Start a new session or run `/reload-plugins` after a marketplace installation.

### Update or recover a Claude Code installation

Refresh the marketplace source, then update the installed plugin (a restart
applies the update):

```text
claude plugin marketplace update tracebook
claude plugin update tracebook@tracebook
```

If the plugin or marketplace is missing, diagnose with `claude plugin list` and
`claude plugin marketplace list`, then re-add the source and reinstall:

```text
claude plugin marketplace add tydandou/tracebook
claude plugin install tracebook@tracebook
```

To move to a different source, remove both first:

```text
claude plugin uninstall tracebook@tracebook
claude plugin marketplace remove tracebook
claude plugin marketplace add tydandou/tracebook
claude plugin install tracebook@tracebook
```

### Open Agent Skills

The reusable package is
[`plugins/tracebook/skills/tracebook/`](plugins/tracebook/skills/tracebook/).
Copy that complete directory as `tracebook` into the Skill directory documented
by the target agent, then start a new session. Keep `SKILL.md`, `references/`,
`assets/`, and `scripts/` together.

By default, knowledge is stored at `~/.tracebook`. To select another external
root, set `TRACEBOOK_ROOT` before starting the agent. These examples read the
existing user-home value; they do not replace or assign `HOME`.
The `preflight` and `resolve` responses identify whether the selected root came
from `--root`, `TRACEBOOK_ROOT`, or the default. An explicit `--root` that
differs from `TRACEBOOK_ROOT` remains authoritative but returns a warning, so a
second empty knowledge root is visible instead of being silently mistaken for
the intended store.

POSIX shell:

```sh
export TRACEBOOK_ROOT="$HOME/team-knowledge"
```

PowerShell:

```powershell
$env:TRACEBOOK_ROOT = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'team-knowledge'
```

### Knowledge-document language

English is the default: if no language file exists, Tracebook creates future
knowledge-root templates and project bootstrap pages in English. To use Chinese
for future created content, create this file yourself **before the first
`resolve`** for that root:

```text
<TRACEBOOK_ROOT>/.tracebook-state/config.json
```

```json
{
  "version": 1,
  "knowledge_language": "zh"
}
```

The only supported values are `en` and `zh`. This is a root-level preference;
there is no install prompt, configuration command, or environment-variable
override. Changing it never translates, rewrites, moves, or deletes existing
knowledge. It changes only the default language of documents created or
repaired later. Paths, Markdown links, lifecycle values, event identifiers, and
health machine fields remain stable English protocol values.

## Quick Start

1. Install Tracebook through a marketplace or load the local clone.
2. Open a new agent session in the project root you are working on; Git does
   not need to be initialized yet.
3. Ask for normal repository work, such as: `Diagnose this issue and verify the
   root cause.` The broader Skill metadata lets Codex select Tracebook without
   requiring its name in every prompt.
4. Work normally. Tracebook preflights the target and, for an activated project,
   reads the latest committed project snapshot without taking a lock. It uses
   `resolve` only when activation or maintenance requires write permission.
5. At task end, it captures and checks only a new, verified durable conclusion.
   Routine work with no such conclusion needs no extra skip report.

Tracebook does not write durable knowledge after temporary Q&A, pure log
analysis, unverified inference, a user prohibition, or a task with no durable
conclusion.

## Choose a Knowledge Scope

| Scope | Use it for | Stored under |
| --- | --- | --- |
| `project` | Facts specific to one project | `01-projects/<readable-name>--<id-suffix>` |
| `domain` | Reusable business terminology, rules, processes, or industry knowledge | `02-domain` |
| `pattern` | Reusable engineering practice | `03-patterns` |

Choose the narrowest accurate scope. Project facts should not be promoted to
domain or pattern knowledge merely because they might be useful elsewhere.

## Natural-Language Usage

The Plugin is designed to be invoked in normal task language. Examples:

- `Use Tracebook to load architecture and source-map context before changing the order flow.`
- `Use Tracebook while debugging this incident, but do not capture anything unless the root cause is verified.`
- `Capture this verified settlement term as reusable domain knowledge with its source evidence.`
- `Record this idempotent-consumer approach as a reusable pattern, then run the required health check.`
- `Run a Deep Tracebook audit for the current project; keep findings as candidates for human review.`

Before engineering work, the Skill reads the external-root rules, health
status, project index, and project status, followed only by relevant documents.
After the task, it applies the durable-write gate described in
[`SKILL.md`](plugins/tracebook/skills/tracebook/SKILL.md).

## Daily Workflow

This is the deterministic runner workflow for integrations, diagnosis, and
other cases that need reproducible commands. Natural-language Plugin use
remains the primary interface. The examples below assume the shell is at the
business repository root, `SKILL_DIR` points to the installed Tracebook Skill,
and `TRACEBOOK_ROOT` is set as shown above.

### Preflight a new or uncertain target

Before creating a new project outside the current repository, run the read-only
preflight. It reports whether a target is already registered and never creates
the root, project metadata, or target directory:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" preflight \
  --root "$TRACEBOOK_ROOT" \
  --cwd /workspace/new-service
```

### Resolve

With the default knowledge root, the concise command is:

```text
python "$SKILL_DIR/scripts/tracebook_runner.py" resolve --cwd .
```

To pass the configured root explicitly:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" resolve \
  --root "$TRACEBOOK_ROOT" \
  --cwd .
```

`resolve` initializes or repairs only missing template files in the configured
external root. Every project has an immutable `project_id`; the current local
path and optional normalized Git remote resolve to that ID. It returns `root`,
`project`, and the ordered `read_paths`. It does not search for or import a
different existing knowledge root. It is an activation/maintenance command and
may acquire write locks.

### Read an activated project without blocking

For ordinary development work on an already registered project, use the
lock-free snapshot reader. It does not initialize the root, register a project,
repair health, recover transactions, or create lock files:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" context-read-path \
  --root "$TRACEBOOK_ROOT" --cwd . --query "order retry behavior"
```

If it returns `PROJECT_ACTIVATION_REQUIRED`, run `resolve` once with write
permission, then retry the read. A project capture builds a complete immutable
knowledge snapshot and atomically switches its pointer only after all snapshot
pages are ready. Readers therefore see the previous or the next complete
snapshot, never a partial write.

### Update a project location or remote

Project metadata lives outside the business repository at
`01-projects/<readable-name>--<id-suffix>/project.json`. Names are the primary
human-facing label and may repeat; the suffix disambiguates folders while the
immutable `project_id` remains the actual identity. `01-projects/index.md`
lists projects by name for browsing and search. Locations and remotes are unique
signals that resolve to a `project_id`. When a project moves, replace its
complete location list (repeat `--location` for multiple clones):

```text
python "$SKILL_DIR/scripts/tracebook_runner.py" project-update \
  --root "$TRACEBOOK_ROOT" \
  --project-id prj-... \
  --location /workspace/project
```

Bind a later remote explicitly. A remote already owned by another project is
rejected; Tracebook never automatically merges knowledge:

```text
python "$SKILL_DIR/scripts/tracebook_runner.py" project-bind-remote \
  --root "$TRACEBOOK_ROOT" \
  --project-id prj-... \
  --remote github.com/acme/project
```

### Inspect or recover pending transactions

`resolve` attempts a safe roll-forward only when every prepared transaction
still matches its recorded hashes. If it refuses recovery, inspect the external
root before taking any manual action:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" transactions \
  --root "$TRACEBOOK_ROOT"
```

`transactions` is read-only: it does not need `--cwd`, acquire a lock, create
templates, or change knowledge files. Its JSON reports each transaction as
`recoverable`, `blocked`, `cleanup-ready`, `writer-or-crash`, or `invalid`, with
structured issue codes such as `TARGET_CHANGED`.

`writer-or-crash` means the transaction published an intent but has no manifest
yet: either a writer is still staging files, or a process died before the commit
point. A read-only diagnosis takes no lock and so cannot tell them apart — only
`recover-transactions` can, under the scope lock. Do not delete such a directory
by hand; let recovery handle it.

Use the explicit maintenance command only to roll forward transactions already
judged safe; it never discards, quarantines, or overwrites a changed target:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" recover-transactions \
  --root "$TRACEBOOK_ROOT"
```

Project and system metadata writers reject a pending transaction in their
shared `registry` scope with `TRANSACTION_RECOVERY_REQUIRED`. Run the read-only
diagnostic and explicit recovery above before retrying; a later write is never
allowed to overwrite prepared targets and make the earlier transaction
unrecoverable.

### Capture

Send capture requests through the versioned ASCII-safe envelope. It preserves
the exact UTF-8 bytes and verifies them with SHA-256 before parsing, so the same
request works through Windows PowerShell 5.1/7.x, Bash, and Zsh without depending
on the active console code page. Example request body:

```json
{
  "operation": "create",
  "knowledge_id": "order-retry-eligibility",
  "scope": "project",
  "kind": "business-rule",
  "title": "Order retry eligibility",
  "body": "Only orders in the retryable state may re-enter fulfillment.",
  "evidence": [
    "src/order.py:L20-L38"
  ],
  "status": "current"
}
```

On Linux and macOS (Bash or Zsh), wrap a UTF-8 request and pipe the ASCII-only
envelope to the Runner:

```bash
{
  python "$SKILL_DIR/scripts/tracebook_request_envelope.py" --request - <<'JSON'
{
  "operation": "create",
  "knowledge_id": "order-retry-eligibility",
  "scope": "project",
  "kind": "business-rule",
  "title": "Order retry eligibility",
  "body": "Only orders in the retryable state may re-enter fulfillment.",
  "evidence": ["src/order.py:L20-L38"]
}
JSON
} | python "$SKILL_DIR/scripts/tracebook_runner.py" capture \
  --root "$TRACEBOOK_ROOT" --cwd . --request -
```

On Windows PowerShell 5.1 or PowerShell 7.x:

```powershell
$request = @'
{"operation":"create","knowledge_id":"order-retry-eligibility","scope":"project","kind":"business-rule","title":"Order retry eligibility","body":"Only orders in the retryable state may re-enter fulfillment.","evidence":["src/order.py:L20-L38"]}
'@
& "$SKILL_DIR/scripts/New-TracebookRequestEnvelope.ps1" -Json $request |
  python "$SKILL_DIR/scripts/tracebook_runner.py" capture `
    --root "$env:TRACEBOOK_ROOT" --cwd . --request -
```

The Runner still accepts legacy raw UTF-8 JSON for compatibility. Do not pipe
raw non-ASCII JSON from Windows PowerShell 5.1: its default native-command
pipeline encoding is ASCII and irreversibly replaces those characters before
Python receives them. Suspicious replacement markers or runs of ASCII `?` are
rejected before any knowledge write; `--allow-suspicious-encoding` is reserved
for text where those characters are intentional.

`--request <path>` remains available for a pre-existing file outside both the
knowledge root and business repository. Files inside either governed tree are
rejected; do not create a temporary request there.

`current` knowledge requires an evidence list. A durable, explicitly unresolved
item may use `pending` with an empty evidence list; `pending` must not be
presented as a confirmed fact. The source format
`src/order.py:L20-L38` identifies the business-repository evidence without
copying source into the knowledge root.

Create is idempotent for the same entity event. To change an entity, first use
`context` to obtain its `knowledge_id` and current version, then send `revise`
or `change-status` with `expected_version`. The Runner preserves the former
Current section in History. A version mismatch is an explicit conflict; it is
never silently merged. For a replaced conclusion, use `superseded` with an
existing `replacement_knowledge_id`.

### Context

Run a bounded, deterministic search before detailed repository work:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" context \
  --root "$TRACEBOOK_ROOT" \
  --cwd . \
  --profile adaptive \
  --query "order retry duplicate charge" \
  --max-results 10 \
  --max-chars 20000
```

The `adaptive` profile searches Current first and retries History discovery only
after zero eligible Current matches. It still returns the selected current/as-of
version, does not attach History by default, keeps the 10-entity / 20,000-character
limits, and reports `adaptive_history_fallback`. Existing callers that omit a
profile retain the Current-only `default` behavior. Add
`--include-history` for prior versions, or `--as-of YYYY-MM-DD` to reconstruct
what was current on a date. The JSON includes stable IDs, score, evidence,
status, version state, update date, and a deterministic excerpt; it is not a vector
database or a claim that the returned result is business truth. For history,
version, change, regression, Git-commit, code-evolution, or change-rationale
questions, use the bounded audit preset. A current-worktree status or diff check
does not require History unless requested:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" context-read-path \
  --root "$TRACEBOOK_ROOT" --cwd . \
  --profile audit --query "why retry behavior changed"
```

`--profile audit` discovers eligible entities through Current or History and
defaults to 30 selected entities / 50,000 result-content characters. A historical
match returns the selected current version, identified by `match_source` and
`matched_version`; it does not override status, kind, project, or as-of filters.
`--include-history` alone retains its attachment-only discovery behavior.

For a decisive entity, read its complete body and evidence from the same snapshot:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" context-read-path \
  --root "$TRACEBOOK_ROOT" --cwd . --knowledge-id order-retry-eligibility \
  --full-content --include-history
```

`--full-content` requires `--knowledge-id`; use `--kind` when IDs exist in multiple
project collections. Complete items that do not fit are omitted, never silently
clipped. Without it, `excerpt` is a 500-character prefix; `excerpt_truncated` is
independent of result-set `truncated`. History can still be truncated, so this is
not an unconditional complete-version-chain guarantee.
Domain/pattern and explicit legacy fallback read the body and metadata from one
authority-page read; `read_snapshots` covers projects, not a cross-scope snapshot.

Explicit limits override presets. `max-results` limits entities in current_context;
`returned_count` also counts attached versions. `max-chars` budgets compact JSON
array contents (including separators) for current_context, historical_context,
warnings, omitted_entities and history_omitted_entities. Fixed envelope/brackets,
request echoes and selected-project provenance are excluded, so it is not a whole
pretty-printed JSON size limit. `budget_chars_used` reports usage. Omission samples
contain at most 10 path-qualified entities and share that budget; counts remain
complete. `history_available: null` means history was not inspected.

For zero, truncated or insufficient results, follow up with concrete source paths,
IDs or recorded terminology. Adaptive recovers a history-only term after a zero
Current match; audit remains the explicit profile for historical analysis.
Compare `read_snapshots` and versions when combining reads, and verify applicability
against source before adopting a conclusion. The Skill bounds follow-ups and
discloses remaining gaps. The read-only audit profile is distinct from the `audit`
command, which persists a Deep health report.

### Read related microservices deliberately

The active project remains the default boundary. To read a service explicitly
named by the user, discover its stable ID first, then include only that ID:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" project-search \
  --root "$TRACEBOOK_ROOT" --query order-service

python "$SKILL_DIR/scripts/tracebook_runner.py" context \
  --root "$TRACEBOOK_ROOT" --cwd . \
  --project-id prj-... --query "OrderPaid event contract"
```

Register a system when a bounded set of microservices shares contracts or
directed relationships. A project may belong to multiple systems:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" system-create --root "$TRACEBOOK_ROOT" --name "Commerce"
python "$SKILL_DIR/scripts/tracebook_runner.py" system-bind-project --root "$TRACEBOOK_ROOT" --system-id sys-... --project-id prj-...
python "$SKILL_DIR/scripts/tracebook_runner.py" system-relate --root "$TRACEBOOK_ROOT" --system-id sys-... --source-project-id prj-... --target-project-id prj-... --kind event
python "$SKILL_DIR/scripts/tracebook_runner.py" context --root "$TRACEBOOK_ROOT" --cwd . --system-id sys-... --query "OrderPaid event contract"
```

For a new project that explicitly borrows another project's architecture, pass
that source project to the read-only command and use `--profile reference`.
It does not require `--cwd`, so it cannot initialize or register the new
target before development starts:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" context-read \
  --root "$TRACEBOOK_ROOT" --project-id prj-... \
  --profile reference --query "image generation architecture"
```

The profile returns only architecture, module, and decision entries. Every
cross-project result identifies its source; Tracebook never scans every
registered project by default.

### Check the captured scope

Integrations must preserve this exact data dependency:

```text
capture.changed_paths -> repeated check --changed
capture.new_paths     -> repeated check --new-path
capture.health_scope  -> check --scope
check_type Deep       -> audit --scope with the same health_scope
```

For example, assemble the check command by repeating flags for every returned
path:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" check \
  --root "$TRACEBOOK_ROOT" \
  --cwd . \
  --source-root . \
  --changed "$CHANGED_PATH_1" \
  --changed "$CHANGED_PATH_2" \
  --new-path "$NEW_PATH_1" \
  --scope "$HEALTH_SCOPE"
```

A direct `check` or `audit` that is not following a capture defaults to
`project` when `--scope` is omitted. After a capture, however, a missing or
invalid `health_scope` is an error: stop and report the incomplete response;
never fall back to `project`.

### Run a requested Deep audit

`check_type: Deep` means a Deep audit is required; it does not mean the audit
has already run. Reuse the same capture `health_scope`:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" audit \
  --root "$TRACEBOOK_ROOT" \
  --cwd . \
  --source-root . \
  --scope "$HEALTH_SCOPE"
```

The audit report contains candidates. A person must compare them with their
evidence before any finding becomes a durable conclusion.

### Structured JSON fields

| Command | Emitted fields | Meaning |
| --- | --- | --- |
| `resolve` | `root`, `root_source`, `root_existed`, `root_created`, `root_initialized_before`, `root_initialized`, `project`, `read_paths` | Configured root provenance and initialization result, project record resolved by `project_id`, and focused context paths |
| `preflight` | `root_source`, `root_existed`, `root_initialized`, `target`, `registered`, `project`, `read_paths` | Read-only root and target inspection; does not initialize or register |
| `project-search` | `projects` | Deterministic registered-project candidates |
| `context-read` | `current_context`, `historical_context`, `warnings`, `truncated`, result/truncation metadata | Read selected registered projects without activating a target |
| `context-read-path` | `current_context`, `historical_context`, `warnings`, `truncated`, result/truncation metadata | Lock-free read of an already activated target's committed project snapshot |
| `project-update` | `project` | Explicitly update a project name or complete location list |
| `project-bind-remote` | `project` | Bind a normalized remote to an existing project |
| `system-create` | `system` | Create an explicit multi-project system |
| `system-bind-project` | `system` | Add a registered project to a system |
| `system-relate` | `system` | Add a directed relationship between two system members |
| `transactions` | `root`, `transactions` | Read-only transaction diagnostics and per-transaction disposition |
| `recover-transactions` | `recovered_paths` | Explicit safe roll-forward results; never a discard or quarantine action |
| `context` | `current_context`, `historical_context`, `warnings`, `truncated`, result/truncation metadata | Bounded deterministic authority-page retrieval |
| `capture` | `changed_paths`, `new_paths`, `skipped`, `health_scope`, `event_id`, `warnings` | Versioned entity transaction result, non-fatal cleanup diagnostics, and scope required by the following check |
| `check` | `check_type`, `changed_paths`, `report`, `findings` | Required health level, persisted health paths, human-readable Markdown, and structured findings |
| `audit` | `changed_paths`, `report`, `findings` | Persisted Deep-health paths plus human-readable and structured audit findings |

`event_id` identifies the idempotent capture event when one is available.
`skipped: true` means the capture made no new knowledge write. Consumers should
use fields only from the command that emitted them. Capture `warnings` do not
roll back an already durable write; for example, a failed best-effort
`snapshot-prune` is reported there. The Markdown `report` remains the human view, while
`findings` is the stable JSON view for automation.

## Knowledge Layout and Multi-Project Isolation

The default local root has this governed layout:

```text
~/.tracebook/
├── 00-global/          # shared rules, workflow, and health state
├── 01-projects/        # one readable, isolated directory per project
├── 02-domain/          # reusable business knowledge
├── 03-patterns/        # reusable engineering knowledge
├── raw/                # original material awaiting organization
└── 99-archive/         # historical material
```

Every project is stored under
`01-projects/<readable-name>--<id-suffix>` and identified by an immutable
`project_id`. The storage label is created once from the name plus a short ID
suffix, so duplicate names remain distinguishable. A later name change updates
the project configuration and navigation but does not move the knowledge
directory. The same normalized remote or registered location resolves to the
same project; different matches for a path and remote are reported as a conflict
and never merged automatically.

## Link Policy

Markdown links are the canonical output format. Tracebook templates and runner
writes generate standard Markdown links with relative paths so the knowledge
remains portable across Markdown tools.

Wikilinks are accepted as compatibility input for manually edited Obsidian
knowledge. Health checks audit both Markdown links and Wikilinks, but Tracebook
does not generate Wikilinks. See the
[`directory rules`](plugins/tracebook/skills/tracebook/references/directory-rules.md)
for the governed destinations.

## Privacy and Repository Boundaries

- All Tracebook knowledge and health state stays in the configured local
  external root (`~/.tracebook` by default).
- Tracebook reads business files only when context or evidence validation needs
  them. It does not copy the source tree into the knowledge root.
- Initialization, capture, check, and audit write only inside the external
  root. Installing and operating Tracebook requires zero writes to the business
  repository and does not create a project-level `AGENTS.md` there.
- No API key, cloud sync, MCP server, vector database, or background daemon is
  required or provided. No lifecycle Hooks are bundled; focused context loading
  and write-gate evaluation are handled by the Skill, with manual
  `$tracebook` invocation always available.
- Tracebook does not discover, migrate, import, copy, or modify an existing
  knowledge root automatically. Pointing `TRACEBOOK_ROOT` at a location is an
  explicit configuration choice, not an import operation.

Existing external knowledge is **not imported automatically**. Tracebook does
not search for another knowledge root or merge its contents into the configured
root.

## Health Checks and Human Review

| Level | Typical behavior |
| --- | --- |
| Local | Reads and reports on the selected scope when no higher trigger applies; it does not write scope status or logs. If the command registers a previously unknown project, it refreshes the global aggregate so the registry and aggregate remain consistent. |
| Light | Follows a knowledge write or changed knowledge files; checks links, indexes, sources, code paths, and status. |
| Regular | Triggered by elapsed time or accumulated changes, pages, pending confirmations, or missing sources; adds orphan, drift, duplicate, and log review. |
| Deep | Requested after the Deep threshold, a large core knowledge page, or an explicit audit request; samples durable conclusions against evidence. |

The detailed policy is in the
[`health check rules`](plugins/tracebook/skills/tracebook/references/health-check-rules.md).
A `check` result can request Deep work, but only `audit` performs it. Deep
findings are possible fact, source, root-cause, and status issues. They never
assert business truth automatically and require human review. No health command
may modify business code.

## Troubleshooting

- **The Plugin is unavailable:** run `codex plugin marketplace list`. If it
  does not list `tracebook`, add the intended tagged release or local clone
  before installing `tracebook@tracebook`, then start a new session. In Claude Code,
  `/reload-plugins` reloads an installed plugin.
- **Unexpected project resolution:** pass the project root with `--cwd`. Check
  `git remote get-url origin` when clones should share knowledge; use
  `project-update` or `project-bind-remote` to resolve a path/remote conflict.
- **Knowledge is in an unexpected location:** inspect `TRACEBOOK_ROOT` in the
  environment that launched the agent. If unset, the root is `~/.tracebook`.
  Inspect `root_source`, `root_initialized`, and any `root_warning` in
  `preflight` or `resolve` before writing.
- **Capture is rejected:** verify `write_intent: durable`,
  `content_kind: knowledge`, an allowed scope/kind combination, and
  evidence for `Current` knowledge. Use `Pending` only for a durable unresolved
  item.
- **A post-capture check has no scope:** treat a missing or invalid
  `health_scope` as an incomplete runner response. Do not retry with the default
  project scope.
- **Existing notes do not appear:** Tracebook does not discover or import an
  existing knowledge root. Existing material must remain untouched unless a
  separate, explicitly approved migration process is provided.
- **A link warning appears:** generated knowledge uses Markdown links; manual
  Wikilinks are audited as compatibility input but are not generated.

## Development and Release Verification

From a repository clone, run the focused integration test and the full suite:

```text
python -m unittest tests.test_runner_integration -v
python -m unittest discover -s tests -v
```

Validate the Skill package, compile Python sources, and check whitespace:

```text
python plugins/tracebook/skills/tracebook/scripts/validate_skill_package.py
python -m compileall -q plugins/tracebook/skills/tracebook/scripts tests
git diff --check
```

The repository CI runs the full suite and these static checks with Python 3.10
and 3.13 on Ubuntu and Windows. Linux exercises the symlink boundary cases that
may be skipped on Windows hosts without symlink privileges.

Before documenting or publishing a release, compare marketplace commands with
the current Codex and Claude Code CLI help, validate both language guides, and
publish the matching Git tag. The tagged Codex installation command above
resolves the published `v4.0.8` release.

## Stable Scope and Guarantees

Tracebook is complete for the local, evidence-backed project-memory workflow
documented here. The following boundaries are deliberate guarantees, not missing
runtime dependencies:

- Existing or unsupported knowledge roots are never upgraded, moved, merged, or
  imported automatically. Start a fresh installation with an empty configured
  root; any future migration remains an explicit, separately approved operation.
- No cloud sync, MCP server, vector database, daemon, or background service.
- No lifecycle Hooks. Automatic Skill selection remains host-dependent, but
  `$tracebook` can always be invoked explicitly.
- No automatic confirmation that a business statement or Deep-audit finding is
  true; evidence and human review remain authoritative.
- No business-repository installation or generated repository configuration.
- Release CI is configured for Python 3.10 and 3.13 on Ubuntu and Windows;
  environments outside that matrix are not claimed.
- Generated output uses Markdown links. Wikilinks are compatibility input for
  auditing and manual editing, not generated output.
- Deep candidate extraction scans every active durable Markdown page in the
  selected project, domain, or pattern scope and evaluates evidence or Pending
  state within each level-two knowledge entry. It remains heuristic: an empty
  candidate list does not prove that the knowledge is correct.

## Contributing

Keep changes narrow, evidence-backed, and consistent across the Skill, runner,
tests, and both README languages. Run the development and release verification
commands above before opening a pull request. Changes that add runtime
capabilities must update tests and must not weaken the external-root or
human-review boundaries.

## License

Apache-2.0. See [LICENSE](LICENSE).
