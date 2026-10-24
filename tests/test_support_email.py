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
            self.assertRegex((WEB/name).read_text(encoding="utf-8"), r"/app\.js\?v=[A-Za-z0-9_-]+")
            # 
                          (WEB/name).read_text(encoding="utf-8"))

    def test_each_mailbox_has_the_right_purpose(self):
        contacts=(WEB/"contacts.html").read_text(encoding="utf-8")
        required={
            "support@smetra.online":"Поддержка",
            "info@smetra.online":"Общие вопросы",
            "sales@smetra.online":"Продажи и компании",
            "docs@smetra.online":"Документооборот",
            "abuse@smetra.online":"Безопасность и жалобы",
        }
        for address,description in required.items():
            with self.subTest(address=address):
                self.assertIn("mailto:"+address,contacts)
                self.assertIn(description,contacts)
        self.assertIn("noreply@smetra.online",contacts)
        self.assertNotIn('mailto:noreply@smetra.online',contacts)

    def test_role_specific_legal_contacts(self):
        self.assertIn("mailto:abuse@smetra.online",
                      (WEB/"privacy.html").read_text(encoding="utf-8"))
        self.assertIn("mailto:docs@smetra.online",
                      (WEB/"terms.html").read_text(encoding="utf-8"))
        self.assertIn("mailto:sales@smetra.online",
                      (WEB/"index.html").read_text(encoding="utf-8"))
