from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.capture import CaptureRequest
from plugins.tracebook.skills.tracebook.scripts.check_knowledge import run_check
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import capture, resolve


class LifecycleCaptureTest(unittest.TestCase):
    """Schema-v2 entity lifecycle: change-status and superseded transitions."""

    def _request(self, **overrides: object) -> CaptureRequest:
        values: dict[str, object] = {
            "operation": "create",
            "scope": "project",
            "kind": "decision",
            "knowledge_id": "persist-idempotency-keys",
            "title": "Persist idempotency keys first",
            "body": "Persist the message key before applying side effects.",
            "evidence": ("src/consumer.py:L20-L34",),
            "status": "current",
            "write_intent": "durable",
            "content_kind": "knowledge",
        }
        values.update(overrides)
        return CaptureRequest(**values)

    def _context(self, base: Path):
        repo = base / "business"
        (repo / ".git").mkdir(parents=True)
        return resolve(base / "knowledge", repo)

    def _authority(self, context, knowledge_id: str = "persist-idempotency-keys") -> Path:
        return (
            context.root
            / context.record.relative_path
            / "knowledge"
            / "decision"
            / f"{knowledge_id}.md"
        )

    def test_change_status_to_deprecated_bumps_version_and_frontmatter(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            capture(context, self._request(), date(2026, 7, 13))

            result = capture(
                context,
                self._request(
                    operation="change-status",
                    expected_version=1,
                    status="deprecated",
                ),
                date(2026, 7, 14),
            )

            self.assertFalse(result.skipped)
            content = self._authority(context).read_text(encoding="utf-8")
            frontmatter = content.split("---", 2)[1]
            self.assertIn("status: deprecated", frontmatter)
            self.assertIn("version: 2", frontmatter)
            self.assertIn("### Version 1 — 2026-07-13", content)

    def test_change_status_requires_matching_expected_version(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            capture(context, self._request(), date(2026, 7, 13))

            with self.assertRaisesRegex(ValueError, "expected_version"):
                capture(
                    context,
                    self._request(
                        operation="change-status",
                        expected_version=5,
                        status="deprecated",
                    ),
                        date(2026, 7, 14),
                    )

    def test_replacement_is_rejected_for_non_superseded_status(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            with self.assertRaisesRegex(
                ValueError, "allowed only for Superseded knowledge",
            ):
                capture(
                    context,
                    self._request(replacement_knowledge_id="unexpected-target"),
                    date(2026, 7, 13),
                )

    def test_supersede_records_current_replacement_slug(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            # The successor is resolved beside this entity, so for project scope
            # it must share its kind directory.
            capture(
                context,
                self._request(
                    knowledge_id="persist-key-and-outcome",
                    title="Persist key and outcome",
                    body="Persist the key and the outcome atomically.",
                ),
                date(2026, 7, 13),
            )
            capture(context, self._request(), date(2026, 7, 13))

            result = capture(
                context,
                self._request(
                    operation="change-status",
                    expected_version=1,
                    status="superseded",
                    replacement_knowledge_id="persist-key-and-outcome",
                ),
                date(2026, 7, 14),
            )

            self.assertFalse(result.skipped)
            frontmatter = self._authority(context).read_text(encoding="utf-8").split("---", 2)[1]
            self.assertIn("status: superseded", frontmatter)
            self.assertIn("replacement_knowledge_id: persist-key-and-outcome", frontmatter)

    def test_supersede_rejects_missing_or_self_replacement(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            capture(context, self._request(), date(2026, 7, 13))

            # Self-reference and a missing successor fail for different reasons;
            # a caller cannot act on the refusal if both read the same.
            for replacement, message in (
                ("does-not-exist", r"no `does-not-exist` in project scope kind `decision`"),
                ("persist-idempotency-keys", "must differ from knowledge_id"),
            ):
                with self.subTest(replacement=replacement):
                    with self.assertRaisesRegex(ValueError, message):
                        capture(
                            context,
                            self._request(
                                operation="change-status",
                                expected_version=1,
                                status="superseded",
                                replacement_knowledge_id=replacement,
                            ),
                            date(2026, 7, 14),
                        )

    def test_project_supersede_requires_the_successor_to_share_its_kind(self) -> None:
        """Project paths carry kind, so the successor is looked up in that directory.

        The refusal has to name the kind: a caller told only "same collection"
        cannot tell that the successor exists but sits one directory over.
        """
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            capture(context, self._request(
                kind="business-rule", knowledge_id="settlement-window",
                title="Settlement window",
                body="Settlement runs on the next business day.",
            ), date(2026, 7, 13))
            capture(context, self._request(), date(2026, 7, 13))

            with self.assertRaisesRegex(
                ValueError, r"no `settlement-window` in project scope kind `decision`",
            ):
                capture(context, self._request(
                    operation="change-status", expected_version=1,
                    status="superseded", replacement_knowledge_id="settlement-window",
                ), date(2026, 7, 14))

            # Unchanged: a rejected supersede leaves the entity current at v1.
            frontmatter = self._authority(context).read_text(encoding="utf-8").split("---", 2)[1]
            self.assertIn("status: current", frontmatter)
            self.assertIn("version: 1", frontmatter)

    def test_domain_supersede_accepts_a_successor_of_another_kind(self) -> None:
        """Domain and pattern paths carry no kind, so any kind in scope resolves.

        This asymmetry with project scope follows from the path layout. It is
        asserted here so a later change to either layout cannot alter one
        scope's behavior silently.
        """
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            capture(context, self._request(
                scope="domain", kind="business-rule", knowledge_id="refund-window",
                title="Refund window", body="Refunds close after 30 days.",
            ), date(2026, 7, 13))
            capture(context, self._request(
                scope="domain", kind="terminology", knowledge_id="refund-term",
                title="Refund terminology", body="A refund reverses a settled charge.",
            ), date(2026, 7, 13))

            result = capture(context, self._request(
                scope="domain", kind="terminology", knowledge_id="refund-term",
                operation="change-status", expected_version=1,
                status="superseded", replacement_knowledge_id="refund-window",
                title="Refund terminology", body="Folded into the refund window rule.",
            ), date(2026, 7, 14))

            self.assertFalse(result.skipped)
            page = context.root / "02-domain" / "knowledge" / "refund-term.md"
            frontmatter = page.read_text(encoding="utf-8").split("---", 2)[1]
            self.assertIn("status: superseded", frontmatter)
            self.assertIn("replacement_knowledge_id: refund-window", frontmatter)
            report = run_check(
                context.root,
                context.root / "02-domain",
                [page],
                date(2026, 7, 14),
            )
            self.assertFalse([
                issue for issue in report.entity_issues if "replacement" in issue
            ])

    def test_supersede_rejects_pending_replacement(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            capture(context, self._request(
                knowledge_id="proposed-successor",
                title="Proposed successor",
                body="This direction is not yet confirmed.",
                status="pending",
                evidence=(),
            ), date(2026, 7, 13))
            capture(context, self._request(), date(2026, 7, 13))

            with self.assertRaisesRegex(
                ValueError, "must reference Current knowledge; found pending",
            ):
                capture(context, self._request(
                    operation="change-status",
                    expected_version=1,
                    status="superseded",
                    replacement_knowledge_id="proposed-successor",
                ), date(2026, 7, 14))

    def test_supersede_rejects_non_authority_replacement(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            capture(context, self._request(), date(2026, 7, 13))
            fake = self._authority(context, "fake-successor")
            fake.write_text("---\nstatus: current\n---\n", encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError, "must reference a matching schema-v2 authority",
            ):
                capture(context, self._request(
                    operation="change-status",
                    expected_version=1,
                    status="superseded",
                    replacement_knowledge_id="fake-successor",
                ), date(2026, 7, 14))

    def test_rejected_supersede_create_does_not_create_collection(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            collection = (
                context.root / context.record.relative_path / "knowledge" / "api"
            )

            with self.assertRaisesRegex(ValueError, "no `missing-successor`"):
                capture(context, self._request(
                    operation="create",
                    kind="api",
                    knowledge_id="retired-api",
                    status="superseded",
                    replacement_knowledge_id="missing-successor",
                ), date(2026, 7, 14))

            self.assertFalse(collection.exists())

    def test_supersede_rejects_inactive_replacement(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            # Successor exists but is itself deprecated -> not an active target.
            capture(
                context,
                self._request(
                    knowledge_id="retired-successor",
                    title="Retired successor",
                ),
                date(2026, 7, 13),
            )
            capture(
                context,
                self._request(
                    knowledge_id="retired-successor",
                    title="Retired successor",
                    operation="change-status",
                    expected_version=1,
                    status="deprecated",
                ),
                date(2026, 7, 13),
            )
            capture(context, self._request(), date(2026, 7, 13))

            with self.assertRaisesRegex(ValueError, "replacement_knowledge_id"):
                capture(
                    context,
                    self._request(
                        operation="change-status",
                        expected_version=1,
                        status="superseded",
                        replacement_knowledge_id="retired-successor",
                    ),
                    date(2026, 7, 14),
                )


if __name__ == "__main__":
    unittest.main()
