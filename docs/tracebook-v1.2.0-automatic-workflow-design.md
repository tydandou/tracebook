# Tracebook v1.2.0 Automatic Workflow Design

## Problem

Tracebook v1.1.1 already requires an engineering task to evaluate a durable
write gate, but that requirement lives in the Skill body. Codex sees the body
only after selecting the Skill. The previous metadata made selection depend on
first deciding that the task needed durable project knowledge, so ordinary
repository analysis, debugging, review, implementation, testing, build, and
release work could bypass the workflow entirely.

Static tests also checked only that gate-related sentences existed. They did
not cover realistic trigger prompts or plugin lifecycle behavior.

## Goals

- Make Tracebook an implicit default for nontrivial software-repository work.
- Load only the minimal external context before engineering work.
- Keep durable writes conditional, evidence-backed, and user-controllable.
- Require every selected workflow to report either a checked capture or one
  controlled skip reason.
- Add lifecycle reminders without modifying business repositories or
  automatically writing knowledge.
- Preserve all v1.1.1 knowledge roots and runner contracts.

## Non-goals

- Capturing every code change, passing test, log, or conversation.
- Treating raw logs or AI inference as durable facts.
- Parsing Codex transcripts, which are not a stable Hook interface.
- Supporting project resolution outside Git repositories. A local-path
  identity remains available only for a Git repository without a remote.
- Making plugin Hooks an absolute enforcement boundary. Users must trust them,
  and they can be disabled unless managed by an administrator.

## Design

### 1. Skill discovery

The frontmatter description front-loads repository-task triggers: analysis,
debugging, review, code/configuration changes, tests, builds, deployments,
CI/CD, and incident diagnosis. `agents/openai.yaml` explicitly permits implicit
invocation and uses a matching default prompt.

General Q&A, non-project work, raw-log summaries, and explicit no-write
requests remain exclusions. An explicit no-write request suppresses capture;
it does not suppress read-only context loading when that context is relevant.

### 2. Read and write separation

For a qualifying repository task, Tracebook resolves the project and reads the
small ordered context set before nontrivial work. Reading is the default.

Writing occurs only when all four conditions are true:

1. the conclusion is new or materially changed;
2. evidence verifies it;
3. it remains useful after the conversation;
4. it has a governed Tracebook destination.

Otherwise the final report uses one controlled reason:
`not-project-work`, `no-durable-conclusion`, `unverified`, `already-known`, or
`user-disabled`.

Tests and logs are evidence. They are not durable knowledge by themselves. A
root cause supported by logs plus source, configuration, reproduction, or
another stable source may be captured; raw complete logs may not.

### 3. Plugin lifecycle reminders

The plugin bundles `hooks/hooks.json` using Codex's default plugin discovery.
No manifest override is required.

- `UserPromptSubmit` runs a small Python command. Inside a Git work tree it
  injects the default-read and final-gate contract. Outside Git it exits with
  no output.
- `Stop` emits a concise reminder to verify that the final response contains a
  capture/check result or controlled skip reason. It does not read the
  transcript, block completion, or request another turn, so it cannot create a
  Stop-loop.

The Hook never calls `resolve`, `capture`, `check`, or `audit`. All knowledge
mutations remain model-selected, explicit runner operations governed by the
Skill.

### 4. Failure and compatibility behavior

- Missing Git, malformed Hook input, subprocess errors, and timeouts fail open
  with no output. Hook failures must not break normal Codex work.
- Hook commands have POSIX and Windows forms and use `PLUGIN_ROOT` to locate
  the installed script.
- Existing knowledge roots, language configuration, lifecycle values, event
  identifiers, and generated paths are unchanged.
- Plugin Hooks require Codex trust review and may be disabled. In that case,
  the broader description and Skill gate provide the soft fallback.
- Claude Code and generic Open Agent Skills hosts continue to use the Skill;
  Codex-specific Hook behavior is an additive enhancement.

## Validation

- Unit-test Git and non-Git Hook behavior, both lifecycle events, malformed
  input, and the no-continuation invariant.
- Keep a positive/negative prompt matrix and assert that Skill metadata covers
  the intended trigger and exclusion vocabulary.
- Run the full unit suite, package validator, Skill Creator validator, Python
  compilation, JSON parsing, and `git diff --check`.
- Install the tagged marketplace release in a clean/new Codex session for the
  final behavioral check; Hook trust remains an explicit user action.

## Rollback

Revert the v1.2.0 commit or install tag `v1.1.1`. Removing `hooks/` and
restoring the previous Skill metadata fully disables the new behavior. No
knowledge-root migration or data rollback is required.
