# Tracebook

[English](README.md) | [简体中文](README.zh-CN.md)

Tracebook is a local, durable knowledge layer for software work. Its Agent
Skill loads focused project context before a task and captures verified,
long-lived conclusions afterward, outside the business repository.

The repository provides native marketplace metadata for Codex and Claude Code,
and the same Skill package can be used by agents that support Open Agent
Skills. Natural-language use is the normal path; a deterministic JSON runner is
available for integrations, diagnosis, and advanced workflows.

## Why Tracebook

Important engineering context is easily scattered across conversations,
incidents, source files, and personal notes. Tracebook keeps that context in a
governed Markdown knowledge root with evidence, lifecycle status, indexes, and
health history. Agents can read only the relevant context, while people retain
an inspectable record of what was captured and why.

The knowledge root stays separate from business code. That separation lets
multiple business repositories use one local knowledge system without
installing files or services into those repositories.

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

## Install

The `3.2.0` release is prepared for the `v3.2.0` tag. After that tag is
published, use the tagged installation commands for the stable release, or use
the local development loading instructions when working from a clone.

### Codex

Install the tagged release:

```text
codex plugin marketplace add tydandou/tracebook --ref v3.2.0
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

`codex plugin remove` removes the installed plugin, not its knowledge root. If
`codex plugin add tracebook@tracebook` reports that the plugin was not found,
the `tracebook` marketplace source is absent from the active Codex profile.
Check it first:

```text
codex plugin marketplace list
```

If `tracebook` is absent, add the intended source before installing again:

```text
codex plugin marketplace add tydandou/tracebook --ref v3.2.0
codex plugin add tracebook@tracebook
```

If `tracebook` is already configured but must move to a different tagged
source, Codex requires replacing the marketplace before adding it again:

```text
codex plugin remove tracebook@tracebook
codex plugin marketplace remove tracebook
codex plugin marketplace add tydandou/tracebook --ref v3.2.0
codex plugin add tracebook@tracebook
```

For a local clone, update that clone and re-add it only when `tracebook` is
absent from the marketplace list:

```text
git pull --ff-only
codex plugin marketplace add .
codex plugin add tracebook@tracebook
```

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

### Open Agent Skills

The reusable package is
[`plugins/tracebook/skills/tracebook/`](plugins/tracebook/skills/tracebook/).
Copy that complete directory as `tracebook` into the Skill directory documented
by the target agent, then start a new session. Keep `SKILL.md`, `references/`,
`assets/`, and `scripts/` together.

By default, knowledge is stored at `~/.tracebook`. To select another external
root, set `TRACEBOOK_ROOT` before starting the agent. These examples read the
existing user-home value; they do not replace or assign `HOME`.

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
`recoverable`, `blocked`, `cleanup-ready`, or `invalid`, with structured issue
codes such as `TARGET_CHANGED`.

Use the explicit maintenance command only to roll forward transactions already
judged safe; it never discards, quarantines, or overwrites a changed target:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" recover-transactions \
  --root "$TRACEBOOK_ROOT"
```

### Capture

Save a request outside the business repository, for example in the system
temporary directory:

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

Then run:

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" capture \
  --root "$TRACEBOOK_ROOT" \
  --cwd . \
  --request "$REQUEST_FILE"
```

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
  --query "order retry duplicate charge" \
  --max-results 10 \
  --max-chars 20000
```

Default results contain only matching `current` authority pages. Add
`--include-history` for prior versions, or `--as-of YYYY-MM-DD` to reconstruct
what was current on a date. The JSON includes stable IDs, score, evidence,
status, update date, and a short summary; it is not a vector database or a
claim that the returned result is business truth.

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
| `resolve` | `root`, `project`, `read_paths` | Configured root, project record resolved by `project_id`, and focused context paths |
| `preflight` | `target`, `registered`, `project`, `read_paths` | Read-only target inspection; does not initialize or register |
| `project-search` | `projects` | Deterministic registered-project candidates |
| `context-read` | `current_context`, `historical_context`, `warnings`, `truncated` | Read selected registered projects without activating a target |
| `context-read-path` | `current_context`, `historical_context`, `warnings`, `truncated` | Lock-free read of an already activated target's committed project snapshot |
| `project-update` | `project` | Explicitly update a project name or complete location list |
| `project-bind-remote` | `project` | Bind a normalized remote to an existing project |
| `system-create` | `system` | Create an explicit multi-project system |
| `system-bind-project` | `system` | Add a registered project to a system |
| `system-relate` | `system` | Add a directed relationship between two system members |
| `transactions` | `root`, `transactions` | Read-only transaction diagnostics and per-transaction disposition |
| `recover-transactions` | `recovered_paths` | Explicit safe roll-forward results; never a discard or quarantine action |
| `context` | `current_context`, `historical_context`, `warnings`, `truncated` | Bounded deterministic authority-page retrieval |
| `capture` | `changed_paths`, `new_paths`, `skipped`, `health_scope`, `event_id` | Schema-v2 entity transaction result and scope required by the following check |
| `check` | `check_type`, `changed_paths`, `report` | Required health level, persisted health paths, and Markdown report |
| `audit` | `changed_paths`, `report` | Persisted Deep-health paths and Markdown audit report |

`event_id` identifies the idempotent capture event when one is available.
`skipped: true` means the capture made no new knowledge write. Consumers should
use fields only from the command that emitted them.

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
| Local | Reads and reports on the selected scope when no higher trigger applies; it does not write scope status or logs and does not rebuild the global aggregate. |
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
- **Capture is rejected:** verify `write_intent: durable`,
  `content_kind: knowledge`, an allowed scope/kind/category combination, and
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
resolves the published `v3.2.0` release.

## Current Limitations

- `3.2.0` retains schema-v2 authority pages and registry v2. Existing registry-v1
  knowledge roots are intentionally not migrated, imported, or mixed with the
  new format; point `TRACEBOOK_ROOT` at a new empty root for v3 work.

- Registry v1 is not upgraded automatically or mixed with the project-id
  registry. `resolve` reports an explicit upgrade requirement; existing
  knowledge pages are never moved or merged automatically.

- No migration, discovery, or automatic import of existing knowledge roots.
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
