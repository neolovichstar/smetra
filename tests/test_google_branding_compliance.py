"""Checks public app identity and user-data disclosures for Google OAuth review."""

import unittest
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "apps" / "web"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attributes):
        if tag == "a":
            self.links.add(dict(attributes).get("href", ""))


class GoogleBrandingComplianceTests(unittest.TestCase):
    def test_public_homepage_explains_app_and_links_privacy(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn("сметра. —", html)
        self.assertIn("строительных смет", html)
        self.assertIn("Google Drive", html)
        links = Links()
        links.feed(html)
        self.assertIn("/privacy", links.links)
        self.assertIn("/privacy#google-drive", links.links)
        self.assertIn("/terms", links.links)

    def test_google_data_policy_discloses_scopes_processing_and_revocation(self):
        html = (SITE / "privacy.html").read_text(encoding="utf-8")
        for item in (
            "сметра.", "openid", "email", "profile", "drive.readonly",
            "Google Drive API", "OpenRouter", "Limited Use",
            "зашифрованном виде", "отозвать разрешения", "удалени",
        ):
            self.assertIn(item, html)
        self.assertIn("https://myaccount.google.com/connections", html)
        self.assertIn('id="google-drive"', html)
        self.assertIn("support@smetra.online", html)

    def test_sitemap_uses_canonical_website_only(self):
        xml = (SITE / "sitemap.xml").read_text(encoding="utf-8")
        urls = [node.text for node in ElementTree.fromstring(xml).iter()
                if node.tag.endswith("loc")]
        self.assertIn("https://smetra.online/", urls)
        self.assertIn("https://smetra.online/privacy", urls)
        self.assertTrue(all(url.startswith("https://smetra.online/") for url in urls))
        self.assertNotIn("smetra.vercel.app", xml)


if __name__ == "__main__":
    unittest.main()
