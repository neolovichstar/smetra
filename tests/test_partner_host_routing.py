"""HTTP regression tests for the separate console.smetra.online website."""
import http.client
import unittest

from tests.test_business import BusinessFlows


class PartnerHostnameRoutingTests(unittest.TestCase):
    setUpClass = classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(BusinessFlows.tearDownClass.__func__)
    setUp = BusinessFlows.setUp

    def request_raw(self, method, path, hostname):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5
        )
        try:
            conn.request(method, path, headers={"Host": hostname})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read().decode(
                "utf-8", "replace"
            )
        finally:
            conn.close()

    def test_console_root_is_partner_marketing_not_product_landing(self):
        status, headers, body = self.request_raw("GET", "/", "console.smetra.online")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("Сметра для партнёров", body)
        self.assertIn('href="/app"', body)
        self.assertIn('href="/docs"', body)
        self.assertNotIn("Проекты в одном месте", body)

    def test_console_dashboard_and_markdown_docs_are_distinct(self):
        status, _, dashboard = self.request_raw("GET", "/app", "console.smetra.online")
        self.assertEqual(status, 200)
        self.assertIn('id="connect"', dashboard)
        self.assertNotIn("Больше продаж.", dashboard)
        status, _, docs = self.request_raw("GET", "/docs", "console.smetra.online")
        self.assertEqual(status, 200)
        self.assertIn("Developer Docs", docs)
        status, _, source = self.request_raw("GET", "/partner-docs.md", "console.smetra.online")
        self.assertEqual(status, 200)
        self.assertTrue(source.startswith("# Smetra Partner API"))

    def test_partner_policy_pages_are_distinct(self):
        code, _, privacy = self.request_raw("GET", "/privacy", "console.smetra.online")
        self.assertEqual(code, 200)
        self.assertIn("Обработка данных", privacy)
        code, _, terms = self.request_raw("GET", "/terms", "console.smetra.online")
        self.assertEqual(code, 200)
        self.assertIn("Условия пилотного использования", terms)

    def test_console_host_rejects_customer_endpoints(self):
        for route in ("/admin", "/api/me", "/api/billing", "/api/auth/providers"):
            status, _, _ = self.request_raw("GET", route, "console.smetra.online")
            self.assertEqual(status, 404, route)

    def test_customer_domain_does_not_show_partner_root(self):
        status, _, html = self.request_raw("GET", "/", "smetra.online")
        self.assertEqual(status, 200)
        self.assertNotIn("Сметра для партнёров", html)


if __name__ == "__main__":
    unittest.main()
