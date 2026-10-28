import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from backend import business, cloud_drives, identity


class GoogleLoginTests(unittest.TestCase):
    def test_google_login_requires_credentials_and_has_private_config(self):
        with patch.dict(os.environ, {"GOOGLE_AUTH_CLIENT_ID": "", "GOOGLE_AUTH_CLIENT_SECRET": "", "GOOGLE_DRIVE_CLIENT_ID": "", "GOOGLE_DRIVE_CLIENT_SECRET": ""}):
            providers = {x["id"]: x for x in identity.providers()}
            self.assertFalse(providers["google"]["enabled"])
        with patch.dict(os.environ, {"GOOGLE_AUTH_CLIENT_ID": "google-id", "GOOGLE_AUTH_CLIENT_SECRET": "private-secret"}):
            providers = {x["id"]: x for x in identity.providers()}
            self.assertTrue(providers["google"]["enabled"])
            self.assertNotIn("private-secret", str(providers))
        with patch.dict(os.environ, {"GOOGLE_AUTH_CLIENT_ID": "", "GOOGLE_AUTH_CLIENT_SECRET": "", "GOOGLE_DRIVE_CLIENT_ID": "drive-id", "GOOGLE_DRIVE_CLIENT_SECRET": "drive-secret"}):
            self.assertEqual(identity.config("google"), ("drive-id", "drive-secret"))
        with patch.dict(os.environ, {"GOOGLE_AUTH_CLIENT_ID": "incomplete-auth-id", "GOOGLE_AUTH_CLIENT_SECRET": "", "GOOGLE_DRIVE_CLIENT_ID": "drive-id", "GOOGLE_DRIVE_CLIENT_SECRET": "drive-secret"}):
            self.assertFalse(next(p for p in identity.providers() if p["id"] == "google")["enabled"])


    def test_google_callback_is_canonical_when_public_origin_is_legacy_alias(self):
        from tests.test_identity_assistant import IdentityAssistantTests
        handler = IdentityAssistantTests()
        IdentityAssistantTests.setUpClass()
        try:
            with patch.dict(os.environ, {
                "GOOGLE_AUTH_CLIENT_ID": "google-id",
                "GOOGLE_AUTH_CLIENT_SECRET": "test-secret",
                "PUBLIC_ORIGIN": "https://smetra.vercel.app",
            }):
                status, headers, _ = handler.get_redirect(
                    "/api/auth/oauth/google/start?intent=login", host="smetra.online",
                )
            self.assertEqual(status, 303)
            self.assertEqual(
                parse_qs(urlsplit(headers["Location"]).query)["redirect_uri"],
                ["https://smetra.online/api/auth/oauth/google/callback"],
            )
        finally:
            IdentityAssistantTests.tearDownClass()

    def test_google_authorization_uses_only_basic_login_permissions(self):
        # This uses the exact production route, not the Drive restricted-scope callback.
        from tests.test_identity_assistant import IdentityAssistantTests
        handler = IdentityAssistantTests()
        IdentityAssistantTests.setUpClass()
        try:
            with patch.dict(os.environ, {"GOOGLE_AUTH_CLIENT_ID": "google-id", "GOOGLE_AUTH_CLIENT_SECRET": "secret"}):
                status, headers, _ = handler.get_redirect("/api/auth/oauth/google/start?intent=login", host="smetra.online")
            self.assertEqual(status, 303)
            url = urlsplit(headers["Location"])
            params = parse_qs(url.query)
            self.assertEqual(url.hostname, "accounts.google.com")
            self.assertEqual(params["scope"], ["openid email profile"])
            self.assertEqual(params["redirect_uri"], ["https://smetra.online/api/auth/oauth/google/callback"])
            self.assertEqual(params["code_challenge_method"], ["S256"])
            self.assertNotIn("client_secret", params)
            self.assertNotIn("drive.readonly", url.query)
        finally:
            IdentityAssistantTests.tearDownClass()

    def test_google_start_from_legacy_alias_redirects_to_canonical_host(self):
        from tests.test_identity_assistant import IdentityAssistantTests
        handler = IdentityAssistantTests()
        IdentityAssistantTests.setUpClass()
        try:
            with patch.dict(os.environ, {"GOOGLE_AUTH_CLIENT_ID": "google-id", "GOOGLE_AUTH_CLIENT_SECRET": "secret"}):
                for host in ("smetra.vercel.app", "www.smetra.online"):
                    status, headers, _ = handler.get_redirect("/api/auth/oauth/google/start?intent=login", host=host)
                    self.assertEqual(status, 303)
                    self.assertEqual(
                        headers["Location"],
                        "https://smetra.online/api/auth/oauth/google/start?intent=login",
                    )
                    self.assertNotIn("Set-Cookie", headers)
        finally:
            IdentityAssistantTests.tearDownClass()

    def test_google_subject_is_verified_server_side_and_avatar_is_not_trusted(self):
        with patch.dict(os.environ, {"GOOGLE_AUTH_CLIENT_ID": "google-id", "GOOGLE_AUTH_CLIENT_SECRET": "private-secret"}):
            with patch("backend.identity.remote", side_effect=[
                {"access_token": "opaque-token"},
                {"sub": "1234567890123456789", "name": "Анна", "email": "anna@example.test", "email_verified": True, "picture": "https://evil.example/pic"},
            ]) as mock_remote:
                result = identity.profile("google", "code", "state", "verifier", "https://smetra.online/api/auth/oauth/google/callback", "")
            self.assertEqual(result, ("1234567890123456789", "Анна", "anna@example.test"))
            self.assertEqual(mock_remote.call_args_list[0].args[0], "https://oauth2.googleapis.com/token")
            self.assertEqual(mock_remote.call_args_list[1].kwargs["headers"]["Authorization"], "Bearer opaque-token")
            with patch("backend.identity.remote", side_effect=[
                {"access_token": "token"},
                {"sub": "1234567890123456789", "email": "anna@example.test", "email_verified": False},
            ]):
                with self.assertRaises(ValueError):
                    identity.profile("google", "code", "state", "verifier", "https://smetra.online/api/auth/oauth/google/callback", "")


class CloudFolderBrowseTests(unittest.TestCase):
    def test_google_lists_only_direct_folders_with_pagination(self):
        con = object()
        connection = {"provider": "google_drive", "status": "active"}
        response = {"files": [
            {"id": "folder_2", "name": "Сметы", "mimeType": "application/vnd.google-apps.folder"},
            {"id": "receipt_1", "name": "Счёт.pdf", "mimeType": "application/pdf"},
            {"id": "file_1", "name": "Документ", "mimeType": "text/plain"},
            {"id": "folder_3", "name": "Удалено", "mimeType": "application/vnd.google-apps.folder", "trashed": True},
        ], "nextPageToken": "next-token"}
        with patch("backend.cloud_drives._google_api", return_value=response) as get:
            result = cloud_drives._browse_folders(con, connection, "root", "")
        self.assertEqual(result["folders"], [{"id": "folder_2", "name": "Сметы"}])
        self.assertEqual(result["files"], [{"name": "Счёт.pdf", "mime_type": "application/pdf"},
                                            {"name": "Документ", "mime_type": "text/plain"}])
        self.assertEqual(result["next_cursor"], "next-token")
        self.assertIn("'root' in parents", get.call_args.args[3]["q"])
        self.assertNotIn("mimeType = 'application/vnd.google-apps.folder'", get.call_args.args[3]["q"])
        for parent in ("'", "bad id", "https://evil.com", "../../../etc"):
            with self.assertRaises(business.DomainError):
                cloud_drives._browse_folders(con, connection, parent, "")

    def test_yandex_lists_directories_without_downloading_files(self):
        con = object()
        connection = {"provider": "yandex_disk", "status": "active"}
        response = {"_embedded": {"total": 3, "items": [
            {"path": "disk:/Сметы", "name": "Сметы", "type": "dir"},
            {"path": "/Документы", "name": "Документы", "type": "dir"},
            {"path": "/файл.pdf", "name": "файл.pdf", "type": "file", "mime_type": "application/pdf"},
        ]}}
        with patch("backend.cloud_drives._yandex_api", return_value=response) as get:
            result = cloud_drives._browse_folders(con, connection, "/", "")
        self.assertEqual(result["folders"], [{"id": "/Сметы", "name": "Сметы"}, {"id": "/Документы", "name": "Документы"}])
        self.assertEqual(result["next_cursor"], "")
        self.assertEqual(result["files"], [{"name": "файл.pdf", "mime_type": "application/pdf"}])
        self.assertEqual(get.call_args.args[3]["path"], "/")
        for parent in ("../secret", "/../secret", "relative"):
            with self.assertRaises(business.DomainError):
                cloud_drives._browse_folders(con, connection, parent, "")
        with self.assertRaises(business.DomainError):
            cloud_drives._browse_folders(con, {"provider": "yandex_disk", "status": "disabled"}, "/", "")


if __name__ == "__main__":
    unittest.main()
