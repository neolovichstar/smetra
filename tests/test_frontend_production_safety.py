"""No inline CSP violations, premature presence calls or broken PWA icons."""
from pathlib import Path
import json
import struct
import unittest

WEB=Path(__file__).resolve().parents[1]/"apps"/"web"

class ProductionUIRegressionTests(unittest.TestCase):
    def test_communication_center_has_no_inline_styles(self):
        js=(WEB/"communication-center.js").read_text(encoding="utf-8")
        self.assertNotIn('style=',js)
        self.assertNotIn('.style.',js)
        self.assertIn("comms-empty-list",js)
        self.assertIn("comms-human-needed",js)
        self.assertIn("comms-scroll-locked",js)

    def test_presence_only_starts_after_authorization(self):
        js=(WEB/"communication-center.js").read_text(encoding="utf-8")
        app=(WEB/"app.js").read_text(encoding="utf-8")
        self.assertIn("function startPresence()",js)
        self.assertIn("stopPresence();",js)
        self.assertNotIn("const heartbeat=()=>api('/profile/presence'",js)
        self.assertIn("SmetraCommunication?.startPresence?.()",app)

    def test_favicon_is_valid_windows_icon_and_manifest_png_exists(self):
        icon=(WEB/"favicon.ico").read_bytes()
        self.assertEqual(icon[:6],bytes((0,0,1,0,1,0)))
        size,offset=struct.unpack("<II",icon[14:22])
        self.assertEqual(offset,22)
        self.assertEqual(len(icon),size+offset)
        self.assertTrue(icon[offset:].startswith(bytes((137,80,78,71,13,10,26,10))))
        manifest=json.loads((WEB/"manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["icons"][0]["src"],"/favicon.png")
        self.assertTrue((WEB/"favicon.png").is_file())
