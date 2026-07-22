# Reading Rules

For repository work, first resolve the external root and read only its minimal
ordered context: root rules, global health, project index, and project status.
Then run the Runner's deterministic `context` command with the task wording.
Read only the returned authority pages that are relevant to the work.

`context` returns Current results by default, ordered deterministically by
stable ID, title, evidence/source-path, and body matches. Use
`--include-history` only for historical questions and `--as-of YYYY-MM-DD` to
reconstruct a prior state. Do not load logs, archives, raw files, or every
knowledge page by default. If structured context fails, say so and fall back
to index navigation; do not claim a search was completed.
