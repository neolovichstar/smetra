"""Browser error reports reach the request log, cleaned and bounded; nothing is stored."""
import contextlib
import io
import json
import unittest

from tests import test_business


class ClientErrors(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call

    def test_report_is_logged_without_control_characters_and_bounded(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status, _ = self.call("/client-errors", "POST", {
                "message": "TypeError: x is undefined\n\x1b[31m" + "y" * 900, "source": "/app.js",
                "line": 120, "column": "7", "page": "/app#quotes"})
        self.assertEqual(status, 200)
        entry = next(json.loads(line) for line in out.getvalue().splitlines() if '"client_error"' in line)
        self.assertEqual((entry["source"], entry["line"], entry["column"], entry["page"]), ("/app.js", 120, 0, "/app#quotes"))
        self.assertLessEqual(len(entry["message"]), 300)
        self.assertNotIn("\n", entry["message"])
        self.assertNotIn("\x1b", entry["message"])
        self.assertEqual(self.call("/client-errors", "POST", ["nope"])[0], 400)


if __name__ == "__main__":
    unittest.main()
