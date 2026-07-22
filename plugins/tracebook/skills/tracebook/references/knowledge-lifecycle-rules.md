# Knowledge Lifecycle Rules

An authority page has exactly one current version and an append-only History.
`create` writes version 1. `revise` and `change-status` require
`expected_version`; a mismatch is a visible conflict, not a merge invitation.
The old Current section is retained under `## History` and the new content is
written under `## Current`.

Default retrieval returns only `current` entities. `pending`, `deprecated`,
and `superseded` are excluded unless explicitly requested or historical
context is requested. A `superseded` entity must refer to an existing active
replacement in its own collection. Use `--include-history` or `--as-of` when
the task is specifically about prior reasoning or behavior.
