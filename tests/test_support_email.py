from pathlib import Path
import unittest

WEB = Path(__file__).resolve().parents[1] / "apps/web"
EXPECTED = "support@smetra.online"
LEGACY = "reyzin378@gmail.com"

class SupportEmailTests(unittest.TestCase):
    def test_all_support_addresses(self):
        for name in ("app.js", "contacts.html", "index.html", "privacy.html", "terms.html"):
            with self.subTest(page=name):
                content=(WEB/name).read_text(encoding="utf-8")
                self.assertIn("mailto:"+EXPECTED, content)
                self.assertNotIn(LEGACY, content)

    def test_support_mail_link_not_hidden(self):
        text=(WEB/"communication-center.js").read_text(encoding="utf-8")
        self.assertNotIn("guide?.querySelector(", text)

    def test_js_cache_version(self):
        for name in ("app.html", "index.html"):
            self.assertIn("/app.js?v=20261024-support-mail-v1",
                          (WEB/name).read_text(encoding="utf-8"))
