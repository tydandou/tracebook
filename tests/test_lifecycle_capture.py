from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import CaptureRequest, capture, resolve


class LifecycleCaptureTest(unittest.TestCase):
    def _request(self, **overrides: object) -> CaptureRequest:
        values: dict[str, object] = {
            "scope": "project",
            "kind": "decision",
            "category": "adr-0001",
            "title": "Persist idempotency keys first",
            "body": "Persist the message key before applying side effects.",
            "evidence": ("src/consumer.py:L20-L34",),
            "status": "Current",
            "write_intent": "durable",
            "content_kind": "knowledge",
        }
        values.update(overrides)
        return CaptureRequest(**values)

    def _context(self, base: Path):
        repo = base / "business"
        (repo / ".git").mkdir(parents=True)
        return resolve(base / "knowledge", repo)

    def test_high_value_documents_start_with_frontmatter(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))

            capture(context, self._request(), date(2026, 7, 13))
            capture(
                context,
                self._request(
                    scope="domain",
                    kind="domain",
                    category="settlement",
                    title="Settlement term",
                ),
                date(2026, 7, 13),
            )
            capture(
                context,
                self._request(
                    scope="pattern",
                    kind="pattern",
                    category="idempotency",
                    title="Idempotent consumer",
                ),
                date(2026, 7, 13),
            )

            project = context.root / context.record.relative_path
            decision = project / "decisions" / "adr-0001.md"
            domain = context.root / "02-domain" / "settlement.md"
            pattern = context.root / "03-patterns" / "idempotency.md"
            self.assertIn("type: decision", decision.read_text(encoding="utf-8"))
            self.assertIn("status: current", decision.read_text(encoding="utf-8"))
            self.assertIn("type: knowledge", domain.read_text(encoding="utf-8"))
            self.assertIn("scope: domain", domain.read_text(encoding="utf-8"))
            self.assertIn("type: pattern", pattern.read_text(encoding="utf-8"))

    def test_domain_and_pattern_entries_record_owner_project_identity(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))

            for scope, kind, category in (
                ("domain", "domain", "settlement"),
                ("pattern", "pattern", "idempotency"),
            ):
                with self.subTest(scope=scope):
                    capture(
                        context,
                        self._request(
                            scope=scope,
                            kind=kind,
                            category=category,
                            title=f"{scope.title()} owned entry",
                        ),
                        date(2026, 7, 13),
                    )
                    namespace = "02-domain" if scope == "domain" else "03-patterns"
                    content = (context.root / namespace / f"{category}.md").read_text(
                        encoding="utf-8"
                    )
                    self.assertIn(
                        f"Owner Project: `{context.record.identity}`",
                        content,
                    )

    def test_collection_frontmatter_stays_stable_across_entry_lifecycles(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            first_request = self._request(
                scope="domain",
                kind="domain",
                category="settlement",
                title="Settlement term",
            )
            capture(context, first_request, date(2026, 7, 13))
            page = context.root / "02-domain" / "settlement.md"
            before = page.read_text(encoding="utf-8")
            before_frontmatter = before.split("---", 2)[1]

            capture(
                context,
                self._request(
                    scope="domain",
                    kind="domain",
                    category="settlement",
                    title="Pending settlement exception",
                    body="The exception still requires service-owner confirmation.",
                    evidence=(),
                    status="Pending",
                ),
                date(2026, 7, 14),
            )

            after = page.read_text(encoding="utf-8")
            after_frontmatter = after.split("---", 2)[1]
            self.assertEqual(before_frontmatter, after_frontmatter)
            self.assertIn("status: current", after_frontmatter)
            self.assertIn("Status: Current", after)
            self.assertIn("Status: Pending", after)

    def test_decision_rejects_a_different_title_for_the_same_category(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            capture(context, self._request(), date(2026, 7, 13))
            page = (
                context.root
                / context.record.relative_path
                / "decisions"
                / "adr-0001.md"
            )
            before = page.read_text(encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "INVALID_REQUEST.*title"):
                capture(
                    context,
                    self._request(
                        title="Adopt a different decision",
                        body="This must not be appended to the existing entity.",
                    ),
                    date(2026, 7, 14),
                )

            self.assertEqual(before, page.read_text(encoding="utf-8"))

    def test_decision_update_keeps_one_entity_and_updates_lifecycle(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            first = capture(context, self._request(), date(2026, 7, 13))
            replacement = "decisions/adr-0002.md"
            updated_body = "Persist the key and outcome before acknowledging the message."

            second = capture(
                context,
                self._request(
                    body=updated_body,
                    status="Superseded",
                    replacement=replacement,
                ),
                date(2026, 7, 14),
            )

            page = (
                context.root
                / context.record.relative_path
                / "decisions"
                / "adr-0001.md"
            )
            content = page.read_text(encoding="utf-8")
            self.assertNotEqual(first.event_id, second.event_id)
            self.assertIn(self._request().body, content)
            self.assertIn(updated_body, content)
            self.assertIn("status: superseded", content.split("---", 2)[1])
            self.assertIn(f"Replacement: `{replacement}`", content)
            self.assertEqual([page], list(page.parent.glob("adr-0001.md")))

    def test_legacy_first_h2_is_the_entity_title(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            page = (
                context.root
                / context.record.relative_path
                / "decisions"
                / "adr-0001.md"
            )
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                "---\ntype: decision\nstatus: current\n---\n\n"
                "## Persist idempotency keys first\n\nLegacy decision body.\n",
                encoding="utf-8",
            )

            capture(
                context,
                self._request(body="A current update to the legacy decision."),
                date(2026, 7, 13),
            )
            with self.assertRaisesRegex(ValueError, "INVALID_REQUEST.*title"):
                capture(
                    context,
                    self._request(
                        title="Replace the legacy entity identity",
                        body="This title identifies a different entity.",
                    ),
                    date(2026, 7, 14),
                )

    def test_deprecated_knowledge_moves_to_archive_and_updates_index_link(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))

            result = capture(
                context,
                self._request(
                    kind="architecture",
                    category="architecture",
                    title="Retired topology",
                    status="Deprecated",
                ),
                date(2026, 7, 13),
            )

            project = context.root / context.record.relative_path
            archived = project / "archive" / "architecture.md"
            self.assertEqual(result.changed_paths[0], archived)
            self.assertTrue(archived.is_file())
            self.assertIn("Status: Deprecated", archived.read_text(encoding="utf-8"))
            self.assertIn("archive/architecture.md", (project / "index.md").read_text(encoding="utf-8"))

    def test_superseded_knowledge_requires_and_records_a_replacement(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))

            with self.assertRaisesRegex(ValueError, "replacement"):
                capture(
                    context,
                    self._request(status="Superseded"),
                    date(2026, 7, 13),
                )

            capture(
                context,
                self._request(
                    status="Superseded",
                    replacement="decisions/adr-0002.md",
                ),
                date(2026, 7, 13),
            )
            decision = context.root / context.record.relative_path / "decisions" / "adr-0001.md"
            self.assertIn("Replacement: `decisions/adr-0002.md`", decision.read_text(encoding="utf-8"))

    def test_superseded_replacement_must_remain_inside_the_knowledge_root(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))

            for replacement in (
                "../escape.md",
                "decisions/../../escape.md",
                "/absolute/escape.md",
                r"C:\absolute\escape.md",
                "C:escape.md",
                "ftp://host/replacement.md",
            ):
                with self.subTest(replacement=replacement):
                    with self.assertRaisesRegex(ValueError, "replacement"):
                        capture(
                            context,
                            self._request(
                                status="Superseded",
                                replacement=replacement,
                            ),
                            date(2026, 7, 13),
                        )

    def test_project_log_keeps_one_knowledge_heading(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))

            capture(context, self._request(), date(2026, 7, 13))
            capture(
                context,
                self._request(
                    kind="architecture",
                    category="architecture",
                    title="Service topology",
                ),
                date(2026, 7, 13),
            )

            log = context.root / context.record.relative_path / "logs" / "2026-07.md"
            self.assertEqual(log.read_text(encoding="utf-8").count("## Knowledge"), 1)


if __name__ == "__main__":
    unittest.main()
