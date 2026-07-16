# Directory Rules

Use `00-global` for shared workflow, governance rules, and health policy.

Put project-specific knowledge under `01-projects/{project-name}`. Keep
`index.md` and `project-status.md` as the minimum project documents. Create
architecture, product, modules, terminology, business rules, source maps,
API, database, decisions, synthesis, logs, and archive documents only when
they have durable content.

Put cross-project business rules, terminology, processes, and industry
references under `02-domain`. Put cross-project technical patterns under
`03-patterns`. Use `raw` only for original material awaiting organization and
`99-archive` for historical material. Do not create an `AGENTS.md` in a
project knowledge directory.
