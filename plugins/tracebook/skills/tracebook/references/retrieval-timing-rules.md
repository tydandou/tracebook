# Retrieval Timing Rules

The opening read is not the only retrieval. Query again whenever the work
produces a **new retrieval key** — a concrete identifier that knowledge could
plausibly be filed under: a repository-relative file path, a class or function
name, a `knowledge_id`, a table name, an error code, a configuration key.

## Judgement, not a quota

A new key is the usual trigger, not the only one: query whenever you judge it
useful. Two facts to decide with:

Retrieval is deterministic — token overlap scoring, a fixed ranking order, and an
immutable snapshot — so the same key against the same snapshot returns a
byte-identical result. Re-querying an unchanged key therefore tends to add
nothing, unless this task has captured knowledge since, which moves the snapshot.

A single query is a local file scan: no network, no embedding, no index. The
adaptive opening reads Current first and scans History only after zero eligible
Current matches, keeping the common path bounded while recovering an old term.

Routine work with no durable question — a typo fix, a single test run, a pure
language question — normally needs none.

## Insufficient evidence and bounded follow-up

Zero results, truncated results, omitted warnings, an incomplete decisive excerpt,
or competing applicable conclusions require attention before answering. An empty
query result means no match for that key, not that no relevant knowledge exists.

- Use paths, IDs or terms obtained from source/index navigation for a targeted
  follow-up; whole English words and CJK bigrams do not imply synonyms, stemming
  or translation. Do not manufacture a business synonym dictionary.
- The adaptive opening already retries History after zero Current matches. If a
  previous name or rule may have disappeared from Current, or the task asks for
  versions, changes, regressions, commits, or rationale, explicitly use profile
  audit. A History hit discovers an eligible entity; read its selected
  version, not the historical match as today's fact. Preserve project/kind/status
  filters. Never automatically search all projects or resurrect retired entities.
- Read a few decisive entities with knowledge-id and full-content. If read_snapshots
  or versions changed between queries, reassess using the new complete version;
  do not splice incompatible read generations into one claimed fact.
- Normally allow at most two targeted discovery follow-ups after the opening
  query, with an aggregate 100,000-character result-content budget including
  decisive full reads. A task explicitly requiring deeper historical analysis
  can justify a stated larger budget. Stop earlier when evidence is sufficient
  or no new key remains; repeated state changes or exhausted budgets are disclosed
  limitations, not reasons for unlimited retries.

Before adopting a conclusion, verify applicability and evidence. Recency only
breaks score ties; neither the first result nor entity status proves business
truth. Revise the existing ID for a changed fact; use a separate successor and
change-status only for a verified replacement, never merely because it is newer.

## Examples, not a quota

- A stack trace or backend log resolves to a set of source files: reverse-query
  them with `--evidence-path` (see below).
- Reading code surfaces an unfamiliar module, class, or function name: query
  that identifier. This is when prior knowledge is most likely to exist and
  least likely to be remembered.
- Before a `capture`: query the target `knowledge_id` to learn whether the
  entity exists and at which `version`, instead of discovering it through an
  `INVALID_REQUEST: expected_version conflicts` round trip.

## Reverse lookup from a log or stack trace

A user-supplied log is analysis input, not knowledge and not something to store.
The order matters, because the retrieval keys do not exist until step 2 is done:

1. Read the log the user provided. Identify the failing behavior.
2. Resolve it to concrete source files in the current repository.
3. Reverse-query those files: `context-read-path --evidence-path <path>`,
   repeating the flag per file. Only entities listing a file as formal `Current`
   evidence are marked `evidence_match: true`. Without `--query` the result set
   holds those matches only; adding `--query` also returns query hits marked
   `evidence_match: false`, so filter on that field for the reverse set alone.
4. Only then conclude a root cause.

Step 3 happens after the opening read, mid-task. Skipping it because "the read
phase already ran" wastes the one retrieval that is most specific to the defect.

## Stored knowledge is a prior, not the truth

In defect analysis the evidence in hand outranks the knowledge base. A bug often
means recorded behavior no longer holds, so a retrieved conclusion may be stale.

When a retrieved conclusion contradicts the log or the current source, the
contradiction is itself the finding. Resolve which of the two it is and say so:

- the knowledge is outdated and its entity needs a `revise`; or
- the code regressed against documented behavior, which is the defect.

Never silently prefer the stored conclusion over observed evidence, and never
discard the stored conclusion without stating that it conflicts.
