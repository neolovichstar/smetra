"""Auth and navigation regression checks for the no-flicker shell."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class AuthMotionTests(unittest.TestCase):
 def test_app_starts_with_private_boot_overlay(self):
  html=(ROOT/'apps/web/app.html').read_text()
  self.assertIn('data-app-state="boot"',html)
  self.assertIn('id="app-startup"',html)
  self.assertIn('auth-motion-fix.css',html)
 def test_boot_does_not_confuse_network_failure_with_logout(self):
  source=(ROOT/'apps/web/app.js').read_text()
  self.assertIn("if(error.status===401||error.status===403)",source)
  self.assertIn("showBootError('Соединение не удалось.",source)
  self.assertIn("await render();",source)
  self.assertIn("setAppState('authorized')",source)
  self.assertIn("setAppState('guest')",source)
  self.assertIn("window.SmetraCompleteAuth=async profile",source)
 def test_email_code_switches_shell_without_full_navigation(self):
  source=(ROOT/'apps/web/auth-email.js').read_text()
  self.assertIn("await window.SmetraCompleteAuth(data.user)",source)
  self.assertNotIn("location.assign('/app#dashboard')",source)
 def test_sidebar_route_does_not_render_twice(self):
  source=(ROOT/'apps/web/app.js').read_text()
  self.assertIn("tab=next;if(location.hash.slice(1)!==next)location.hash=next;return renderNavigation()",source)
  self.assertIn("if(!appSections.has(section)||section===tab)return;",source)
  self.assertNotIn("location.hash=tab;closeNavigation();return renderNavigation()",source)
 def test_motion_respects_reduced_preference(self):
  source=(ROOT/'apps/web/auth-motion-fix.css').read_text()
  self.assertIn('prefers-reduced-motion:reduce',source)
  self.assertIn('assistant-composer',source)
  self.assertIn('grid-template-columns',source)
 def test_assistant_empty_state_shares_centered_composer_column(self):
  css=(ROOT/'apps/web/auth-motion-fix.css').read_text()
  html=(ROOT/'apps/web/app.html').read_text()
  self.assertIn('--assistant-dialog-width: 740px',css)
  self.assertIn('width:min(100%,var(--assistant-dialog-width))!important',css)
  self.assertIn('#assistant-messages.assistant-thread',css)
  self.assertIn('.assistant-main-column>.assistant-composer',css)
  self.assertIn('margin-inline:auto!important',css)
  self.assertIn('align-items:stretch!important',css)
  self.assertIn('auth-motion-fix.css?v=20261024-alignment-v2',html)
 def test_oauth_start_cover_and_back_navigation(self):
  source=(ROOT/'apps/web/black.js').read_text()
  self.assertIn("smetra-app-transitioning",source)
  self.assertIn('Перенаправляем в Яндекс ID',source)
  self.assertIn("window.addEventListener('pageshow'",(ROOT/'apps/web/app.js').read_text())

if __name__=="__main__":
 unittest.main()
