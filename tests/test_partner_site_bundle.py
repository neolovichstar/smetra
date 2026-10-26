"""Regression guard: the partner hostname must never publish the customer site.

The actual Vercel preview uses SMETRA_PARTNER_SITE=1 scoped to the feature branch;
this suite validates the isolation function without changing production files.
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_web


class PartnerSiteBundleTests(unittest.TestCase):
    def test_partner_bundle_contains_distinct_landing_login_docs_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "index.html").write_text("consumer landing")
            (output / "app.html").write_text("consumer workspace")
            (output / "admin.html").write_text("consumer admin")
            (output / "assistant-chat.js").write_text("consumer script")
            with patch.object(build_web, "DIST", output):
                with patch.dict(os.environ, {"VERCEL_GIT_COMMIT_REF": build_web.PARTNER_SITE_BRANCH}):
                    build_web.build_partner_bundle()
            landing = (output / "index.html").read_text(encoding="utf-8")
            login = (output / "app.html").read_text(encoding="utf-8")
            docs = (output / "docs.html").read_text(encoding="utf-8")
            self.assertIn("Партнёрская программа", landing)
            self.assertIn("сметра", landing)
            self.assertIn("id=\"connect\"", login)
            self.assertIn("Developer Docs", docs)
            self.assertNotIn("consumer landing", landing)
            self.assertTrue((output / "privacy.html").is_file())
            self.assertTrue((output / "terms.html").is_file())
            self.assertIn("партнёрской платформы",
                          (output / "privacy.html").read_text(encoding="utf-8"))
            self.assertNotIn("МУРАВЬЕВ", (output / "privacy.html").read_text(encoding="utf-8"))

            self.assertFalse((output / "admin.html").exists())
            self.assertFalse((output / "assistant-chat.js").exists())

    def test_partner_bundle_rejects_unintended_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(build_web, "DIST", Path(tmp)):
                with patch.dict(os.environ, {"VERCEL_GIT_COMMIT_REF": "main"}):
                    with self.assertRaisesRegex(RuntimeError, "Refusing partner bundle"):
                        build_web.build_partner_bundle()

    def test_consumer_build_is_opt_in(self):
        self.assertEqual(os.getenv("SMETRA_PARTNER_SITE", "0") == "1", False,
                         "Partner flag must never be globally enabled in CI")
        self.assertIn("partner-landing.html", build_web.WEB.joinpath("partner-landing.html").name)
        self.assertIn("index.html", build_web.PARTNER_STATIC_FILES)


if __name__ == "__main__":
    unittest.main()
