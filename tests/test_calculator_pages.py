"""Public calculator pages stay generated from the cabinet's calculator definitions."""
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("calc_pages", ROOT / "scripts/build_calculator_pages.py")
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)


class CalculatorPages(unittest.TestCase):
    def test_pages_on_disk_match_the_generator_and_calculators_js(self):
        specs = pages.specs()
        for item in pages.PAGES:
            on_disk = (pages.OUT / f"{item['slug']}.html").read_text(encoding="utf-8")
            self.assertEqual(on_disk, pages.page(item, specs[item["kind"]], pages.PAGES),
                             f"{item['slug']}.html is stale: run python scripts/build_calculator_pages.py")
            for field in specs[item["kind"]]["fields"]:
                self.assertIn(f'name="{field[0]}"', on_disk)
        self.assertEqual((pages.OUT / "index.html").read_text(encoding="utf-8"), pages.index(pages.PAGES, specs))

    def test_search_markup_and_sitemap(self):
        sitemap = (ROOT / "apps/web/sitemap.xml").read_text(encoding="utf-8")
        for item in pages.PAGES:
            html = (pages.OUT / f"{item['slug']}.html").read_text(encoding="utf-8")
            ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)[1])
            types = {node["@type"] for node in ld["@graph"]}
            self.assertEqual(types, {"WebPage", "BreadcrumbList", "HowTo", "FAQPage"})
            self.assertIn(f'<link rel="canonical" href="https://smetra.online/kalkulyator/{item["slug"]}">', html)
            self.assertIn(f"https://smetra.online/kalkulyator/{item['slug']}</loc>", sitemap)
            self.assertEqual(len(re.findall(r"<h1>", html)), 1)
        vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertIn({"source": "/kalkulyator/:slug", "destination": "/kalkulyator/:slug.html"}, vercel["rewrites"])


if __name__ == "__main__":
    unittest.main()
