from html.parser import HTMLParser
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.canonical: list[str] = []
        self.descriptions: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")
        if tag == "link" and values.get("rel") == "canonical":
            self.canonical.append(values.get("href") or "")
        if tag == "meta" and values.get("name") == "description":
            self.descriptions.append(values.get("content") or "")


class SiteArtifactsTest(unittest.TestCase):
    pages = (
        SITE / "index.html",
        SITE / "zh" / "index.html",
        SITE / "demo" / "index.html",
        SITE / "compare" / "claude-md" / "index.html",
        SITE / "compare" / "repo-local-memory" / "index.html",
        SITE / "compare" / "vector-memory" / "index.html",
    )

    def test_public_pages_have_search_and_social_metadata(self) -> None:
        for page in self.pages:
            with self.subTest(page=page.relative_to(ROOT)):
                content = page.read_text(encoding="utf-8")
                parser = _LinkParser()
                parser.feed(content)
                self.assertEqual(1, len(parser.canonical))
                self.assertTrue(parser.canonical[0].startswith("https://tydandou.github.io/tracebook/"))
                self.assertEqual(1, len(parser.descriptions))
                self.assertGreaterEqual(len(parser.descriptions[0]), 80)
                self.assertIn('property="og:title"', content)
                self.assertIn('property="og:description"', content)
                self.assertIn('property="og:url"', content)

    def test_local_page_links_resolve(self) -> None:
        for page in self.pages:
            parser = _LinkParser()
            parser.feed(page.read_text(encoding="utf-8"))
            for href in parser.links:
                if not href or href.startswith(("#", "http://", "https://", "mailto:")):
                    continue
                target_text = href.split("#", 1)[0].split("?", 1)[0]
                if not target_text:
                    continue
                target = (page.parent / target_text).resolve()
                if target.is_dir() or target_text.endswith("/"):
                    target = target / "index.html"
                with self.subTest(page=page.relative_to(ROOT), href=href):
                    self.assertTrue(target.is_file(), f"Missing local target: {target}")

    def test_discovery_files_list_every_public_route(self) -> None:
        sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
        llms = (SITE / "llms.txt").read_text(encoding="utf-8")
        for route in (
            "https://tydandou.github.io/tracebook/",
            "https://tydandou.github.io/tracebook/zh/",
            "https://tydandou.github.io/tracebook/demo/",
            "https://tydandou.github.io/tracebook/compare/claude-md/",
            "https://tydandou.github.io/tracebook/compare/repo-local-memory/",
            "https://tydandou.github.io/tracebook/compare/vector-memory/",
        ):
            self.assertIn(route, sitemap)
            self.assertIn(route, llms)

    def test_pages_workflow_deploys_only_the_static_site(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("actions/configure-pages@v5", workflow)
        self.assertIn("actions/upload-pages-artifact@v3", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)
        self.assertIn("path: site", workflow)
        self.assertIn("pages: write", workflow)
        self.assertIn("id-token: write", workflow)


if __name__ == "__main__":
    unittest.main()
