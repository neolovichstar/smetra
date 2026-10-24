import unittest
from unittest.mock import patch
from backend.postgres import Connection, Row, schema_name, translate


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

    def test_communication_and_subscription_tables_are_schema_qualified(self):
        # Must work before importing backend.community; imports must not mutate SQL.
        from backend.postgres import TABLES

        tables = ("chat_conversations", "chat_members", "chat_messages",
                  "app_presence", "billing_subscriptions")
        self.assertTrue(set(tables).issubset(TABLES))
        for table in tables:
            with self.subTest(table=table):
                self.assertEqual(
                    translate(f"SELECT id FROM {table} WHERE id=?", "smetra", True),
                    f"SELECT id FROM smetra.{table} WHERE id=%s",
                )
        self.assertEqual(
            translate(
                "SELECT COUNT(*) FROM billing_subscriptions b "
                "JOIN users u ON b.user_id=u.id WHERE b.current_period_end>?",
                "smetra", True,
            ),
            "SELECT COUNT(*) FROM smetra.billing_subscriptions b "
            "JOIN smetra.users u ON b.user_id=u.id WHERE b.current_period_end>%s",
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

    def test_scoped_advisory_locks_serialize_only_shared_resources(self):
        connection = Connection.__new__(Connection)
        connection.schema = "smetra"
        connection.lock_key = 123
        connection.lock_scopes = ()

        connection.set_transaction_lock_scopes(("workspace:w1", "user:u1"))
        both = set(connection._transaction_lock_keys())

        connection.set_transaction_lock_scopes(("workspace:w2", "user:u1"))
        self.assertEqual(len(both.intersection(connection._transaction_lock_keys())), 1)

        connection.set_transaction_lock_scopes(("workspace:w1", "user:u2"))
        self.assertEqual(len(both.intersection(connection._transaction_lock_keys())), 1)

        connection.set_transaction_lock_scopes(("workspace:w2", "user:u2"))
        self.assertEqual(both.intersection(connection._transaction_lock_keys()), set())

        connection.set_transaction_lock_scopes(None)
        self.assertEqual(connection._transaction_lock_keys(), (connection.lock_key,))

    def test_begin_immediate_acquires_scoped_locks_in_stable_order(self):
        from unittest.mock import Mock

        connection = Connection.__new__(Connection)
        connection.schema = "smetra"
        connection.runtime = False
        connection.nested = False
        connection.scoped = False
        connection.raw = Mock()
        connection.lock_key = 123
        connection.lock_scopes = ("workspace:w1", "user:u1")

        connection.execute("BEGIN IMMEDIATE")

        calls = [
            (call.args[0], call.args[1])
            for call in connection.raw.execute.call_args_list
            if len(call.args) >= 2
        ]
        self.assertEqual(calls[0], (
            "SELECT pg_advisory_xact_lock_shared(%s)", (connection.lock_key,)
        ))
        acquired = [
            params[0] for sql, params in calls
            if sql == "SELECT pg_advisory_xact_lock(%s)"
        ]
        self.assertEqual(acquired, list(connection._transaction_lock_keys()))

    def test_legacy_transactions_keep_exclusive_schema_gate(self):
        from unittest.mock import Mock

        connection = Connection.__new__(Connection)
        connection.runtime = False
        connection.nested = False
        connection.scoped = False
        connection.raw = Mock()
        connection.lock_key = 987
        connection.lock_scopes = ()

        connection.execute("BEGIN IMMEDIATE")

        connection.raw.execute.assert_any_call(
            "SELECT pg_advisory_xact_lock(%s)", (connection.lock_key,)
        )
        self.assertFalse(any(
            call.args and call.args[0] == "SELECT pg_advisory_xact_lock_shared(%s)"
            for call in connection.raw.execute.call_args_list
        ))
