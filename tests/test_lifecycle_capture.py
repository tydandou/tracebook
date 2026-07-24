from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.capture import CaptureRequest
from plugins.tracebook.skills.tracebook.scripts.tracebook_runner import capture, resolve


class LifecycleCaptureTest(unittest.TestCase):
    """Schema-v2 entity lifecycle: change-status and superseded transitions."""

    def _request(self, **overrides: object) -> CaptureRequest:
        values: dict[str, object] = {
            "operation": "create",
            "scope": "project",
            "kind": "decision",
            "category": "decision",
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

    def test_supersede_records_active_replacement_slug(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            # Successor entity in the same collection must exist and be active.
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

            for replacement, message in (
                ("does-not-exist", "replacement_knowledge_id"),
                ("persist-idempotency-keys", "replacement_knowledge_id"),
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
