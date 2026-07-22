# Schema-v2 Frontmatter Rules

Every runner-managed knowledge entity has schema-v2 frontmatter:

```yaml
---
schema_version: 2
type: business-rule
scope: project
project: github.com/acme/order-service
knowledge_id: order-retry-idempotency
title: Order retry idempotency
status: current
version: 3
created: 2026-07-01
updated: 2026-07-22
replacement_knowledge_id: null
---
```

`knowledge_id` is immutable and must be a lowercase-hyphenated slug. `version`
is incremented only by a successful `revise` or `change-status`. Valid status
values are `current`, `pending`, `deprecated`, and `superseded`. A superseded
entity names an existing active replacement ID. Do not hand-edit these fields;
use the Runner so frontmatter, Current content, History, index, status, and
event markers remain one transaction.
