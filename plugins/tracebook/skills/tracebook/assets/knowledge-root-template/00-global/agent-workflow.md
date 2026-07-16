# Agent Knowledge Workflow

After a business task, decide whether verified durable knowledge was learned.
When it was, write it according to the writing, attribution, index,
lifecycle, log, and frontmatter rules.

After every write, perform a local self-check:

1. Confirm the destination directory is correct.
2. Update an entry index when required.
3. Confirm key facts have a source or `Pending` marker.
4. Confirm no obvious orphan document was created.

Run Light, Regular, or Deep health checks only under the trigger conditions in
`00-global/health/health-check-rules.md`.
