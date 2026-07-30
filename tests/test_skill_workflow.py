from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "plugins" / "tracebook" / "skills" / "tracebook"


class SkillWorkflowTest(unittest.TestCase):
    def test_skill_links_to_every_governance_reference(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        names = (
            "reading-rules.md",
            "directory-rules.md",
            "auto-creation-rules.md",
            "writing-rules.md",
            "frontmatter-rules.md",
            "source-attribution-rules.md",
            "index-maintenance-rules.md",
            "log-status-rules.md",
            "knowledge-lifecycle-rules.md",
            "synthesis-rules.md",
            "health-check-rules.md",
            "retrieval-timing-rules.md",
        )

        for name in names:
            self.assertIn(f"references/{name}", skill)
            self.assertTrue((SKILL_ROOT / "references" / name).is_file())

    def test_skill_declares_the_governed_capture_contract(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        for field in ("operation", "knowledge_id", "expected_version", "evidence", "kind", "replacement_knowledge_id"):
            self.assertIn(field, skill)
        self.assertIn("business-rule", skill)
        self.assertIn("decision", skill)
        self.assertIn("synthesis", skill)
    def test_skill_passes_growth_metadata_to_the_runner(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("new_paths", skill)
        self.assertIn("--new-path", skill)
        self.assertIn("topic", skill)
    def test_skill_requires_explicit_audit_for_deep_checks(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("check_type: Deep", skill)
        self.assertIn("tracebook_runner.py audit", skill)
        self.assertIn("human review", skill)

    def test_skill_requires_immediate_user_confirmation_for_a_real_write(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("non-skipped capture with changed paths returns `user_summary`", skill)
        self.assertIn("next user-facing message", skill)
        self.assertIn("display\nit to the user verbatim", skill)
    def test_skill_declares_external_only_read_and_write_gates(self) -> None:
        skill = " ".join(
            (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").split()
        )

        self.assertIn("Do not modify business repositories", skill)
        self.assertIn("existing external knowledge root automatically", skill)
        # Logs alone must still fail the gate; the wording moved when the gate
        # was reordered so "logs plus source passes" is not buried under it.
        self.assertIn("resting on logs alone", skill)
        self.assertIn("logs **plus** source", skill)
        self.assertIn("unverified inference", skill)
        self.assertIn("user prohibits a write", skill)
        self.assertIn("health check", skill.lower())

    def test_skill_requires_a_final_write_gate_outcome(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn(
            "Every engineering task must evaluate the write gate before the final response.",
            skill,
        )
        self.assertIn("Routine work with no durable conclusion needs no skip", skill)

    def test_skill_metadata_covers_development_triggers_and_exclusions(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        description = skill.split("\n---\n", 1)[0].lower()
        cases = json.loads(
            (ROOT / "tests" / "fixtures" / "skill_trigger_cases.json").read_text(
                encoding="utf-8"
            )
        )

        for term in (
            "must invoke before",
            "software-development",
            "scaffolding a new project",
            "outside the current repository",
            "analysis",
            "debugging",
            "review",
            "code changes",
            "tests",
            "builds",
            "deploys",
            "ci/cd",
            "incidents",
            "after task completion",
            "write gate",
            "general q&a",
            "non-project conversations",
        ):
            self.assertIn(term, description)
        self.assertGreaterEqual(len(cases["positive"]), 6)
        self.assertGreaterEqual(len(cases["negative"]), 4)

    def test_skill_defines_deterministic_capture_gate_and_soft_reporting(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("evaluate the write gate", skill)
        self.assertIn("no skip", skill)
        for condition in (
            "materially changed",
            "verified",
            "useful after",
            "governed destination",
        ):
            self.assertIn(condition, skill)

    def test_skill_requires_read_only_transaction_diagnostics_before_manual_action(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("tracebook_runner.py transactions", skill)
        self.assertIn("read-only", skill)
        self.assertIn("recover-transactions", skill)
        self.assertIn("never discards, quarantines, or overwrites", skill)

    def test_skill_uses_lock_free_snapshot_reads_for_registered_projects(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("context-read-path", skill)
        self.assertIn("normal lock-free read", skill)
        self.assertIn("PROJECT_ACTIVATION_REQUIRED", skill)

    def test_repository_agents_file_is_optional_in_skill_and_templates(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        english = (
            SKILL_ROOT / "assets" / "knowledge-root-template" / "AGENTS.md"
        ).read_text(encoding="utf-8")
        chinese = (
            SKILL_ROOT / "assets" / "knowledge-root-template-zh" / "AGENTS.md"
        ).read_text(encoding="utf-8")

        self.assertIn("`AGENTS.md` when present", skill)
        self.assertIn("`AGENTS.md`, when present", english)
        self.assertIn("`AGENTS.md`（如存在）", chinese)

    def test_english_and_chinese_root_agents_cover_the_same_workflow_sections(self) -> None:
        english = (
            SKILL_ROOT / "assets" / "knowledge-root-template" / "AGENTS.md"
        ).read_text(encoding="utf-8")
        chinese = (
            SKILL_ROOT / "assets" / "knowledge-root-template-zh" / "AGENTS.md"
        ).read_text(encoding="utf-8")

        for token in (
            "index.md",
            "context-read-path",
            "knowledge_id",
            "00-global/agent-workflow.md",
            "01-projects",
            "02-domain",
            "03-patterns",
            "04-systems",
            "99-archive",
            "system-create",
            "system-bind-project",
            "system-relate",
            "{{knowledge_root}}",
        ):
            with self.subTest(token=token):
                self.assertIn(token, english)
                self.assertIn(token, chinese)

        self.assertEqual(6, english.count("\n## "))
        self.assertEqual(6, chinese.count("\n## "))


if __name__ == "__main__":
    unittest.main()
