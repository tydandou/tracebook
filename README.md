# Tracebook

Tracebook is a Codex Plugin that bundles a reusable Skill for durable, traceable project knowledge. It keeps
business terminology, rules, architecture, code paths, incident conclusions,
and verified engineering decisions in an external Markdown knowledge root.

It preserves a governed external-knowledge workflow: layered project/domain/pattern
knowledge, source attribution, lifecycle labels, indexes, status summaries,
logs, synthesis pages, and health checks.

## Install

Tracebook uses one shared Skill package and supplies native marketplace metadata
for both Codex and Claude Code.

### Codex

```text
codex plugin marketplace add <github-owner>/tracebook --ref v1.0.0
codex plugin add tracebook@tracebook
```

### Claude Code

```text
claude plugin marketplace add <github-owner>/tracebook#v1.0.0
claude plugin install tracebook@tracebook
```

Replace `<github-owner>` with the repository owner. Start a new Codex session
or run `/reload-plugins` in Claude Code after installation. During Claude
Plugin development, load the local directory directly:

```text
claude --plugin-dir ./plugins/tracebook
```

For another agent that reads Open Agent Skills directly, copy
`plugins/tracebook/skills/tracebook/` into that agent's global Skill directory.

## Quick Start

1. Install the Plugin, then work in any Git repository as usual.
2. Ask Codex to use Tracebook for a coding, debugging, analysis, or design task
   that needs durable project context.
3. On first use, the Skill creates the external knowledge root, resolves the
   repository identity, and reads only the returned context paths.
4. After verified work, it captures only durable conclusions and reports the
   knowledge changes and health result.

No repository setup, project-level `AGENTS.md`, service process, API key, or
vector database is required. To store knowledge somewhere other than the
standard local root, set `TRACEBOOK_ROOT` before starting Codex.

```powershell
$env:TRACEBOOK_ROOT = (Join-Path $HOME "team-knowledge")
```


## What It Creates

On first use, Tracebook creates a local external knowledge root:

```text
~/.tracebook/
```

The root contains the same global rules, project directories, domain knowledge,
engineering patterns, raw-material area, archive, indexes, lifecycle rules,
and health-check rules as the Tracebook design.

Tracebook identifies Git projects by normalized `origin` remote. Multiple
clones of the same repository share one knowledge directory. A local-only
repository uses a stable absolute-path fallback identity.

Set `TRACEBOOK_ROOT` to use a different local knowledge root; otherwise
Tracebook uses `~/.tracebook`.

## Privacy and Repository Boundaries

- Tracebook stores knowledge locally in its configured root (`~/.tracebook` by default).
- It does not require an API key, cloud service, vector database, daemon, MCP
  server, or hook.
- It does not modify business repositories to install or operate.
- It does not create project-level `AGENTS.md` files.
- It does not automatically discover, copy, import, or modify
  an existing external knowledge root.

Existing external knowledge is **not imported automatically**. A
future migration feature must be explicitly requested, start with a dry-run,
copy rather than move source files, and provide a rollback manifest.

## Link Policy

Markdown links are the canonical output format. Tracebook templates and runner
writes use standard `[label](path)` links so generated knowledge remains
portable across Markdown, Git, Codex, Claude Code, and Obsidian.

Wikilinks are accepted as compatibility input for imported knowledge and
manual Obsidian editing. Health checks audit both link formats, but the runner
does not generate Wikilinks.
## Knowledge Capture Policy

Tracebook reads focused project context before engineering work. After a task,
it writes only verified durable knowledge, such as business rules, terminology,
module relations, architecture changes, code paths, API/database changes, bug
root causes, verification conclusions, important risks, and reusable patterns.

It does not write after pure log analysis, temporary Q&A, unverified inference,
or when the user prohibits a write. Critical facts include a source reference
or are marked `Pending`.

## Daily Workflow

For normal use, invoke the Skill through Codex; the Skill decides whether the
current task needs knowledge and uses the runner for deterministic operations.
The workflow is:

1. `resolve` initializes or repairs the external root, identifies the current
   Git project, and returns the small ordered set of context files to read.
2. The agent reads that context and performs the engineering task in the
   business repository.
3. After evidence-backed work, `capture` routes a durable item to the governed
   project, domain, or pattern document and updates its indexes and status.
4. `check` performs the applicable local, Light, or Regular health check.
   When it requests a Deep check, run `audit`; its findings remain candidates
   until a person verifies them.

The runner is also available for integrations and diagnosis. Set `SKILL_DIR` to
this installed Skill directory and run these PowerShell examples from a Git
repository:

```powershell
python "$SKILL_DIR/scripts/tracebook_runner.py" resolve --cwd "$PWD"
python "$SKILL_DIR/scripts/tracebook_runner.py" capture --cwd "$PWD" --request .\capture-request.json
python "$SKILL_DIR/scripts/tracebook_runner.py" check --cwd "$PWD" --changed <knowledge-page>
python "$SKILL_DIR/scripts/tracebook_runner.py" audit --cwd "$PWD"
```

All commands emit structured JSON. `capture` requests must follow the governed
contract in [SKILL.md](plugins/tracebook/skills/tracebook/SKILL.md): durable intent, knowledge content, an allowed
scope and kind, and evidence for `Current` facts. Pass `--root` only to override
`TRACEBOOK_ROOT` for that command.


## Development

Run the local test suite from the repository root:

```text
python -m unittest discover -s tests -v
```

Validate the Skill package before publishing:

```text
python plugins/tracebook/skills/tracebook/scripts/validate_skill_package.py
```

Before creating a release tag, also compile the scripts and run a whitespace check:

```text
python -m compileall -q plugins/tracebook/skills/tracebook/scripts tests
git diff --check
```

## License

Apache-2.0. See [LICENSE](LICENSE).
