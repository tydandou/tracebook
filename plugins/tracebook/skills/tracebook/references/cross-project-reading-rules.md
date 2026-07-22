# Cross-Project Reading Rules

Treat the active project as the default boundary. A different project becomes a
source only when the user names it, supplies its path or stable ID, or selects
a registered system that contains it. Do not search every project merely
because they share an external knowledge root.

Use `project-search` to present deterministic project candidates. A display
name can be ambiguous, so the selected `project_id` is the authority for a
cross-project read. Use a system only when its explicit membership and
relations describe the requested microservice set.

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
