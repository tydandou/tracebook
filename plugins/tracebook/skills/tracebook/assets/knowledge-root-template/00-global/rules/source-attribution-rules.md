# Source Attribution Rules

The knowledge base is not the primary fact source. Prefer source code, raw
material, API definitions, database migrations, and test results.

Add sources whenever practical for numbers, percentages, enums, API fields,
database fields, business conditions, core rules, architecture conclusions,
and bug root causes. Prefer source references such as:

```text
path/to/file.ext:L20-L38
```

If a source cannot be verified, mark the conclusion `Pending`. Do not rewrite
numeric values, enums, field names, or AI inferences as confirmed facts.
