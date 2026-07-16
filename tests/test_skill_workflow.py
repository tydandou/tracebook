from pathlib import Path
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
        )

        for name in names:
            self.assertIn(f"references/{name}", skill)
            self.assertTrue((SKILL_ROOT / "references" / name).is_file())

    def test_skill_declares_the_governed_capture_contract(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        for field in ("write_intent", "content_kind", "evidence", "kind", "replacement"):
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
    def test_skill_declares_external_only_read_and_write_gates(self) -> None:
        skill = " ".join(
            (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").split()
        )

        self.assertIn("Do not modify business repositories", skill)
        self.assertIn("existing external knowledge root automatically", skill)
        self.assertIn("pure log analysis", skill)
        self.assertIn("unverified inference", skill)
        self.assertIn("user prohibits a write", skill)
        self.assertIn("health check", skill.lower())


if __name__ == "__main__":
    unittest.main()
