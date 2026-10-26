from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AndroidReleaseScriptTests(unittest.TestCase):
    def test_ru_store_script_matches_current_gradle_identity(self):
        gradle = (ROOT / "apps/mobile/app/build.gradle").read_text(encoding="utf-8")
        script = (ROOT / "scripts/build_android_release.ps1").read_text(encoding="utf-8")
        version_code = re.search(r"versionCode\s+(\d+)", gradle)
        version_name = re.search(r"versionName\s+['\"]([^'\"]+)['\"]", gradle)
        self.assertIsNotNone(version_code)
        self.assertIsNotNone(version_name)
        self.assertIn(f"versionCode='{version_code.group(1)}'", script)
        escaped_version = re.escape(version_name.group(1))
        self.assertIn(f"versionName='{escaped_version}'", script)
        self.assertIn(f"smetra-mobile-{version_name.group(1)}-release.apk", script)

    def test_release_build_requires_and_verifies_the_persisted_signing_certificate(self):
        script = (ROOT / "scripts/build_android_release.ps1").read_text(encoding="utf-8")
        for marker in (
            "SIGNING_STORE_FILE",
            "SIGNING_STORE_PASSWORD",
            "SIGNING_KEY_ALIAS",
            "SIGNING_KEY_PASSWORD",
            "RUSTORE_CERT_SHA256",
            "apksigner verify --verbose --print-certs",
            "if ($expected -ne $fingerprint)",
            "https://smetra.online",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, script)


if __name__ == "__main__":
    unittest.main()
