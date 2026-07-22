# Health Check Rules

Run the required Light check after a successful capture. It checks links,
indexes, evidence, source paths, status, and schema-v2 entity integrity:
frontmatter, authority uniqueness, version continuity, event markers,
Current evidence, and valid active replacements. Checks report problems; they
never guess a repair or change business code.

Regular checks remain low-frequency and add duplicate, orphan, drift,
pending, and log-growth review. Deep audit remains an explicit manual command
for evidence sampling and major re-entry work; it is not a Hook gate. The
health report is a signal for human review, not proof of business truth.
