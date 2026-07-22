# v3.1.0 End-to-End Test Findings

## F-001: New-project reference reading has no read-only command

Status: Confirmed, fixed in this release.

### Reproduction

1. Register an existing source project in an isolated knowledge root.
2. Run `preflight` for a not-yet-created target directory.
3. Attempt to retrieve the source project's `reference` profile without
   resolving or registering the target.

The integration test initially failed because the runner exposed only
`context`, which requires `--cwd` and resolves that path before retrieval.
Using it for the new target would register the target and violate the
read-only preflight contract.

### Root cause

The runner conflated active-project activation (`resolve`) with read-only
authority-page retrieval. Existing-project work needs both; new-project
architecture research needs only the latter.

### Resolution

Add `context-read`, a command that accepts explicitly registered project IDs
and performs bounded retrieval without `--cwd`, initialization, transaction
recovery, project registration, or target-directory creation. Preserve the
source project in the response and retain the existing `context` command for
active-project work.

## F-002: Context returns unrelated Current entries

Status: Confirmed, fixed in this release.

### Reproduction

1. Capture one architecture entry and one source-map entry in a source project.
2. Query the source with the `reference` profile for a token that occurs only
   in the source-map entry.
3. The profile correctly excludes the source map, but previously returned the
   unrelated architecture entry with its Current-status base score.

### Root cause

The ranker grants Current entries a base score of 10. The selection loop did
not require any query-derived score, so every Current candidate survived even
when title, evidence, and body had no token overlap with the query.

### Resolution

Keep lifecycle status as a ranking preference, but require a candidate to
exceed its lifecycle-only base score before returning it. A query with no
matching authority page now returns the intended structured empty context.
