"""The assistant is told plainly that creating an estimate is its job."""
import unittest

from backend.assistant import tools


class QuoteToolTests(unittest.TestCase):
    def test_create_quotes_is_described_for_the_model(self):
        spec = {t["function"]["name"]: t["function"] for t in tools()}
        create = spec["create_quotes"]
        self.assertIn("смет", create["description"])
        self.assertIn("подтверждения", create["description"])
        price = create["parameters"]["properties"]["items"]["items"]["properties"]["unit_price"]
        self.assertIn("копейках", price["description"])
        self.assertNotIn(" quotes.", spec["update_quotes"]["description"])


if __name__ == "__main__":
    unittest.main()
