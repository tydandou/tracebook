import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicArtifactsTest(unittest.TestCase):
    def test_readme_states_installation_privacy_and_non_migration_policy(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("~/.tracebook", readme)
        self.assertIn("Existing external knowledge is **not imported automatically**", readme)
        self.assertIn("not imported automatically", readme)
        self.assertIn("business repositories", readme)
        self.assertIn("API key", readme)
        self.assertIn("codex plugin marketplace add", readme)
        self.assertIn("codex plugin add tracebook@tracebook", readme)
        self.assertIn("claude plugin marketplace add", readme)
        self.assertIn("claude plugin install tracebook@tracebook", readme)
        self.assertIn("claude --plugin-dir ./plugins/tracebook", readme)
        self.assertIn("plugins/tracebook/skills/tracebook/scripts/validate_skill_package.py", readme)

    def test_plugin_manifest_and_marketplace_expose_tracebook(self) -> None:
        manifest = json.loads(
            (ROOT / "plugins" / "tracebook" / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual("tracebook", manifest["name"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual("tracebook", marketplace["name"])
        self.assertEqual("./plugins/tracebook", marketplace["plugins"][0]["source"]["path"])
    def test_claude_plugin_manifest_and_marketplace_expose_tracebook(self) -> None:
        manifest = json.loads(
            (ROOT / "plugins" / "tracebook" / ".claude-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        marketplace = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual("tracebook", manifest["name"])
        self.assertEqual("tracebook", marketplace["name"])
        self.assertIn("Durable external project knowledge", marketplace["description"])
        self.assertEqual("./plugins/tracebook", marketplace["plugins"][0]["source"])
    def test_readme_declares_canonical_markdown_link_policy(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("## Link Policy", readme)
        self.assertIn("Markdown links are the canonical output format", readme)
        self.assertIn("Wikilinks are accepted as compatibility input", readme)
    def test_release_docs_explain_v1_workflow_and_boundaries(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("## Quick Start", readme)
        self.assertIn("## Daily Workflow", readme)
        self.assertIn("resolve --cwd", readme)
        self.assertIn("capture", readme)
        self.assertIn("check", readme)
        self.assertIn("audit", readme)
        self.assertIn("## [1.0.0] - Unreleased", changelog)
        self.assertIn("Not Included", changelog)
    def test_license_is_apache_2_0(self) -> None:
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0, January 2004", license_text)


if __name__ == "__main__":
    unittest.main()
