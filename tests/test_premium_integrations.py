import hashlib
import os
import urllib.parse
import unittest
from unittest.mock import Mock, patch

from backend import business, cloud_drives, product_sources, entitlements
from backend.app import Handler


class YandexDiskOAuthTests(unittest.TestCase):
    def test_existing_yandex_id_credentials_reuse_registered_login_callback(self):
        env = {
            "YANDEX_CLIENT_ID": "existing-client",
            "YANDEX_CLIENT_SECRET": "existing-secret",
            "PUBLIC_ORIGIN": "https://smetra.online",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                cloud_drives._credentials("yandex_disk"),
                (
                    "existing-client",
                    "existing-secret",
                    "https://smetra.online/api/auth/oauth/yandex/callback",
                ),
            )

    def test_dedicated_yandex_disk_credentials_override_login_credentials(self):
        env = {
            "YANDEX_CLIENT_ID": "login-client",
            "YANDEX_CLIENT_SECRET": "login-secret",
            "YANDEX_DISK_CLIENT_ID": "disk-client",
            "YANDEX_DISK_CLIENT_SECRET": "disk-secret",
            "YANDEX_DISK_REDIRECT_URI": "https://smetra.online/api/premium/cloud/oauth/callback",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                cloud_drives._credentials("yandex_disk"),
                (
                    "disk-client",
                    "disk-secret",
                    "https://smetra.online/api/premium/cloud/oauth/callback",
                ),
            )

    def test_yandex_authorization_requests_read_only_disk_scope_and_callback(self):
        with patch.dict(os.environ, {}, clear=True):
            url = cloud_drives._provider_start_url(
                "yandex_disk",
                "client-id",
                "https://smetra.online/api/auth/oauth/yandex/callback",
                "state-value",
            )
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(params["redirect_uri"], ["https://smetra.online/api/auth/oauth/yandex/callback"])
        self.assertEqual(params["scope"], ["cloud_api:disk.read"])
        self.assertEqual(params["state"], ["state-value"])

    def test_yandex_rest_requests_use_oauth_authorization_scheme(self):
        connection = {"provider": "yandex_disk"}
        with patch("backend.cloud_drives._access_token", return_value="disk-token"), patch(
            "backend.cloud_drives._http", return_value={"type": "dir"}
        ) as http:
            cloud_drives._yandex_api(object(), connection, "/resources", {"path": "/"})
        self.assertEqual(http.call_args.kwargs["auth_scheme"], "OAuth")
        self.assertEqual(http.call_args.kwargs["token"], "disk-token")

    def test_cloud_state_routes_through_existing_yandex_callback(self):
        handler = object.__new__(Handler)
        con = Mock()
        con.execute.return_value.fetchone.return_value = {"id": "cloud-state"}
        query = {"state": ["opaque-state"]}
        with patch.object(Handler, "send_json", return_value="sent"), patch(
            "backend.business.Service"
        ) as service_type, patch("backend.app.now", return_value=123):
            service_type.return_value.handle.return_value = (200, {"ok": True})
            Handler.api(
                handler,
                "GET",
                "/api/auth/oauth/yandex/callback",
                query,
                con,
            )
        con.execute.assert_called_once_with(
            "SELECT id FROM cloud_oauth_states WHERE state_hash=? "
            "AND provider='yandex_disk' AND consumed_at IS NULL AND expires_at>?",
            (hashlib.sha256(b"opaque-state").hexdigest(), 123),
        )
        service_type.return_value.handle.assert_called_once_with(
            "GET", "/api/premium/cloud/oauth/callback", query
        )


class ProductSourceSafetyTests(unittest.TestCase):
    def test_product_url_is_restricted_to_configured_store_domains(self):
        with patch.dict(os.environ, {"PRODUCT_SCRAPE_ALLOWED_HOSTS": "petrovich.ru"}, clear=True):
            canonical, hostname = product_sources.validate_url(
                "https://shop.petrovich.ru/catalog/item/123",
                resolve_dns=False,
            )
            self.assertEqual(hostname, "shop.petrovich.ru")
            self.assertTrue(canonical.startswith("https://shop.petrovich.ru/catalog/item/123"))
            with self.assertRaises(business.DomainError):
                product_sources.validate_url(
                    "https://example.com/catalog/item/123",
                    resolve_dns=False,
                )

    def test_product_source_rejects_plain_http_and_ip_addresses(self):
        with patch.dict(os.environ, {"PRODUCT_SCRAPE_ALLOWED_HOSTS": "petrovich.ru"}, clear=True):
            with self.assertRaises(business.DomainError):
                product_sources.validate_url(
                    "http://petrovich.ru/catalog/item/123",
                    resolve_dns=False,
                )
            with self.assertRaises(business.DomainError):
                product_sources.validate_url(
                    "https://127.0.0.1/catalog/item/123",
                    resolve_dns=False,
                )



class WorkspaceEntitlementTests(unittest.TestCase):
    def test_legacy_pro_is_solo_not_plus(self):
        row = {"plan": "pro_month", "subscription_status": "active", "entitlement_until": 500}
        result = entitlements.evaluate_workspace_plan(row, "product_monitor", 100)
        self.assertEqual(result["tier"], "pro_solo")
        self.assertFalse(result["allowed"])

    def test_plus_requires_active_subscription_and_unexpired_entitlement(self):
        row = {"plan": "pro_plus_month", "subscription_status": "active", "entitlement_until": 500}
        self.assertTrue(entitlements.evaluate_workspace_plan(row, "cloud_drives", 100)["allowed"])
        self.assertFalse(entitlements.evaluate_workspace_plan(row, "cloud_drives", 501)["allowed"])
        row["subscription_status"] = "cancelled"
        self.assertFalse(entitlements.evaluate_workspace_plan(row, "cloud_drives", 100)["allowed"])

    def test_team_inherits_plus_features(self):
        row = {"plan": "team_year", "subscription_status": "paid", "entitlement_until": 500}
        self.assertTrue(entitlements.evaluate_workspace_plan(row, "visual_estimates", 100)["allowed"])
        self.assertTrue(entitlements.evaluate_workspace_plan(row, "team_management", 100)["allowed"])

    def test_unknown_plan_fails_closed(self):
        row = {"plan": "unrecognized_plan", "subscription_status": "active", "entitlement_until": 500}
        self.assertFalse(entitlements.evaluate_workspace_plan(row, "cloud_drives", 100)["allowed"])

    def test_unknown_feature_is_rejected(self):
        with self.assertRaises(ValueError):
            entitlements.evaluate_workspace_plan(None, "invented_feature", 100)


if __name__ == "__main__":
    unittest.main()
