"""Liveness and readiness probes have different dependency contracts."""
import unittest
from unittest.mock import MagicMock, patch

from backend.app import Handler


class HealthProbeTests(unittest.TestCase):
    def setUp(self):
        self.handler = Handler.__new__(Handler)
        self.handler.send_json = MagicMock()

    def test_health_is_liveness_and_does_not_open_database(self):
        with patch("backend.app.db", side_effect=AssertionError("liveness must not open DB")) as database:
            self.handler.static("/health")
        database.assert_not_called()
        self.handler.send_json.assert_called_once_with(200, {"ok": True})

    def test_ready_probe_checks_database(self):
        connection = MagicMock()
        context = MagicMock()
        context.__enter__.return_value = connection
        with patch("backend.app.db", return_value=context) as database:
            self.handler.static("/ready")
        database.assert_called_once_with()
        connection.execute.assert_called_once_with("SELECT 1")
        self.handler.send_json.assert_called_once_with(200, {"ok": True, "database": True})

    def test_ready_probe_returns_503_when_database_is_unavailable(self):
        with patch("backend.app.db", side_effect=RuntimeError("internal connection detail")):
            self.handler.static("/ready")
        self.handler.send_json.assert_called_once_with(
            503, {"ok": False, "database": False}
        )


if __name__ == "__main__":
    unittest.main()
