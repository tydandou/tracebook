# Health Check Rules

Perform a local self-check after every knowledge write. Run Light checks for a
knowledge write, a new Markdown page, an index/source-map/status/global-rule
change, three or more changed knowledge files, or user request.

Run Regular checks after seven days, ten changes, five pages, ten pending
confirmations, or ten missing sources. Run Deep checks after 30 days, large
business-rule/source-map/API/database changes, or user request.

Light checks cover links, index references, sources, code paths, and status.
Regular checks cover links, orphans, sources, drift, duplicates, pending items,
and logs. Deep checks sample durable conclusions against their evidence. Health
checks never modify business code.
