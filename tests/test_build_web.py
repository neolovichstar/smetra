import tempfile
import unittest
from pathlib import Path

from scripts.build_web import bundle_app_stylesheets


class CabinetCssBundleTests(unittest.TestCase):
    def test_bundles_styles_in_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            output.mkdir()
            (source / "first.css").write_text("body { color: black; }", encoding="utf-8")
            (source / "second.css").write_text(".panel { display: grid; }", encoding="utf-8")
            html = '<head><link rel="stylesheet" href="/first.css"><link rel="stylesheet" href="/second.css"></head>'

            rendered = bundle_app_stylesheets(html, source, output)

            self.assertEqual(rendered.count('rel="stylesheet"'), 1)
            self.assertIn("/app.bundle.", rendered)
            bundle_files = list(output.glob("app.bundle.*.css"))
            self.assertEqual(len(bundle_files), 1)
            bundle = bundle_files[0].read_text(encoding="utf-8")
            self.assertLess(bundle.index("first.css"), bundle.index("second.css"))
            self.assertLess(bundle.index("color: black"), bundle.index("display: grid"))

    def test_single_stylesheet_needs_no_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            output.mkdir()
            html = '<link rel="stylesheet" href="/style.css">'
            self.assertEqual(bundle_app_stylesheets(html, source, output), html)
            self.assertEqual(list(output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
