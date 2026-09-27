# Cross-Project Reading Rules

Start in the active project. Explicit user selection remains valid; feature
work and debugging can also reveal a necessary provider without the user naming
it. Read that provider when an interface, service, or shared contract affects
the task, or when its evidence can fill a specific gap in the execution chain.
Do not wait for zero local matches when the task already requires that contract.

Before expanding, identify the missing fact and the project that can supply it.
Use `preflight` relations as navigation, checked against source, configuration,
logs, or verified knowledge. A relation is not proof of relevance or permission;
a service address in an unrelated hit is not proof of ownership or failure.
If local retrieval is empty and no provider is yet known, use the concrete task
key to inspect the plausible direct relations within the permitted scope. Do
not turn a zero result into an all-project search.

Use `project-search` when the stable ID is unknown. Resolve ambiguous names or
ownership before reading; if the evidence cannot resolve them, ask for the
missing identity or scope. A confirmed dependency within the permitted task
scope needs no repeated confirmation. Do not register a project just to read it.
Use repeated `context-read --project-id` arguments for the selected projects,
with a concrete interface name, error code, configuration key, or other task key.
An explicit source or provider mapping can identify a registered project even
without a system relation; reading it does not create a persistent relation.

Read the relevant contract or execution segment, not the provider's entire
architecture. A successful call to one provider does not establish that another
provider failed; verify the actual failing step. Follow a further dependency
only when a new task-relevant gap requires it, within the same permitted scope
and the shared limits in [retrieval timing rules](retrieval-timing-rules.md).
Do not restart the budget for each project or automatically traverse a system.
Stop when the task has sufficient verified context. If a gap remains, state
what was checked and what evidence or scope is missing.

Every returned cross-project item must retain its source project identity. A
fact about another service is not a fact about the active project. Do not copy
it into the active project merely because it was read there.

For a new project, run `preflight` before creating target files. If the user
asks to borrow an architecture, require an explicit source project and use the
`reference` profile. That profile may load architecture, module, and decision
knowledge, but excludes source maps, incidents, logs, and ordinary changes.

Register shared-contract participants as a named system relationship instead
of silently duplicating the fact between services. The current capture model
keeps the authority in its owning project, domain, or pattern scope; retain
that owner and its evidence in every answer.

## Creating a Relation

Registering a relation is a write, so it has its own gate — the rules above
govern reading only. Create one when all three hold: both projects are already
registered, the link is a stable delivery dependency rather than a passing
reference, and the direction and kind are unambiguous from the task. Capturing
durable knowledge into both projects during one task is the strongest evidence
of the second condition; a `system_relation_candidate` in a `check` report is a
prompt to evaluate it, not proof on its own.

Nothing in the engine infers a relation. Neither adjacent directories, nor a
shared external knowledge root, nor one document naming another repository
creates one, because a wrong relation is a lasting structural claim about the
knowledge base — it is safer to leave two projects unrelated than to assert a
dependency that does not hold. When the three conditions are not all met, make
no relation and do not ask.
