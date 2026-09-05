# Reading Rules

For repository work, first preflight a new or uncertain target; once work on
an existing target starts, resolve the external root and read only its minimal
ordered context: root rules, global health, project index, and project status.
Then run the Runner's deterministic `context` command with the task wording.
Read only the returned authority pages that are relevant to the work.

`context` returns Current results by default, ordered deterministically by
stable ID, title, evidence/source-path, and body matches. Use
`--include-history` to attach history to already matched entities; use the explicit
`--profile audit` for history-based discovery, and `--as-of YYYY-MM-DD` to
reconstruct a prior state. Do not load logs, archives, raw files, or every
knowledge page by default. If structured context fails, say so and fall back
to index navigation; do not claim a search was completed.

The current project is the default search boundary. Select another project or
system only through the explicit cross-project reading rules.

Read the complete body and evidence of decisive entities with `--knowledge-id
<id> --full-content` (add `--kind` when needed). The body comes from the same read
snapshot as its version and evidence, not a separately read mutable authority.
For domain/pattern or an explicit legacy fallback, full-content uses the same
single authority-page read as its metadata; no project-snapshot guarantee is
added to those scopes. read_snapshots describes selected projects only.
If the complete item cannot fit, it is omitted with a truncation signal; increase
the budget deliberately or disclose the gap. Without full-content, excerpt is
only a deterministic 500-character prefix; excerpt_truncated is independent of
result-set truncated. Historical version state is not entity lifecycle status.

max-results limits entities in current_context, including as-of selected entities;
returned_count also includes attached historical versions. max-chars covers the
compact JSON contents of current_context, historical_context, warnings,
omitted_entities and history_omitted_entities, including item separators but not
array brackets, fixed envelope, request echoes or selected-project provenance.
budget_chars_used reports that sum. Omission samples have at most 10 entities;
counts remain complete. history_available is null when history_inspected is false.
