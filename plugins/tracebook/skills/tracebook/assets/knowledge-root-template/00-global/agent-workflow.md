# Agent Knowledge Workflow

Before a business task, preflight a new or uncertain target; once development
starts, resolve the project and run deterministic `context` retrieval with the
task wording. The active project is the default boundary. Select another
project or a registered system only when the request explicitly requires it.
After a business task, decide whether
verified durable knowledge was learned. Create a new schema-v2 `knowledge_id`
only for a new conclusion; otherwise revise the existing entity with its
expected version.

After every write, perform a local self-check:

1. Confirm the destination directory is correct.
2. Update an entry index when required.
3. Confirm key facts have a source or `Pending` marker.
4. Confirm no obvious orphan document was created.

Run Light, Regular, or Deep health checks only under the trigger conditions in
`00-global/health/health-check-rules.md`.
