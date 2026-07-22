# Directory Rules

## Global Rules and Health

`00-global` contains shared agent workflow, rules, and health-check policy.

## Project Knowledge

The resolver-provided `01-projects/{readable-name--id-suffix}` directory contains project-specific durable knowledge. Its
minimum files are `index.md` and `project-status.md`. Create files on demand:

```text
product.md
architecture.md
modules.md
source-map.md or source-map/
business-rules.md or business-rules/
terminology.md
api.md or api/
database.md or database/
synthesis/
decisions/
logs/
archive/
```

Never create `AGENTS.md` inside a project knowledge directory.

## Cross-Project Knowledge

`02-domain` holds reusable business rules, terminology, processes, and
industry references. `03-patterns` holds reusable agent workflows, RAG,
frontend, backend, and operations patterns. Keep single-project facts in the
project directory.

`04-systems` records explicit multi-project system membership and directed
service relationships. It selects a bounded cross-project read scope; it does
not merge project identity or make all projects default context.

## Raw and Archive

`raw` contains unstructured source material pending processing. `99-archive`
contains deprecated designs and historical material. Do not use either as
default task context.
