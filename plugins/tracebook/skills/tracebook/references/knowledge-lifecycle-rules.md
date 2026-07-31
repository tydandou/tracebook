# Knowledge Lifecycle Rules

An authority page has exactly one current version and an append-only History.
`create` writes version 1. `revise` and `change-status` require
`expected_version`; a mismatch is a visible conflict, not a merge invitation.
The old Current section is retained under `## History` and the new content is
written under `## Current`.

## When to Revise

A revise needs a material change to the durable entity: its conclusion,
governed evidence, title, or lifecycle facts. Replace evidence when a source
moves or becomes obsolete, when a health finding is resolved, or when new
evidence materially changes the support for the conclusion. Do not create a
version for formatting-only edits or incidental investigation notes. When new
information is an independent architecture fact, entry-point inventory, or
reusable pattern, give that fact its own entity instead.

A direction that has not been authorized for implementation is not a current
fact. Keep it out of the main entity's Current section: record it as its own
entity with `status: pending`, then `change-status` to `deprecated` when it is
abandoned. Written as the main entity's Current, it produces an extra version
as soon as it is overturned, and the History then holds a proposal that never
described the system.

A superseded approach is worth keeping once it is recorded correctly: the
reason a direction failed — a runtime error, an unmet dependency, a missing
platform capability — is what stops the same dead end from being proposed
again. State that reason in the entity that replaces it, not only in History.

Default retrieval returns only `current` entities. `pending`, `deprecated`,
and `superseded` are excluded unless explicitly requested or historical
context is requested. Use `--include-history` or `--as-of` when the task is
specifically about prior reasoning or behavior.

## Collections and the Supersede Constraint

A `superseded` entity must name an existing `current` replacement in its own
collection. `pending`, `deprecated`, and `superseded` entities cannot replace a
confirmed fact. A replacement pointer is invalid on every other status. A
collection is the directory the entity is stored in, and that
directory differs by scope:

- project scope stores entities under `knowledge/<kind>/`, so the collection is
  one kind. A project entity can only be superseded by an entity of the **same
  kind**.
- domain and pattern scope store entities in one flat `knowledge/` directory per
  scope, with `kind` kept as metadata rather than as a path segment. Any kind in
  the same scope qualifies.

That asymmetry follows from the path layout, not from a rule about what may
replace what. Do not rely on it as a modelling guide.

When the intended successor is a different project kind, supersession is
usually the wrong operation: a successor of another kind is generally a
different fact, not a new version of the same one. Use `change-status` to
`deprecated`, which needs no replacement pointer, and let the new entity stand
on its own. Reach for `superseded` only when one entity genuinely continues
another's role.
