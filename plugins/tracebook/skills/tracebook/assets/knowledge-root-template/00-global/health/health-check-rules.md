# Knowledge Health Check Rules

## Trigger Conditions

Perform a local self-check after every knowledge write. Run a Light check when
a task ends with a knowledge change, a Markdown page is added, an index, source
map, project status, global rule, or global health file changes, three or more
knowledge files change, or a user requests a check.

Run a Regular check when any condition holds:

- More than seven days since the last Regular check.
- Ten or more changes since the last Regular check.
- Five or more new pages since the last Regular check.
- Ten or more pending confirmations.
- Ten or more missing sources.

Run a Deep check when any condition holds:

- More than 30 days since the last Deep check.
- A large change to business rules, source maps, APIs, or database knowledge.
- A user explicitly requests a Deep check.

## Check Scope

Light checks validate references for new documents, sources for key facts,
links, source-map paths, project-status updates, and schema-v2 entity
integrity: authority uniqueness, continuous versions, event markers, Current
evidence, and active replacement IDs.

Regular checks cover broken links, orphan pages, missing sources, outdated
source maps, long-pending confirmations, duplicate pages, and log growth.

Deep checks sample important rules against source or raw evidence, validate
numbers, enums, interfaces, database and API documentation, review root-cause
evidence, find pages that cite unsourced conclusions, and compare project
status against recent logs.

Health checks never modify business code. Update `health-status.md` only after
an actual Light, Regular, or Deep check. Write high-risk open issues there and
put detailed health history in `00-global/health/logs/YYYY-MM.md`.

## Output Format

```markdown
## Knowledge Health Check

### Check Type

Light / Regular / Deep

### Trigger Reason

- ...

### Broken Links

- ...

### Orphan Pages

- ...

### Missing Sources

- ...

### Possible Drift

- ...

### Recommended Fixes

- ...

### Need Human Review

- ...
```
