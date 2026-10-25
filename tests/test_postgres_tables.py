"""Every table created by the communication module is schema-qualified on PostgreSQL."""
import re
import unittest
from pathlib import Path

from backend import community  # noqa: F401  registers its tables
from backend import postgres


class SchemaAllowListTests(unittest.TestCase):
    def test_community_tables_are_qualified(self):
        source = Path(community.__file__).read_text(encoding="utf-8")
        names = set(re.findall(r"CREATE TABLE IF NOT EXISTS ([a-z_]+)", source))
        self.assertIn("billing_subscriptions", names)
        for name in names:
            with self.subTest(table=name):
                self.assertIn(f"smetra.{name}", postgres.translate(f"SELECT 1 FROM {name}", "smetra"))


if __name__ == "__main__":
    unittest.main()
