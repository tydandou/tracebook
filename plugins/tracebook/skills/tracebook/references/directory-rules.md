# Directory Rules

Use `00-global` for shared workflow, governance rules, and health policy.

Put project-specific knowledge under the resolver-provided `01-projects/{readable-name--id-suffix}` path. Keep
`index.md` and `project-status.md` as the minimum project documents. Create
architecture, product, modules, terminology, business rules, source maps,
API, database, decisions, synthesis, logs, and archive documents only when
they have durable content.

Put cross-project business rules, terminology, processes, and industry
references under `02-domain`. Put cross-project technical patterns under
`03-patterns`. Use `raw` only for original material awaiting organization and
`99-archive` for historical material. Do not create an `AGENTS.md` in a
project knowledge directory.

Use `04-systems` only for explicit system membership and directed service
relationships. A system is not a replacement for project identity: one project
may belong to several systems, and the relation graph selects read scope rather
than merging project knowledge.
