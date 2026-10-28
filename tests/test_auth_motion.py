"""Auth and navigation regression checks for the no-flicker shell."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class AuthMotionTests(unittest.TestCase):
 def test_app_starts_with_private_boot_overlay(self):
  html=(ROOT/'apps/web/app.html').read_text()
  self.assertIn('data-app-state="boot"',html)
  self.assertIn('id="app-startup"',html)
  self.assertIn('/ui/shell.css',html)
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
  for name in ('tokens.css','components.css','site.css'):
   self.assertIn('prefers-reduced-motion',(ROOT/'apps/web/ui'/name).read_text())
 def test_assistant_empty_state_shares_centered_composer_column(self):
  css=(ROOT/'apps/web/ui/assistant.css').read_text()
  self.assertIn('.assistant-thread,#assistant-actions{width:100%;max-width:760px;margin:0 auto}',css)
  self.assertIn('.assistant-studio:not(.has-conversation) .assistant-main-column{justify-content:center}',css)
  self.assertIn('.assistant-composer{position:relative;z-index:2;width:100%;max-width:808px;margin:0 auto',css)
 def test_oauth_start_cover_and_back_navigation(self):
  source=(ROOT/'apps/web/black.js').read_text()
  self.assertIn("smetra-app-transitioning",source)
  self.assertIn("smetra-app-transitioning",source)
  self.assertIn("args.provider==='google'?'Google':'Яндекс ID'",source)
  self.assertIn("'Открываем защищённый вход '",source)
  self.assertIn("window.SmetraShell.call('auth.start'",source)
  self.assertIn("event.preventDefault()",source)
  self.assertIn("window.addEventListener('pageshow'",(ROOT/'apps/web/app.js').read_text())

if __name__=="__main__":
 unittest.main()
