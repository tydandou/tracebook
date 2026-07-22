# Knowledge Lifecycle Rules

Use these labels for durable knowledge:

- `Current`: valid task evidence.
- `Pending`: insufficiently sourced or unverified.
- `Deprecated`: explicitly no longer applicable.
- `Superseded`: replaced by a newer rule, document, or implementation.

Pending information must remain marked. Superseded information identifies an
existing active replacement ID. Each entity has one Current section and an
append-only History: create writes version 1; revise and status changes require
the prior `expected_version`. Prefer sourced Current authority pages; use
`--include-history` or `--as-of` only for traceability questions.
