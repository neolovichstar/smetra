import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MobileAnalyticsWiringTests(unittest.TestCase):
    def test_mytracker_is_initialized_from_application(self):
        manifest = (ROOT / "apps/mobile/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        app = (ROOT / "apps/mobile/app/src/main/java/ru/smetra/mobile/SmetraApp.java").read_text(encoding="utf-8")
        gradle = (ROOT / "apps/mobile/app/build.gradle").read_text(encoding="utf-8")
        self.assertIn('android:name=".SmetraApp"', manifest)
        self.assertIn("Analytics.init(this)", app)
        self.assertIn("com.my.tracker:mytracker-sdk:", gradle)
        self.assertIn("MYTRACKER_SDK_KEY", gradle)

    def test_core_funnel_events_are_wired(self):
        main = (ROOT / "apps/mobile/app/src/main/java/ru/smetra/mobile/MainActivity.java").read_text(encoding="utf-8")
        analytics = (ROOT / "apps/mobile/app/src/main/java/ru/smetra/mobile/Analytics.java").read_text(encoding="utf-8")
        for event in (
            "estimate_created",
            "estimate_sent",
            "client_created",
            "project_created",
            "payment_recorded",
            "ai_draft_generated",
            "capture_shared_in",
        ):
            self.assertIn(f'"{event}"', main)
        self.assertIn("trackRegistrationEvent", analytics)
        self.assertIn("trackLoginEvent", analytics)
        self.assertIn("setCustomUserId", analytics)

    def test_analytics_does_not_forward_direct_pii_fields(self):
        analytics = (ROOT / "apps/mobile/app/src/main/java/ru/smetra/mobile/Analytics.java").read_text(encoding="utf-8")
        self.assertNotIn('optString("email"', analytics)
        self.assertNotIn('optString("phone"', analytics)
        self.assertNotIn('optString("name"', analytics)

    def test_backend_sends_confirmed_pro_conversion_s2s(self):
        app = (ROOT / "backend/app.py").read_text(encoding="utf-8")
        bridge = (ROOT / "backend/mytracker.py").read_text(encoding="utf-8")
        env = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn('"pro_subscription_started"', app)
        self.assertIn('newly_succeeded', app)
        self.assertIn('tracker-s2s.my.com/v1/customEvent/', bridge)
        self.assertIn('MYTRACKER_S2S_APP_ID', env)
        self.assertIn('MYTRACKER_S2S_KEY', env)
        for pii in ('email', 'phone', 'card'):
            self.assertNotIn(f'"{pii}"', bridge)


if __name__ == "__main__":
    unittest.main()
