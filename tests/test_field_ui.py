"""Stable interface wiring, security and visual alignment guards."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/"apps"/"web"

class FieldUIRegressionTests(unittest.TestCase):
    def test_assets_load_and_are_served_by_standalone_backend(self):
        html=(WEB/"app.html").read_text(encoding="utf-8")
        server=(ROOT/"backend"/"app.py").read_text(encoding="utf-8")
        self.assertIn('/field-flows.js',html)
        self.assertIn('js_asset = re.fullmatch',server)
        self.assertTrue((WEB/"field-flows.js").stat().st_size>100)
        self.assertIn('/ui/modules.css',html)
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
        shell=(WEB/"ui"/"shell.css").read_text(encoding="utf-8")
        modules=(WEB/"ui"/"modules.css").read_text(encoding="utf-8")
        base=(WEB/"ui"/"base.css").read_text(encoding="utf-8")
        self.assertIn(".sidebar-item-icon",shell)
        self.assertIn("focus-visible",base)
        self.assertIn(".ff-field-grid",modules)
        self.assertIn("ff-offer-line",modules)

if __name__=="__main__":
    unittest.main()
