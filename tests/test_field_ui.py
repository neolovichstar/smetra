"""Stable interface wiring, security and visual alignment guards."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/"apps"/"web"

class FieldUIRegressionTests(unittest.TestCase):
    def test_assets_load_and_are_served_by_standalone_backend(self):
        html=(WEB/"app.html").read_text(encoding="utf-8")
        server=(ROOT/"backend"/"app.py").read_text(encoding="utf-8")
        for filename in ("field-flows.js","field-flows.css","interface-audit.css"):
            self.assertIn('/'+filename,html)
            self.assertIn('("'+filename+'",',server)
            self.assertTrue((WEB/filename).stat().st_size>100)
    def test_navigation_and_private_inbox(self):
        html=(WEB/"app.html").read_text(encoding="utf-8")
        js=(WEB/"app.js").read_text(encoding="utf-8")
        for key in ("fieldwork","inbox"):
            self.assertIn('data-tab="'+key+'"',html)
            self.assertIn("'"+key+"'",js)
        self.assertIn("smetra.pendingShare",js)
        self.assertIn("SmetraFieldFlows.render(tab,active)",js)
        self.assertIn("SmetraFieldFlows?.stop?.()",js)
    def test_ui_uses_server_money_and_consent(self):
        js=(WEB/"field-flows.js").read_text(encoding="utf-8")
        for route in ("/voice/draft","/design-projects/draft","/scan/preview","/scan/import",
                      "/shares","/shared-inbox/"):
            self.assertIn(route,js)
        self.assertIn("SmetraEstimateSafety.ensureConsent()",js)
        self.assertIn("review_confirmed:true",js)
        self.assertIn("selected_total_kopecks",js)
        self.assertIn("required",js)
        self.assertNotIn("localStorage.setItem",js)
        self.assertNotIn("style=",js)
        self.assertNotIn(".style.",js)
        self.assertIn("if(!isCurrent())return",js)
    def test_global_icons_and_mobile_layout(self):
        css=(WEB/"interface-audit.css").read_text(encoding="utf-8")
        feature=(WEB/"field-flows.css").read_text(encoding="utf-8")
        self.assertIn("#sidebar .sidebar-item-icon",css)
        self.assertIn("svg",css)
        self.assertIn("repeat(2,minmax(0,1fr))",feature)
        self.assertIn("prefers-reduced-motion",feature)
        self.assertIn("focus-visible",css)
        self.assertIn("ff-offer-line",feature)

if __name__=="__main__":
    unittest.main()
