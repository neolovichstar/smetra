import unittest
from unittest.mock import patch
from backend.postgres import translate, schema_name, Row


class PostgresQueryTests(unittest.TestCase):
    def test_alias_and_literal_are_not_table_names(self):
        sql = "SELECT count(*) AS projects,'quotes ? 50%' AS label FROM projects WHERE id=?"
        self.assertEqual(
            translate(sql, "smetra", True),
            "SELECT count(*) AS projects,'quotes ? 50%%' AS label FROM smetra.projects WHERE id=%s",
        )

    def test_join_and_conflict_references(self):
        self.assertEqual(
            translate(
                "SELECT q.id FROM quotes q JOIN users u ON q.user_id=u.id", "smetra"
            ),
            "SELECT q.id FROM smetra.quotes q JOIN smetra.users u ON q.user_id=u.id",
        )
        self.assertEqual(
            translate("INSERT OR IGNORE INTO files(id) VALUES(?)", "smetra", True),
            "INSERT INTO smetra.files(id) VALUES(%s) ON CONFLICT DO NOTHING",
        )

    def test_monthly_quota_upsert_targets_existing_counter(self):
        sql = (
            "INSERT INTO rate_limits(key,count,started) VALUES(?,1,?) "
            "ON CONFLICT(key) DO UPDATE SET count=rate_limits.count+1 RETURNING count"
        )
        self.assertIn(
            "SET count=smetra.rate_limits.count+1",
            translate(sql, "smetra", True),
        )

    def test_query_translation_cache_reuses_hot_sql_safely(self):
        sql = "SELECT id FROM clients WHERE workspace_id=? AND id=?"
        translate.cache_clear()
        first = translate(sql, "smetra", True)
        before = translate.cache_info()
        second = translate(sql, "smetra", True)
        after = translate.cache_info()
        self.assertEqual(first, second)
        self.assertEqual(first, "SELECT id FROM smetra.clients WHERE workspace_id=%s AND id=%s")
        self.assertEqual(after.hits, before.hits + 1)
        self.assertLessEqual(after.currsize, 2048)
        translate.cache_clear()

    def test_only_smetra_schemas_allowed(self):
        for name in ("public", "smetra; DROP SCHEMA public", "smetra.other"):
            with (
                self.subTest(name=name),
                patch.dict("os.environ", SMETRA_DB_SCHEMA=name),
                self.assertRaises(ValueError),
            ):
                schema_name()

    def test_preview_environment_cannot_select_production_schema(self):
        with (
            patch.dict("os.environ", {"VERCEL_ENV": "preview", "SMETRA_DB_SCHEMA": "smetra"}),
            self.assertRaisesRegex(ValueError, "Preview deployment must use an isolated"),
        ):
            schema_name()

    def test_preview_environment_can_select_an_isolated_qa_schema(self):
        with patch.dict(
            "os.environ",
            {"VERCEL_ENV": "preview", "SMETRA_DB_SCHEMA": "smetra_qa_20260928"},
        ):
            self.assertEqual(schema_name(), "smetra_qa_20260928")

    def test_production_environment_can_select_production_schema(self):
        with patch.dict("os.environ", {"VERCEL_ENV": "production", "SMETRA_DB_SCHEMA": "smetra"}):
            self.assertEqual(schema_name(), "smetra")

    def test_rows_support_mapping_and_index_access(self):
        row = Row(id="abc", total=12)
        self.assertEqual(row[0], row["id"])
        self.assertEqual(dict(row), {"id": "abc", "total": 12})
