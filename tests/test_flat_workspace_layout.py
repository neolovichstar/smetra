"""Guard against reintroducing detached assistant rails and card panels."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"


class FlatWorkspaceLayoutTests(unittest.TestCase):
    def test_single_layered_design_system(self):
        page = (WEB / "app.html").read_text()
        sheets = re.findall(r'href="/([^"?]+\.css)', page)
        self.assertEqual(sheets, ["ui/tokens.css", "ui/base.css", "ui/components.css", "ui/shell.css",
                                  "ui/workspace.css", "ui/editor.css", "ui/assistant.css", "ui/modules.css",
                                  "ui/tools.css"])
        legacy = [p.name for p in WEB.glob("*.css") if p.name not in ("change.css", "offline.css")]
        self.assertEqual(legacy, [])

    def test_assistant_rail_stays_in_one_layout_tree(self):
        script = (WEB / "assistant-chat.js").read_text()
        self.assertNotIn("assistantAppShell.insertBefore(assistantToolRail", script)
        self.assertIn("assistantStudioRoot.appendChild(assistantToolRail)", script)
        self.assertIn("assistant-toolrail", script)
        self.assertIn("assistant-main-column", script)

    def test_mobile_and_desktop_are_present(self):
        shell = (WEB / "ui" / "shell.css").read_text()
        self.assertIn("@media (max-width:800px)", shell)
        self.assertIn("body.sidebar-compact .app-shell{grid-template-columns:var(--sidebar-rail) minmax(0,1fr)}", shell)
        self.assertIn(".dashboard-metric", (WEB / "ui" / "workspace.css").read_text())
        self.assertIn(".assistant-composer", (WEB / "ui" / "assistant.css").read_text())

    def test_important_overrides_stay_rare(self):
        total = sum(p.read_text().count("!important") for p in (WEB / "ui").glob("*.css"))
        self.assertLess(total, 60)

    def test_existing_functional_hooks_are_kept(self):
        script = (WEB / "assistant-chat.js").read_text()
        for control_id in ("assistant-form", "assistant-attach", "assistant-send",
                           "assistant-new-thread", "assistant-history-list",
                           "assistant-knowledge"):
            with self.subTest(control_id=control_id):
                self.assertIn(control_id, script)


if __name__ == "__main__":
    unittest.main()
