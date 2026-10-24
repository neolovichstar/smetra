"""Guard against reintroducing detached assistant rails and card panels."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"


class FlatWorkspaceLayoutTests(unittest.TestCase):
    def test_style_is_linked_after_legacy_workspace_sheets(self):
        page = (WEB / "app.html").read_text()
        self.assertIn("cabinet-alignment-v4.css", page)
        self.assertLess(
            page.index("workspace-layout-v3.css"),
            page.index("cabinet-alignment-v4.css"),
        )

    def test_assistant_rail_stays_in_one_layout_tree(self):
        script = (WEB / "assistant-chat.js").read_text()
        self.assertNotIn("assistantAppShell.insertBefore(assistantToolRail", script)
        self.assertIn("assistantStudioRoot.appendChild(assistantToolRail)", script)
        self.assertIn("assistant-toolrail", script)
        self.assertIn("assistant-main-column", script)

    def test_mobile_and_desktop_are_present(self):
        css = (WEB / "cabinet-alignment-v4.css").read_text()
        self.assertIn("@media(min-width:801px)", css)
        self.assertIn("@media(max-width:650px)", css)
        self.assertIn("grid-template-columns:220px minmax(0,1fr)", css)
        self.assertIn(".dashboard-metric", css)
        self.assertIn(".assistant-composer", css)

    def test_existing_functional_hooks_are_kept(self):
        script = (WEB / "assistant-chat.js").read_text()
        for control_id in ("assistant-form", "assistant-attach", "assistant-send",
                           "assistant-new-thread", "assistant-history-list",
                           "assistant-knowledge"):
            with self.subTest(control_id=control_id):
                self.assertIn(control_id, script)


if __name__ == "__main__":
    unittest.main()
