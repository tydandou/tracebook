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

    def test_guides_document_the_manual_root_language_configuration(self) -> None:
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

        self.assertIn('"knowledge_language": "zh"', english)
        self.assertIn("before the first", english)
        self.assertIn("never translates, rewrites, moves, or deletes", english)
        self.assertIn('"knowledge_language": "zh"', chinese)
        self.assertIn("第一次执行 `resolve` **之前**", chinese)

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
        self.assertEqual("2.0.2", manifest["version"])
        self.assertTrue(
            (ROOT / "plugins" / "tracebook" / "hooks" / "hooks.json").is_file()
        )
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual(
            "https://github.com/tydandou/tracebook", manifest["homepage"]
        )
        self.assertEqual(
            "https://github.com/tydandou/tracebook", manifest["repository"]
        )
        self.assertEqual(
            "https://github.com/tydandou", manifest["author"]["url"]
        )
        self.assertEqual("tracebook", marketplace["name"])
        self.assertEqual("./plugins/tracebook", marketplace["plugins"][0]["source"]["path"])
        self.assertEqual("local", marketplace["plugins"][0]["source"]["source"])
        self.assertEqual("AVAILABLE", marketplace["plugins"][0]["policy"]["installation"])
        self.assertEqual("ON_INSTALL", marketplace["plugins"][0]["policy"]["authentication"])
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
        self.assertEqual("2.0.2", manifest["version"])
        self.assertEqual("tracebook", marketplace["name"])
        self.assertIn("Durable external project knowledge", marketplace["description"])
        self.assertEqual("./plugins/tracebook", marketplace["plugins"][0]["source"])
        self.assertEqual("2.0.2", marketplace["plugins"][0]["version"])

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
        self.assertIn("## [2.0.2] - 2026-07-22", changelog)
        self.assertIn("## [2.0.1] - 2026-07-22", changelog)
        self.assertIn("## [2.0.0] - 2026-07-22", changelog)
        self.assertIn("## [1.2.1] - 2026-07-22", changelog)
        self.assertIn("## [1.2.0] - 2026-07-21", changelog)
        self.assertIn("## [1.1.1] - 2026-07-20", changelog)
        self.assertIn("## [1.1.0] - 2026-07-20", changelog)
        self.assertIn("## [1.0.0] - 2026-07-19", changelog)
        self.assertNotIn("## [1.0.0] - Unreleased", changelog)
        self.assertIn("Not Included", changelog)

    def test_guides_document_read_only_transaction_diagnostics(self) -> None:
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

        self.assertIn("recover-transactions", english)
        self.assertIn("`transactions` is read-only", english)
        self.assertIn("recover-transactions", chinese)
        self.assertIn("`transactions` 是只读命令", chinese)

    def test_ci_verifies_supported_python_versions_on_linux_and_windows(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )

        for required in (
            "ubuntu-latest",
            "windows-latest",
            "'3.10'",
            "'3.13'",
            "python -B -m unittest discover -s tests -v",
            "validate_skill_package.py",
            "python -m compileall -q",
            "fetch-depth: 0",
            "github.event.pull_request.base.sha",
            "github.event.before",
            'git cat-file -e "$base^{object}"',
            'git diff --check "$base" "$head"',
        ):
            self.assertIn(required, workflow)

    def test_bilingual_guides_describe_the_release_and_complete_deep_scope(self) -> None:
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        normalized_chinese = " ".join(chinese.split())

        self.assertNotIn("release candidate", english)
        self.assertIn("The `2.0.2` release is published", english)
        self.assertIn("marketplace source is absent", english)
        self.assertIn("codex plugin marketplace remove tracebook", english)
        self.assertNotIn("optimized for project core-page", english)
        self.assertIn("every active durable Markdown page", english)
        self.assertIn("each level-two knowledge entry", english)
        self.assertIn("version mismatch is an explicit conflict", english)
        self.assertIn("deterministic `context` retrieval", english)

        self.assertNotIn("发布候选", chinese)
        self.assertIn("`2.0.2` 已正式发布", chinese)
        self.assertIn("codex plugin marketplace list", chinese)
        self.assertNotIn("针对 project 核心页面的命名方式优化", chinese)
        self.assertIn("每个活跃的持久 Markdown 页面", normalized_chinese)
        self.assertIn("每个二级标题知识条目", normalized_chinese)
        self.assertIn("内容事件幂等", chinese)
    def test_license_is_apache_2_0(self) -> None:
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0, January 2004", license_text)


if __name__ == "__main__":
    unittest.main()
