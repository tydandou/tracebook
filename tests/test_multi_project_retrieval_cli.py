"""End-to-end retrieval across fictional projects and shared knowledge scopes."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.request_transport import encode_envelope
from tests.test_retrieval_cli_workflow import fingerprint


PLUGIN = Path(__file__).resolve().parents[1] / "plugins/tracebook"
RUNNER = Path("skills/tracebook/scripts/tracebook_runner.py")


class MultiProjectRetrievalCLITest(unittest.TestCase):
    def exercise(self, runner, base):
        root = base / "knowledge"
        sources = [base / name for name in ("fixture-one", "fixture-two", "fixture-three", "fixture-clone")]
        for index, source in enumerate(sources):
            source.mkdir()
            (source / "src").mkdir()
            (source / "src/widget.py").write_text("VALUE = 1\n", encoding="utf-8")
            if index:
                subprocess.run(["git", "init", "-q", str(source)], check=True, capture_output=True)
            if index >= 2:
                remote = ("https://example.invalid/fixtures/widget.git" if index == 2
                          else "git@example.invalid:fixtures/widget.git")
                subprocess.run(["git", "-C", str(source), "remote", "add", "origin", remote],
                               check=True, capture_output=True)
        original_sources = [fingerprint(source) for source in sources]

        def call(command, *args, request=None, expected=0):
            process = subprocess.run([sys.executable, "-X", "utf8", "-B", str(runner),
                                      command, "--root", str(root), *args], cwd=base,
                                     input=encode_envelope(json.dumps(request, ensure_ascii=False).encode("utf-8"))
                                     if request is not None else None,
                                     capture_output=True, timeout=90)
            self.assertEqual(expected, process.returncode, process.stdout.decode("utf-8") +
                             process.stderr.decode("utf-8"))
            return json.loads(process.stdout)

        initial = call("preflight", "--cwd", str(sources[0]))
        self.assertTrue(initial["blocked"])
        self.assertFalse(root.exists())
        projects = [call("resolve", "--cwd", str(source))["project"] for source in sources]
        ids = [project["project_id"] for project in projects]
        self.assertEqual(3, len(set(ids)))
        self.assertEqual(ids[2], ids[3])
        self.assertTrue((root / "AGENTS.md").is_file())
        self.assertTrue((root / "registry.json").is_file())
        for project in projects:
            directory = root / project["relative_path"]
            self.assertTrue((directory / "index.md").is_file())
            self.assertTrue((directory / "project-status.md").is_file())
            self.assertFalse((directory / "AGENTS.md").exists())

        def write(index=0, expected=0, day="2026-09-26", **changes):
            request = dict(operation="create", scope="project", kind="decision",
                           knowledge_id="shared-rule", title="Fictional widget rule",
                           body=f"widget_inspect sample_record marker{index}，虚构测试说明。",
                           evidence=["src/widget.py:L1"], status="current")
            request.update(changes)
            receipt = call("capture", "--cwd", str(sources[index]), "--request", "-",
                           "--today", day, request=request, expected=expected)
            if expected == 0 and not receipt["skipped"]:
                self.assertTrue(receipt["changed_paths"])
                health = ["--cwd", str(sources[index]), "--source-root", str(sources[index]),
                          "--scope", receipt["health_scope"], "--today", "2026-09-26"]
                for field, flag in (("changed_paths", "--changed"), ("new_paths", "--new-path")):
                    for path in receipt[field]:
                        health.extend((flag, path))
                checked = call("check", *health)
                for field in ("entity_issues", "missing_sources", "broken_links"):
                    self.assertEqual([], checked["findings"][field])
                if checked["check_type"] == "Deep":
                    call("audit", "--cwd", str(sources[index]), "--source-root", str(sources[index]),
                         "--scope", receipt["health_scope"], "--today", "2026-09-26")
            return receipt

        def read(*args, command="context-read", expected=0):
            before = fingerprint(root)
            result = call(command, *args, expected=expected)
            self.assertEqual(before, fingerprint(root))
            return result

        def entities(result):
            return result["current_context"]

        def owners(result):
            return {item["source_project"]["project_id"] for item in entities(result)}

        for index in range(3):
            write(index)
        self.assertTrue(write()["skipped"])
        for index in range(3):
            local = read("--project-id", ids[index], "--query", "widget_inspect")
            self.assertEqual({ids[index]}, owners(local))
            self.assertIn(f"marker{index}", entities(local)[0]["excerpt"])
        clone = read("--cwd", str(sources[3]), "--knowledge-id", "shared-rule",
                     command="context-read-path")
        self.assertEqual({ids[2]}, owners(clone))
        selected = ["--project-id", ids[0], "--project-id", ids[1], "--project-id", ids[0]]
        union = read(*selected, "--query", "widget_inspect")
        self.assertEqual({ids[0], ids[1]}, owners(union))
        self.assertEqual(2, union["matched_count"])
        self.assertEqual({ids[0], ids[1]}, set(union["read_snapshots"]))
        exact = read(*selected, "--knowledge-id", "shared-rule", "--full-content")
        self.assertEqual(2, len({item["body"] for item in entities(exact)}))
        for identity in ids[:2]:
            evidence = read("--project-id", identity, "--evidence-path", "src/widget.py")
            self.assertEqual({identity}, owners(evidence))
            self.assertTrue(all(item["evidence_match"] for item in entities(evidence)))
        rejected = read(*selected, "--evidence-path", "src/widget.py", expected=2)
        self.assertIn("evidence-path requires exactly one project_id", rejected["error"])
        self.assertEqual([], entities(read("--project-id", ids[0], "--query", "marker2")))

        system = call("system-create", "--name", "Fictional fixture system")["system"]["system_id"]
        for identity in ids[:2]:
            call("system-bind-project", "--system-id", system, "--project-id", identity)
        system_result = call("context", "--cwd", str(sources[0]), "--system-id", system,
                             "--query", "widget_inspect")
        self.assertEqual({ids[0], ids[1]}, owners(system_result))
        self.assertNotIn(ids[2], {p["project_id"] for p in system_result["queried_projects"]})

        for scope in ("domain", "pattern"):
            write(scope=scope, body=f"widget_inspect sharedglyph {scope} fictional fixture")
            shared = read("--project-id", ids[1], "--scope", scope, "--query", "widget_inspect")
            self.assertEqual(1, shared["matched_count"])
            self.assertNotIn("source_project", entities(shared)[0])
        combined = read(*selected, "--scope", "all", "--query", "widget_inspect")
        self.assertEqual(4, combined["matched_count"])
        self.assertEqual(4, len({item["path"] for item in entities(combined)}))
        self.assertEqual([], entities(read("--project-id", ids[0], "--query", "sharedglyph")))
        reference = read(*selected, "--profile", "reference", "--query", "widget_inspect")
        self.assertEqual({ids[0], ids[1]}, owners(reference))

        write(knowledge_id="renamed-rule", body="archiveglyph fetch-widget-options", day="2026-09-25")
        write(knowledge_id="renamed-rule", operation="revise", expected_version=1, body="freshglyph")
        self.assertEqual([], entities(read(*selected, "--query", "archiveglyph")))
        for profile in ("adaptive", "audit"):
            historical = read(*selected, "--query", "archiveglyph", "--profile", profile)
            self.assertEqual({ids[0]}, owners(historical))
            item, = entities(historical)
            self.assertEqual((2, 1, "history"), (item["version"], item["matched_version"], item["match_source"]))
            self.assertEqual("freshglyph", item["excerpt"])
        component = read(*selected, "--query", "fetch", "--profile", "adaptive")
        self.assertEqual({ids[0]}, owners(component))
        past = read(*selected, "--query", "archiveglyph", "--as-of", "2026-09-25")
        self.assertEqual(1, entities(past)[0]["version"])
        history = read(*selected, "--knowledge-id", "renamed-rule", "--include-history", "--full-content")
        self.assertEqual("archiveglyph fetch-widget-options", history["historical_context"][0]["body"])
        self.assertEqual(ids[0], history["historical_context"][0]["source_project"]["project_id"])
        snapshot_before = read(*selected, "--knowledge-id", "shared-rule")["read_snapshots"]
        before_rejection = fingerprint(root)
        write(operation="revise", expected_version=99, expected=2)
        self.assertEqual(before_rejection, fingerprint(root))
        write(operation="revise", expected_version=1, body="widget_inspect sample_record updatedglyph")
        snapshot_after = read(*selected, "--knowledge-id", "shared-rule")["read_snapshots"]
        self.assertNotEqual(snapshot_before[ids[0]], snapshot_after[ids[0]])
        self.assertEqual(snapshot_before[ids[1]], snapshot_after[ids[1]])

        write(1, knowledge_id="restricted-rule", body="restrictedglyph", status="pending", evidence=[])
        self.assertEqual([], entities(read(*selected, "--query", "restrictedglyph", "--profile", "audit")))
        self.assertEqual({ids[1]}, owners(read(*selected, "--query", "restrictedglyph", "--status", "pending")))
        write(1, knowledge_id="restricted-rule", operation="change-status", expected_version=1,
              body="restrictedglyph", status="deprecated", evidence=["src/widget.py:L1"])
        self.assertEqual([], entities(read(*selected, "--query", "restrictedglyph", "--profile", "audit")))
        self.assertEqual({ids[1]}, owners(read(*selected, "--query", "restrictedglyph", "--status", "deprecated")))
        limited = read(*selected, "--scope", "all", "--query", "widget_inspect", "--max-results", "1")
        # The renamed fixture still overlaps through its src/widget.py evidence.
        self.assertEqual((5, 1), (limited["matched_count"], limited["returned_count"]))
        self.assertTrue(limited["truncated"])
        tiny = read(*selected, "--knowledge-id", "shared-rule", "--max-chars", "1")
        self.assertEqual([], entities(tiny))
        self.assertTrue(tiny["truncated"])
        read("--project-id", "prj-unknown", "--query", "widget_inspect", expected=2)
        read(*selected, "--scope", "all", "--evidence-path", "src/widget.py", expected=2)
        for scope in ("project", "domain", "pattern"):
            reviewed = call("audit", "--cwd", str(sources[0]), "--source-root", str(sources[0]),
                            "--scope", scope, "--today", "2026-09-26")
            self.assertIn("## Deep Knowledge Audit", reviewed["report"])
        self.assertEqual([], call("transactions")["transactions"])
        self.assertEqual(original_sources, [fingerprint(source) for source in sources])

    def test_source_and_copied_plugin_multi_project_lifecycle(self):
        for copied in (False, True):
            with self.subTest(copied=copied), TemporaryDirectory(prefix="tb-multi-") as temporary:
                base = Path(temporary).resolve()
                package = base / "plugin" if copied else PLUGIN
                if copied:
                    shutil.copytree(PLUGIN, package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                self.exercise(package / RUNNER, base)


if __name__ == "__main__":
    unittest.main()
