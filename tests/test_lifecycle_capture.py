from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.check_knowledge import run_check
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

    @staticmethod
    def _knowledge_snapshot(root: Path) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if relative.parts and relative.parts[0] == ".tracebook-state":
                continue
            snapshot[relative.as_posix()] = path.read_bytes()
        return snapshot

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

    def test_next_capture_migrates_legacy_collection_status_to_current(self) -> None:
        for scope, kind, namespace, legacy_status in (
            ("domain", "domain", "02-domain", "unconfirmed"),
            ("pattern", "pattern", "03-patterns", "deprecated"),
        ):
            with self.subTest(scope=scope), TemporaryDirectory() as temp:
                context = self._context(Path(temp))
                page = context.root / namespace / "legacy-container.md"
                page.write_text(
                    "\n".join(
                        [
                            "---",
                            f"type: {'pattern' if scope == 'pattern' else 'knowledge'}",
                            f"status: {legacy_status}",
                            f"scope: {scope}",
                            "owner_project: legacy-owner",
                            "created: 2025-01-02",
                            "updated: 2025-02-03",
                            "custom_field: preserve-me",
                            "---",
                            "# Legacy collection",
                            "",
                            "Legacy collection body must remain byte-for-byte present.",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                capture(
                    context,
                    self._request(
                        scope=scope,
                        kind=kind,
                        category="legacy-container",
                        title="Pending managed entry",
                        body="This entry remains pending human confirmation.",
                        evidence=(),
                        status="Pending",
                    ),
                    date(2026, 7, 15),
                )

                content = page.read_text(encoding="utf-8")
                frontmatter = content.split("---", 2)[1]
                self.assertIn("status: current", frontmatter)
                self.assertNotIn(f"status: {legacy_status}", frontmatter)
                self.assertIn("owner_project: legacy-owner", frontmatter)
                self.assertIn("created: 2025-01-02", frontmatter)
                self.assertIn("updated: 2025-02-03", frontmatter)
                self.assertIn("custom_field: preserve-me", frontmatter)
                self.assertIn(
                    "Legacy collection body must remain byte-for-byte present.",
                    content,
                )
                self.assertIn("Status: Pending", content)

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

    def test_decision_archive_rejects_title_conflict_with_active_entity(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            capture(context, self._request(), date(2026, 7, 13))
            project = context.root / context.record.relative_path
            active = project / "decisions" / "adr-0001.md"
            archived = project / "archive" / "decisions" / "adr-0001.md"
            index = project / "index.md"
            active_before = active.read_text(encoding="utf-8")
            index_before = index.read_text(encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "INVALID_REQUEST.*title"):
                capture(
                    context,
                    self._request(
                        title="Archive a different decision",
                        body="This is not the entity identified by adr-0001.",
                        status="Deprecated",
                    ),
                    date(2026, 7, 14),
                )

            self.assertEqual(active_before, active.read_text(encoding="utf-8"))
            self.assertEqual(index_before, index.read_text(encoding="utf-8"))
            self.assertFalse(archived.exists())

    def test_same_title_deprecated_decision_keeps_archive_routing(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            capture(context, self._request(), date(2026, 7, 13))
            project = context.root / context.record.relative_path
            active = project / "decisions" / "adr-0001.md"

            result = capture(
                context,
                self._request(
                    body="This decision has been retired from active use.",
                    status="Deprecated",
                ),
                date(2026, 7, 14),
            )

            archived = project / "archive" / "decisions" / "adr-0001.md"
            self.assertIn(archived, result.changed_paths)
            self.assertTrue(archived.is_file())
            self.assertIn("Status: Deprecated", archived.read_text(encoding="utf-8"))
            self.assertIn(
                "<!-- tracebook:managed-pointer -->",
                active.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "archive/decisions/adr-0001.md",
                (project / "index.md").read_text(encoding="utf-8"),
            )

    def test_decision_transition_moves_history_and_leaves_managed_pointer(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            first = capture(context, self._request(), date(2026, 7, 13))
            project = context.root / context.record.relative_path
            active = project / "decisions" / "adr-0001.md"
            active.write_text(
                active.read_text(encoding="utf-8").replace(
                    "tags: []",
                    "custom_field: preserve-me\ntags: []",
                    1,
                ),
                encoding="utf-8",
            )
            retired_body = "This decision is retained as historical authority."

            second = capture(
                context,
                self._request(
                    body=retired_body,
                    status="Deprecated",
                ),
                date(2026, 7, 14),
            )

            archived = project / "archive" / "decisions" / "adr-0001.md"
            pointer = active.read_text(encoding="utf-8")
            authority = archived.read_text(encoding="utf-8")
            index = (project / "index.md").read_text(encoding="utf-8")
            self.assertIn("<!-- tracebook:managed-pointer -->", pointer)
            self.assertIn(
                "Managed Entity Authority: "
                "[adr-0001](../archive/decisions/adr-0001.md)",
                pointer,
            )
            self.assertNotIn("type: decision", pointer)
            self.assertNotRegex(pointer, r"(?m)^#{1,2} ")
            self.assertIn("Evidence:", pointer)

            self.assertIn("type: decision", authority)
            self.assertIn("status: deprecated", authority)
            self.assertIn("## Persist idempotency keys first", authority)
            self.assertIn("custom_field: preserve-me", authority)
            self.assertIn(self._request().body, authority)
            self.assertIn("- `src/consumer.py:L20-L34`", authority)
            self.assertIn(retired_body, authority)
            self.assertIn(
                "Managed Pointer: [adr-0001](../../decisions/adr-0001.md)",
                authority,
            )
            for event_id in (first.event_id, second.event_id):
                self.assertEqual(
                    1,
                    authority.count(f"<!-- tracebook:event:{event_id} -->"),
                )

            self.assertEqual(1, index.count("- [adr-0001]("))
            self.assertIn(
                "- [adr-0001](archive/decisions/adr-0001.md)",
                index,
            )
            self.assertNotIn("- [adr-0001](decisions/adr-0001.md)", index)

    def test_first_deprecated_decision_creates_only_archive_authority(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            project = context.root / context.record.relative_path

            result = capture(
                context,
                self._request(status="Deprecated"),
                date(2026, 7, 13),
            )

            active = project / "decisions" / "adr-0001.md"
            archived = project / "archive" / "decisions" / "adr-0001.md"
            self.assertFalse(active.exists())
            self.assertTrue(archived.is_file())
            self.assertNotIn(
                "tracebook:managed-pointer",
                archived.read_text(encoding="utf-8"),
            )
            self.assertEqual((archived,), result.new_paths)

    def test_entity_capture_rejects_dual_entities_and_corrupt_pointer(self) -> None:
        entity = (
            "---\ntype: decision\nstatus: current\n"
            "custom_field: preserve-me\n---\n\n"
            "## Persist idempotency keys first\n\n"
            "Legacy body.\n\nEvidence:\n- `src/consumer.py:L20-L34`\n"
        )
        for scenario in ("dual-entity", "corrupt-pointer"):
            with self.subTest(scenario=scenario), TemporaryDirectory() as temp:
                context = self._context(Path(temp))
                project = context.root / context.record.relative_path
                active = project / "decisions" / "adr-0001.md"
                archived = project / "archive" / "decisions" / "adr-0001.md"
                active.parent.mkdir(parents=True, exist_ok=True)
                archived.parent.mkdir(parents=True, exist_ok=True)
                archived.write_text(entity, encoding="utf-8")
                if scenario == "dual-entity":
                    active.write_text(entity, encoding="utf-8")
                else:
                    active.write_text(
                        "<!-- tracebook:managed-pointer -->\n\n"
                        "Managed Entity Authority: [adr-0001](../wrong.md)\n\n"
                        "Evidence:\n- `human: Tracebook managed pointer`\n",
                        encoding="utf-8",
                    )
                active_before = active.read_text(encoding="utf-8")
                archive_before = archived.read_text(encoding="utf-8")

                with self.assertRaisesRegex(ValueError, "INVALID_REQUEST"):
                    capture(
                        context,
                        self._request(status="Deprecated"),
                        date(2026, 7, 14),
                    )

                self.assertEqual(active_before, active.read_text(encoding="utf-8"))
                self.assertEqual(
                    archive_before,
                    archived.read_text(encoding="utf-8"),
                )

    def test_entity_capture_rejects_corrupt_authority_backlinks_before_event_no_op(
        self,
    ) -> None:
        scenarios = (
            "missing",
            "duplicate-marker",
            "duplicate-target",
            "malformed",
            "wrong-target",
            "blank-separated",
            "text-separated",
        )
        for kind in ("decision", "synthesis"):
            category = "adr-0001" if kind == "decision" else "refund-flow"
            title = (
                "Persist idempotency keys first"
                if kind == "decision"
                else "Refund flow synthesis"
            )
            directory = "decisions" if kind == "decision" else "synthesis"
            for authority_location in ("active", "archive"):
                seed_status = (
                    "Historical" if authority_location == "active" else "Current"
                )
                authority_status = (
                    "Current" if authority_location == "active" else "Historical"
                )
                for scenario in scenarios:
                    with (
                        self.subTest(
                            kind=kind,
                            authority=authority_location,
                            scenario=scenario,
                        ),
                        TemporaryDirectory() as temp,
                    ):
                        context = self._context(Path(temp))
                        seed = self._request(
                            kind=kind,
                            category=category,
                            title=title,
                            body=f"Seed {kind} history in {seed_status} authority.",
                            status=seed_status,
                        )
                        request = self._request(
                            kind=kind,
                            category=category,
                            title=title,
                            body=f"Stable {authority_location} {kind} authority event.",
                            status=authority_status,
                        )
                        capture(context, seed, date(2026, 7, 13))
                        result = capture(context, request, date(2026, 7, 14))

                        project = context.root / context.record.relative_path
                        active = project / directory / f"{category}.md"
                        archived = project / "archive" / directory / f"{category}.md"
                        authority = (
                            active if authority_location == "active" else archived
                        )
                        pointer = archived if authority == active else active
                        self.assertTrue(pointer.is_file())
                        content = authority.read_text(encoding="utf-8")
                        marker = "<!-- tracebook:managed-pointer-backlink -->"
                        marker_index = content.splitlines().index(marker)
                        target = content.splitlines()[marker_index + 1]
                        event_marker = f"<!-- tracebook:event:{result.event_id} -->"
                        self.assertIn(event_marker, content)

                        if scenario == "missing":
                            corrupted = content.replace(
                                f"{marker}\n{target}\n",
                                "",
                                1,
                            )
                        elif scenario == "duplicate-marker":
                            corrupted = content.replace(
                                marker,
                                f"{marker}\n{marker}",
                                1,
                            )
                        elif scenario == "duplicate-target":
                            corrupted = content.replace(
                                target,
                                f"{target}\n{target}",
                                1,
                            )
                        elif scenario == "malformed":
                            corrupted = content.replace(
                                target,
                                "Managed Pointer: malformed",
                                1,
                            )
                        elif scenario == "wrong-target":
                            corrupted = content.replace(
                                target,
                                f"Managed Pointer: [{category}](wrong.md)",
                                1,
                            )
                        elif scenario == "blank-separated":
                            corrupted = content.replace(
                                f"{marker}\n{target}",
                                f"{marker}\n\n{target}",
                                1,
                            )
                        else:
                            corrupted = content.replace(
                                f"{marker}\n{target}",
                                f"{marker}\nUnexpected backlink separator.\n{target}",
                                1,
                            )
                        self.assertNotEqual(content, corrupted)
                        self.assertIn(event_marker, corrupted)
                        authority.write_text(corrupted, encoding="utf-8")
                        before = self._knowledge_snapshot(context.root)

                        try:
                            retry = capture(context, request, date(2026, 7, 15))
                        except ValueError as error:
                            self.assertRegex(
                                str(error),
                                "INVALID_REQUEST.*backlink",
                            )
                        else:
                            self.fail(
                                "exact retry was incorrectly "
                                f"skipped={retry.skipped} for {scenario} backlink"
                            )

                        self.assertEqual(
                            before,
                            self._knowledge_snapshot(context.root),
                        )

    def test_entity_authority_without_pointer_rejects_managed_backlink(
        self,
    ) -> None:
        for kind in ("decision", "synthesis"):
            category = "adr-0001" if kind == "decision" else "refund-flow"
            title = (
                "Persist idempotency keys first"
                if kind == "decision"
                else "Refund flow synthesis"
            )
            directory = "decisions" if kind == "decision" else "synthesis"
            for authority_location in ("active", "archive"):
                with (
                    self.subTest(kind=kind, authority=authority_location),
                    TemporaryDirectory() as temp,
                ):
                    context = self._context(Path(temp))
                    status = (
                        "Current" if authority_location == "active" else "Historical"
                    )
                    request = self._request(
                        kind=kind,
                        category=category,
                        title=title,
                        body=f"Standalone {authority_location} {kind} authority.",
                        status=status,
                    )
                    result = capture(context, request, date(2026, 7, 13))
                    project = context.root / context.record.relative_path
                    active = project / directory / f"{category}.md"
                    archived = project / "archive" / directory / f"{category}.md"
                    authority = active if authority_location == "active" else archived
                    pointer = archived if authority == active else active
                    self.assertFalse(pointer.exists())
                    content = authority.read_text(encoding="utf-8")
                    event_marker = f"<!-- tracebook:event:{result.event_id} -->"
                    self.assertIn(event_marker, content)
                    authority.write_text(
                        content.rstrip()
                        + "\n\n<!-- tracebook:managed-pointer-backlink -->\n"
                        + f"Managed Pointer: [{category}](wrong.md)\n",
                        encoding="utf-8",
                    )
                    before = self._knowledge_snapshot(context.root)

                    with self.assertRaisesRegex(
                        ValueError,
                        "INVALID_REQUEST.*backlink",
                    ):
                        capture(context, request, date(2026, 7, 14))

                    self.assertEqual(
                        before,
                        self._knowledge_snapshot(context.root),
                    )

    def test_entity_transition_retries_are_idempotent_across_dates(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            project = context.root / context.record.relative_path
            active = project / "decisions" / "adr-0001.md"
            archived = project / "archive" / "decisions" / "adr-0001.md"
            index = project / "index.md"
            status = project / "project-status.md"
            log = project / "logs" / "2026-07.md"

            original = capture(context, self._request(), date(2026, 7, 13))
            retired_request = self._request(
                body="Retire this decision while preserving its full history.",
                status="Historical",
            )
            retired = capture(context, retired_request, date(2026, 7, 14))
            retired_snapshot = {
                path: path.read_text(encoding="utf-8")
                for path in (active, archived, index, status, log)
            }

            retired_retry = capture(
                context,
                retired_request,
                date(2026, 7, 15),
            )

            self.assertTrue(retired_retry.skipped)
            self.assertEqual(retired.event_id, retired_retry.event_id)
            self.assertEqual((), retired_retry.changed_paths)
            self.assertEqual((), retired_retry.new_paths)
            self.assertEqual(
                retired_snapshot,
                {
                    path: path.read_text(encoding="utf-8")
                    for path in retired_snapshot
                },
            )

            restored = capture(context, self._request(), date(2026, 7, 16))
            self.assertFalse(restored.skipped)
            self.assertEqual(original.event_id, restored.event_id)
            self.assertEqual(
                (active, archived, index, status, log),
                restored.changed_paths,
            )
            self.assertEqual((), restored.new_paths)
            active_content = active.read_text(encoding="utf-8")
            self.assertEqual(
                1,
                active_content.count(
                    f"<!-- tracebook:event:{original.event_id} -->"
                ),
            )

            restored_snapshot = {
                path: path.read_text(encoding="utf-8")
                for path in (active, archived, index, status, log)
            }
            restored_retry = capture(
                context,
                self._request(),
                date(2026, 7, 17),
            )
            self.assertTrue(restored_retry.skipped)
            self.assertEqual(original.event_id, restored_retry.event_id)
            self.assertEqual((), restored_retry.changed_paths)
            self.assertEqual((), restored_retry.new_paths)
            self.assertEqual(
                restored_snapshot,
                {
                    path: path.read_text(encoding="utf-8")
                    for path in restored_snapshot
                },
            )

    def test_multiple_entity_transitions_keep_one_authority_and_each_event_once(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            project = context.root / context.record.relative_path
            active = project / "decisions" / "adr-0001.md"
            archived = project / "archive" / "decisions" / "adr-0001.md"
            index = project / "index.md"
            status = project / "project-status.md"
            log = project / "logs" / "2026-07.md"

            requests = (
                self._request(body="Current event one."),
                self._request(body="Deprecated event two.", status="Deprecated"),
                self._request(body="Current event three."),
                self._request(body="Historical event four.", status="Historical"),
            )
            results = []
            for offset, request in enumerate(requests, start=13):
                results.append(capture(context, request, date(2026, 7, offset)))

            self.assertEqual((active,), results[0].new_paths)
            self.assertEqual((archived,), results[1].new_paths)
            self.assertEqual((), results[2].new_paths)
            self.assertEqual((), results[3].new_paths)
            self.assertEqual(
                (archived, active, index, status, log),
                results[3].changed_paths,
            )

            pointer = active.read_text(encoding="utf-8")
            authority = archived.read_text(encoding="utf-8")
            self.assertIn("tracebook:managed-pointer", pointer)
            self.assertNotIn("type: decision", pointer)
            self.assertEqual(1, index.read_text(encoding="utf-8").count("- [adr-0001]("))
            self.assertIn("archive/decisions/adr-0001.md", index.read_text(encoding="utf-8"))
            for request, result in zip(requests, results):
                self.assertIn(request.body, authority)
                self.assertEqual(
                    1,
                    authority.count(
                        f"<!-- tracebook:event:{result.event_id} -->"
                    ),
                )

    def test_managed_pointer_and_authority_pass_existing_health_checks(self) -> None:
        with TemporaryDirectory() as temp:
            context = self._context(Path(temp))
            capture(context, self._request(), date(2026, 7, 13))
            result = capture(
                context,
                self._request(
                    body="Retire this entity without creating a second authority.",
                    status="Deprecated",
                ),
                date(2026, 7, 14),
            )
            project = context.root / context.record.relative_path
            active = project / "decisions" / "adr-0001.md"
            archived = project / "archive" / "decisions" / "adr-0001.md"
            self.assertIn(active, result.changed_paths)
            self.assertIn(archived, result.changed_paths)
            health_status = (
                context.root / "00-global" / "health" / "health-status.md"
            )
            health_status.write_text(
                health_status.read_text(encoding="utf-8").replace(
                    "- Changes Since Last Regular Check: 0",
                    "- Changes Since Last Regular Check: 10",
                ),
                encoding="utf-8",
            )

            report = run_check(
                context.root,
                project,
                [active, archived],
                date(2026, 7, 14),
            )

            self.assertEqual("Regular", report.check_type)
            self.assertEqual([], report.broken_links)
            self.assertEqual([], report.orphan_pages)
            self.assertEqual([], report.missing_sources)
            self.assertEqual([], report.duplicate_pages)

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
