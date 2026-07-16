from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.validate_skill_package import validate_skill_package


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "plugins" / "tracebook" / "skills" / "tracebook"


class SkillPackageTest(unittest.TestCase):
    def test_package_validator_accepts_this_skill_and_rejects_missing_reference(self) -> None:
        self.assertEqual([], validate_skill_package(SKILL_ROOT))

        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "agents").mkdir()
            (root / "SKILL.md").write_text(
                "---\nname: sample\ndescription: Sample\n---\n\n[missing](references/missing.md)\n",
                encoding="utf-8",
            )
            (root / "agents" / "openai.yaml").write_text(
                "interface:\n  display_name: Sample\n  short_description: Sample\n  default_prompt: Sample\n",
                encoding="utf-8",
            )

            self.assertIn("references/missing.md", validate_skill_package(root))
    def test_skill_metadata_and_required_references_exist(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("name: tracebook", skill)
        self.assertIn("~/.tracebook", skill)
        self.assertTrue((SKILL_ROOT / "agents" / "openai.yaml").is_file())
        self.assertTrue((SKILL_ROOT / "references" / "reading-rules.md").is_file())
        agent = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("interface:", agent)
        self.assertIn("  display_name:", agent)


if __name__ == "__main__":
    unittest.main()
