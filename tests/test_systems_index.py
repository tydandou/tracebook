from pathlib import Path
import json
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugins.tracebook.skills.tracebook.scripts import transaction
from plugins.tracebook.skills.tracebook.scripts.errors import TracebookError
from plugins.tracebook.skills.tracebook.scripts.project_registry import ensure_project
from plugins.tracebook.skills.tracebook.scripts.system_registry import bind_project

RUNNER = (
    Path(__file__).resolve().parents[1]
    / "plugins" / "tracebook" / "skills" / "tracebook" / "scripts" / "tracebook_runner.py"
)


class SystemsIndexTest(unittest.TestCase):
    """A registered system must be reachable by browsing, not only by id."""

    def _run(self, *arguments: str, expect_ok: bool = True) -> dict:
        result = subprocess.run(
            [sys.executable, str(RUNNER), *arguments], capture_output=True, check=False
        )
        payload = json.loads(result.stdout.decode("utf-8"))
        if expect_ok:
            self.assertEqual(0, result.returncode, payload)
        return payload

    def _fixture(self, base: Path) -> tuple[Path, dict[str, str]]:
        root = base / "knowledge"
        ids: dict[str, str] = {}
        for name in ("docs", "svc"):
            repo = base / name
            (repo / ".git").mkdir(parents=True)
            resolved = self._run("resolve", "--root", str(root), "--cwd", str(repo))
            ids[name] = resolved["project"]["project_id"]
        return root, ids

    def _index(self, root: Path) -> str:
        return (root / "04-systems" / "index.md").read_text(encoding="utf-8")

    def test_created_system_appears_in_the_systems_index(self) -> None:
        with TemporaryDirectory() as temp:
            root, _ = self._fixture(Path(temp))
            self.assertNotIn("](", self._index(root))

            system = self._run("system-create", "--root", str(root), "--name", "Delivery")
            system_id = system["system"]["system_id"]
            index = self._index(root)
            self.assertIn(system_id, index)
            self.assertIn("Delivery", index)
            self.assertIn("/index.md)", index)

    def test_system_page_lists_members_and_relations(self) -> None:
        with TemporaryDirectory() as temp:
            root, ids = self._fixture(Path(temp))
            system = self._run("system-create", "--root", str(root), "--name", "Delivery")
            system_id = system["system"]["system_id"]
            page = root / system["system"]["relative_path"] / "index.md"
            self.assertIn("- None", page.read_text(encoding="utf-8"))

            for name in ("docs", "svc"):
                self._run("system-bind-project", "--root", str(root),
                          "--system-id", system_id, "--project-id", ids[name])
            self._run("system-relate", "--root", str(root), "--system-id", system_id,
                      "--source-project-id", ids["docs"],
                      "--target-project-id", ids["svc"], "--kind", "designs")

            body = page.read_text(encoding="utf-8")
            # The id is static page content, not part of the generated block, so
            # rebuilding never adds a second copy of it.
            self.assertEqual(1, body.count("- System ID:"), body)
            self.assertIn("## Members", body)
            self.assertIn(ids["docs"], body)
            self.assertIn(ids["svc"], body)
            self.assertIn("## Relations", body)
            self.assertIn("docs --designs--> svc", body)

    def test_repeated_binding_does_not_duplicate_index_or_member_entries(self) -> None:
        with TemporaryDirectory() as temp:
            root, ids = self._fixture(Path(temp))
            system = self._run("system-create", "--root", str(root), "--name", "Delivery")
            system_id = system["system"]["system_id"]
            relative = system["system"]["relative_path"]
            for _ in range(3):
                self._run("system-bind-project", "--root", str(root),
                          "--system-id", system_id, "--project-id", ids["docs"])

            index = self._index(root)
            self.assertEqual(1, index.count(system_id), index)
            page = (root / relative / "index.md").read_text(encoding="utf-8")
            self.assertEqual(1, page.count(ids["docs"]), page)

    def test_idempotent_binding_rebuilds_missing_legacy_navigation(self) -> None:
        with TemporaryDirectory() as temp:
            root, ids = self._fixture(Path(temp))
            system = self._run("system-create", "--root", str(root), "--name", "Delivery")
            system_id = system["system"]["system_id"]
            page = root / system["system"]["relative_path"] / "index.md"
            self._run("system-bind-project", "--root", str(root),
                      "--system-id", system_id, "--project-id", ids["docs"])

            for path, start, end in (
                (page, "<!-- tracebook:system:start -->", "<!-- tracebook:system:end -->"),
                (root / "04-systems" / "index.md",
                 "<!-- tracebook:systems:start -->", "<!-- tracebook:systems:end -->"),
            ):
                current = path.read_text(encoding="utf-8")
                prefix, marker, remainder = current.partition(start)
                self.assertTrue(marker, current)
                _, marker, suffix = remainder.partition(end)
                self.assertTrue(marker, current)
                path.write_text(prefix + suffix, encoding="utf-8")

            self._run("system-bind-project", "--root", str(root),
                      "--system-id", system_id, "--project-id", ids["docs"])
            self.assertIn("<!-- tracebook:system:start -->",
                          page.read_text(encoding="utf-8"))
            self.assertIn("<!-- tracebook:systems:start -->", self._index(root))

    def test_invalid_systems_index_fails_before_membership_is_written(self) -> None:
        with TemporaryDirectory() as temp:
            root, ids = self._fixture(Path(temp))
            system = self._run("system-create", "--root", str(root), "--name", "Delivery")
            system_dir = root / system["system"]["relative_path"]
            config = system_dir / "system.json"
            page = system_dir / "index.md"
            registry = root / "04-systems" / "registry.json"
            before = {path: path.read_bytes() for path in (config, page, registry)}

            systems_index = root / "04-systems" / "index.md"
            systems_index.unlink()
            systems_index.mkdir()
            payload = self._run(
                "system-bind-project", "--root", str(root),
                "--system-id", system["system"]["system_id"],
                "--project-id", ids["docs"], expect_ok=False,
            )

            self.assertEqual("INVALID_SYSTEM_STATE", payload["error"]["code"])
            for path, content in before.items():
                self.assertEqual(content, path.read_bytes(), path)

    def test_interrupted_system_transaction_is_diagnosable_and_recoverable(self) -> None:
        with TemporaryDirectory() as temp:
            root, ids = self._fixture(Path(temp))
            system = self._run("system-create", "--root", str(root), "--name", "Delivery")
            system_id = system["system"]["system_id"]
            original_replace = transaction._replace_target
            replacements = 0

            def crash_after_first_replacement(
                target: Path,
                staged: Path,
                *,
                operation: str,
            ) -> None:
                nonlocal replacements
                if replacements == 1:
                    raise OSError("system bind crashed after first replacement")
                original_replace(target, staged, operation=operation)
                replacements += 1

            with patch.object(
                transaction,
                "_replace_target",
                side_effect=crash_after_first_replacement,
            ):
                with self.assertRaisesRegex(
                    OSError, "system bind crashed after first replacement"
                ):
                    bind_project(root, system_id, ids["docs"])

            diagnostics = transaction.inspect_transactions(root)
            self.assertEqual(1, len(diagnostics), diagnostics)
            self.assertEqual("recoverable", diagnostics[0].disposition)
            recovered = transaction.recover_transactions(root)
            self.assertTrue(recovered)

            config = root / system["system"]["relative_path"] / "system.json"
            payload = json.loads(config.read_text(encoding="utf-8"))
            self.assertIn(ids["docs"], payload["project_ids"])
            self.assertEqual((), transaction.inspect_transactions(root))

    def test_pending_system_transaction_blocks_later_metadata_writes_until_recovered(self) -> None:
        """A second writer must not turn a recoverable first write into blocked."""
        with TemporaryDirectory() as temp:
            root, ids = self._fixture(Path(temp))
            system = self._run("system-create", "--root", str(root), "--name", "Delivery")
            system_id = system["system"]["system_id"]
            original_replace = transaction._replace_target
            replacements = 0

            def crash_after_first_replacement(
                target: Path,
                staged: Path,
                *,
                operation: str,
            ) -> None:
                nonlocal replacements
                if replacements == 1:
                    raise OSError("system bind crashed before the second replacement")
                original_replace(target, staged, operation=operation)
                replacements += 1

            with patch.object(
                transaction,
                "_replace_target",
                side_effect=crash_after_first_replacement,
            ):
                with self.assertRaisesRegex(OSError, "before the second replacement"):
                    bind_project(root, system_id, ids["docs"])

            (pending,) = transaction.inspect_transactions(root)
            self.assertEqual("recoverable", pending.disposition)

            with self.assertRaises(TracebookError) as blocked_bind:
                bind_project(root, system_id, ids["svc"])
            self.assertEqual(
                "TRANSACTION_RECOVERY_REQUIRED", blocked_bind.exception.code
            )

            blocked_update = self._run(
                "project-update", "--root", str(root),
                "--project-id", ids["docs"], "--name", "renamed-docs",
                expect_ok=False,
            )
            self.assertEqual(
                "TRANSACTION_RECOVERY_REQUIRED",
                blocked_update["error"]["code"],
            )
            blocked_remote = self._run(
                "project-bind-remote", "--root", str(root),
                "--project-id", ids["docs"],
                "--remote", "https://github.com/example/docs.git",
                expect_ok=False,
            )
            self.assertEqual(
                "TRANSACTION_RECOVERY_REQUIRED",
                blocked_remote["error"]["code"],
            )
            with self.assertRaises(TracebookError) as blocked_resolve:
                ensure_project(root, Path(temp) / "docs")
            self.assertEqual(
                "TRANSACTION_RECOVERY_REQUIRED", blocked_resolve.exception.code
            )
            (still_pending,) = transaction.inspect_transactions(root)
            self.assertEqual("recoverable", still_pending.disposition)

            transaction.recover_transactions(root)
            bind_project(root, system_id, ids["svc"])
            self._run(
                "project-update", "--root", str(root),
                "--project-id", ids["docs"], "--name", "renamed-docs",
            )

            config = root / system["system"]["relative_path"] / "system.json"
            payload = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual({ids["docs"], ids["svc"]}, set(payload["project_ids"]))
            page = config.with_name("index.md").read_text(encoding="utf-8")
            self.assertIn("renamed-docs", page)
            self.assertEqual((), transaction.inspect_transactions(root))

    def test_project_rename_refreshes_member_system_pages(self) -> None:
        with TemporaryDirectory() as temp:
            root, ids = self._fixture(Path(temp))
            system = self._run("system-create", "--root", str(root), "--name", "Delivery")
            system_id = system["system"]["system_id"]
            page = root / system["system"]["relative_path"] / "index.md"
            self._run("system-bind-project", "--root", str(root),
                      "--system-id", system_id, "--project-id", ids["docs"])

            self._run("project-update", "--root", str(root),
                      "--project-id", ids["docs"], "--name", "renamed-docs")

            body = page.read_text(encoding="utf-8")
            self.assertIn("renamed-docs", body)
            self.assertNotIn("- docs —", body)

    def test_location_update_and_project_rename_touch_only_expected_system_pages(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root, ids = self._fixture(base)
            member = self._run("system-create", "--root", str(root), "--name", "Delivery")
            unrelated = self._run("system-create", "--root", str(root), "--name", "Analytics")
            member_page = root / member["system"]["relative_path"] / "index.md"
            unrelated_page = root / unrelated["system"]["relative_path"] / "index.md"
            self._run(
                "system-bind-project", "--root", str(root),
                "--system-id", member["system"]["system_id"],
                "--project-id", ids["docs"],
            )

            before_member = member_page.read_bytes()
            before_unrelated = unrelated_page.read_bytes()
            moved = base / "moved-docs"
            (moved / ".git").mkdir(parents=True)
            self._run(
                "project-update", "--root", str(root),
                "--project-id", ids["docs"], "--location", str(moved),
            )
            self.assertEqual(before_member, member_page.read_bytes())
            self.assertEqual(before_unrelated, unrelated_page.read_bytes())

            self._run(
                "project-update", "--root", str(root),
                "--project-id", ids["docs"], "--name", "renamed-docs",
            )
            self.assertIn("renamed-docs", member_page.read_text(encoding="utf-8"))
            self.assertEqual(before_unrelated, unrelated_page.read_bytes())

    def test_invalid_member_system_page_blocks_project_rename_without_writes(self) -> None:
        with TemporaryDirectory() as temp:
            root, ids = self._fixture(Path(temp))
            system = self._run("system-create", "--root", str(root), "--name", "Delivery")
            system_id = system["system"]["system_id"]
            system_dir = root / system["system"]["relative_path"]
            page = system_dir / "index.md"
            self._run("system-bind-project", "--root", str(root),
                      "--system-id", system_id, "--project-id", ids["docs"])

            project = next(
                path for path in (root / "01-projects").glob("*/project.json")
                if ids["docs"] in path.read_text(encoding="utf-8")
            )
            projects_index = root / "01-projects" / "index.md"
            before = {path: path.read_bytes() for path in (project, projects_index)}
            page.unlink()
            page.mkdir()

            payload = self._run(
                "project-update", "--root", str(root),
                "--project-id", ids["docs"], "--name", "renamed-docs",
                expect_ok=False,
            )

            self.assertEqual("INVALID_SYSTEM_STATE", payload["error"]["code"])
            for path, content in before.items():
                self.assertEqual(content, path.read_bytes(), path)

    def test_a_pre_block_system_page_gains_the_block_without_duplicating_its_id(self) -> None:
        """The shape a system page had before the generated block existed."""
        with TemporaryDirectory() as temp:
            root, ids = self._fixture(Path(temp))
            system = self._run("system-create", "--root", str(root), "--name", "Delivery")
            system_id = system["system"]["system_id"]
            page = root / system["system"]["relative_path"] / "index.md"
            page.write_text(
                f"# Delivery\n\n- System ID: `{system_id}`\n", encoding="utf-8"
            )

            self._run("system-bind-project", "--root", str(root),
                      "--system-id", system_id, "--project-id", ids["docs"])

            body = page.read_text(encoding="utf-8")
            self.assertEqual(1, body.count("- System ID:"), body)
            self.assertIn("## Members", body)
            self.assertIn(ids["docs"], body)

    def test_hand_written_notes_on_the_index_survive_regeneration(self) -> None:
        with TemporaryDirectory() as temp:
            root, _ = self._fixture(Path(temp))
            path = root / "04-systems" / "index.md"
            path.write_text(
                path.read_text(encoding="utf-8") + "\n本行是人工补充的说明。\n",
                encoding="utf-8",
            )
            self._run("system-create", "--root", str(root), "--name", "Delivery")
            self.assertIn("本行是人工补充的说明。", self._index(root))


if __name__ == "__main__":
    unittest.main()
