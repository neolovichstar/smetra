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

    def test_admin_subscription_count_uses_portable_timestamp_parameter(self):
        sql = "SELECT count(*) FROM users WHERE entitlement_until > ? AND deleted_at IS NULL"
        self.assertEqual(
            translate(sql, "smetra", True),
            "SELECT count(*) FROM smetra.users WHERE entitlement_until > %s AND deleted_at IS NULL",
        )
        self.assertNotIn("unixepoch()", sql.lower())

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

    def test_only_smetra_schemas_allowed(self):
        for name in ("public", "smetra; DROP SCHEMA public", "smetra.other"):
            with (
                self.subTest(name=name),
                patch.dict("os.environ", SMETRA_DB_SCHEMA=name),
                self.assertRaises(ValueError),
            ):
                schema_name()

    def test_connection_returns_warm_connection_to_pool(self):
        from unittest.mock import Mock, patch
        from backend.postgres import Connection

        raw = Mock()
        pool = Mock()
        pool.getconn.return_value = raw
        with (
            patch.dict("os.environ", {"DATABASE_URL": "postgresql://localhost/smetra", "SMETRA_LOCAL_POSTGRES": "1"}),
            patch("backend.postgres._connection_pool", return_value=pool),
        ):
            connection = Connection()
            self.assertIs(connection.raw, raw)
            connection.close()

        pool.getconn.assert_called_once_with(timeout=5)
        pool.putconn.assert_called_once_with(raw)
        raw.close.assert_not_called()

    def test_rows_support_mapping_and_index_access(self):
        row = Row(id="abc", total=12)
        self.assertEqual(row[0], row["id"])
        self.assertEqual(dict(row), {"id": "abc", "total": 12})

    def test_simple_insert_executemany_batches_network_round_trips(self):
        from backend.postgres import Connection

        con = Connection.__new__(Connection)
        rows = [(f"id-{i}", "quote-1", i, "{}") for i in range(200)]
        with patch.object(Connection, "execute", autospec=True, return_value="cursor") as execute:
            result = con.executemany("INSERT INTO quote_items VALUES(?,?,?,?)", rows)

        self.assertIsNone(result)
        execute.assert_called_once()
        sql, parameters = execute.call_args.args[1:]
        self.assertEqual(sql.count("?"), 200 * 4)
        self.assertEqual(sql.count("("), 200)
        self.assertEqual(parameters, tuple(value for row in rows for value in row))

    def test_executemany_keeps_fallback_for_non_simple_insert(self):
        from backend.postgres import Connection

        con = Connection.__new__(Connection)
        rows = [(1, "a"), (2, "b")]
        with patch.object(Connection, "execute", autospec=True, side_effect=lambda _self, sql, params: (sql, params)) as execute:
            result = con.executemany("UPDATE rate_limits SET count=? WHERE key=?", rows)

        self.assertEqual(execute.call_count, 2)
        self.assertIsNone(result)
