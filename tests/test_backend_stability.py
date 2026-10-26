"""Regressions for database pressure, interrupted SSE and malformed chat input."""
import hashlib
import io
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend import postgres
from backend.assistant import ChatStream
from backend.app import Handler
from backend.business import DomainError
from tests import test_business


class DatabasePressureTests(unittest.TestCase):
    def test_fallback_reuses_request_connection_without_commit_or_close(self):
        con = Mock()
        con.execute.return_value.fetchone.return_value = (1,)
        with patch("backend.postgres.Connection", side_effect=AssertionError("second checkout")):
            self.assertTrue(postgres.throttle("write:user", 2, 60, 100, connection=con))
        con.execute.assert_called_once()
        con.commit.assert_not_called()
        con.close.assert_not_called()

    def test_fallback_retains_limit_semantics(self):
        con = Mock()
        con.execute.return_value.fetchone.return_value = (3,)
        self.assertFalse(postgres.throttle("write:user", 2, 60, 100, connection=con))

    def test_handler_supplies_the_live_primary_connection_on_redis_outage(self):
        from backend.redis_infra import RedisUnavailable

        con = object()
        handler = SimpleNamespace(_request_db=con)
        with patch.dict(os.environ, DATABASE_URL="postgresql://localhost/fixture"), \
                patch("backend.redis_infra.rate_limit", side_effect=RedisUnavailable("fixture")), \
                patch("backend.postgres.throttle", return_value=True) as throttle:
            Handler.throttle(handler, "write:user", 2, 60)
        self.assertIs(throttle.call_args.kwargs.get("connection"), con)

    def test_sql_translation_cache_avoids_repeating_regex_work(self):
        sql = "SELECT name FROM clients WHERE workspace_id=? AND id=?"
        postgres.translate(sql, "smetra_cache_fixture", True)
        with patch("backend.postgres.re.sub", side_effect=AssertionError("translated twice")):
            translated = postgres.translate(sql, "smetra_cache_fixture", True)
        self.assertIn("smetra_cache_fixture.clients", translated)
        self.assertIn("%s", translated)

    def test_cache_separates_schema_parameter_mode_and_table_registry(self):
        sql = "SELECT id FROM fixture_table WHERE id=?"
        self.assertIn("id=?", postgres.translate(sql, "smetra_a"))
        self.assertIn("id=%s", postgres.translate(sql, "smetra_b", True))
        with patch.object(postgres, "TABLES", postgres.TABLES | {"fixture_table"}):
            self.assertIn("smetra_a.fixture_table", postgres.translate(sql, "smetra_a"))
        self.assertNotIn("smetra_a.fixture_table", postgres.translate(sql, "smetra_a"))

    def test_translation_cache_is_bounded_and_skips_bulk_statements(self):
        postgres._translate_cached.cache_clear()
        for index in range(2100):
            postgres.translate("SELECT " + str(index), "smetra")
        self.assertEqual(postgres._translate_cached.cache_info().currsize, 2048)
        before = postgres._translate_cached.cache_info()
        large = "SELECT id FROM clients WHERE id IN (" + ",".join("?" for _ in range(5000)) + ")"
        translated = postgres.translate(large, "smetra", True)
        self.assertIn("smetra.clients", translated)
        self.assertEqual(translated.count("%s"), 5000)
        self.assertEqual(postgres._translate_cached.cache_info(), before)


class StreamDurabilityTests(unittest.TestCase):
    def fixture(self, finish=None, writer=None):
        events = []
        runtime = Mock()
        runtime.finish.side_effect = finish or (lambda success: events.append(("finish", success)))
        lease = Mock()
        lease.release.side_effect = lambda: events.append(("lease", None))

        class Writer(io.BytesIO):
            def write(self, data):
                if b"event: done" in data:
                    events.append(("done", None))
                return super().write(data)

        handler = SimpleNamespace(
            wfile=writer or Writer(), request_id="stream-fixture",
            send_response=Mock(), send_header=Mock(), end_headers=Mock(),
        )
        service = SimpleNamespace(runtime_connection=runtime)
        return service, handler, lease, runtime, events

    def test_commit_precedes_done_and_lease_release(self):
        service, handler, lease, runtime, events = self.fixture()
        with patch("backend.assistant.public_quota", return_value={"remaining": 50}), \
                patch("backend.assistant.answer_chat", return_value={"answer": "Готово", "quota": {"remaining": 40}}):
            ChatStream(service, "Проверка", {}, lease=lease).write(handler)
        self.assertEqual(events, [("finish", True), ("done", None), ("lease", None)])
        runtime.finish.assert_called_once_with(True)
        self.assertIsNone(service.runtime_connection)
        handler.send_header.assert_any_call("Cache-Control", "no-store, no-transform")

    def test_commit_failure_has_error_without_done_or_second_finalize(self):
        service, handler, lease, runtime, events = self.fixture(
            finish=lambda _: (_ for _ in ()).throw(RuntimeError("fixture commit failure"))
        )
        def quota(_):
            if runtime.finish.called:
                raise AssertionError("query on released connection")
            return {"remaining": 50}
        with patch("backend.assistant.public_quota", side_effect=quota), \
                patch("backend.assistant.answer_chat", return_value={"answer": "Готово", "quota": {"remaining": 40}}):
            ChatStream(service, "Проверка", {}, lease=lease).write(handler)
        self.assertNotIn(b"event: done", handler.wfile.getvalue())
        self.assertIn(b"event: error", handler.wfile.getvalue())
        runtime.finish.assert_called_once_with(True)
        lease.release.assert_called_once()

    def test_disconnect_during_done_keeps_committed_result(self):
        class Writer(io.BytesIO):
            def write(self, data):
                if b"event: done" in data:
                    raise BrokenPipeError("fixture client left")
                return super().write(data)
        service, handler, lease, runtime, events = self.fixture(writer=Writer())
        with patch("backend.assistant.public_quota", return_value={"remaining": 50}), \
                patch("backend.assistant.answer_chat", return_value={"answer": "Готово"}):
            ChatStream(service, "Проверка", {}, lease=lease).write(handler)
        runtime.finish.assert_called_once_with(True)
        lease.release.assert_called_once()

    def test_header_failure_releases_runtime_and_lease(self):
        service, handler, lease, runtime, events = self.fixture()
        handler.end_headers.side_effect = BrokenPipeError("fixture client left")
        with patch("backend.assistant.answer_chat") as answer:
            ChatStream(service, "Проверка", {}, lease=lease).write(handler)
        answer.assert_not_called()
        self.assertEqual(events, [("finish", False), ("lease", None)])

    def test_failure_rolls_back_before_unlocking_and_cleanup_failure_is_contained(self):
        service, handler, lease, runtime, events = self.fixture()
        runtime.finish.side_effect = RuntimeError("fixture rollback failure")
        with patch("backend.assistant.public_quota", return_value={"remaining": 50}), \
                patch("backend.assistant.answer_chat", side_effect=DomainError(502, "Ошибка модели")):
            ChatStream(service, "Проверка", {}, lease=lease).write(handler)
        runtime.finish.assert_called_once_with(False)
        lease.release.assert_called_once()
        self.assertIn(b"event: error", handler.wfile.getvalue())


class ChatInputTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def test_malformed_images_and_context_are_client_errors_before_model(self):
        owner, _ = self.account("invalid-chat-input")
        payloads = [
            {"images": [{"name": "a.png", "mime": "image/png", "content": value}]}
            for value in (None, 1, True, [], {})
        ] + [
            {"context": {"entity": value, "id": "fixture"}}
            for value in ([], {}, True, None)
        ]
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-not-real"), \
                patch("backend.assistant.query_model") as model:
            for payload in payloads:
                with self.subTest(payload=payload):
                    status, result = self.call("/assistant/chat", "POST", {"text": "Проверка", **payload}, owner)
                    self.assertEqual(status, 400, result)
        model.assert_not_called()

    def test_confirmation_and_dismissal_require_post(self):
        owner, _ = self.account("assistant-methods")
        with patch("backend.assistant.confirm") as confirm:
            for path in ("confirm", "dismiss", "undo", "chat", "stream"):
                for method in ("GET", "PATCH", "DELETE"):
                    with self.subTest(path=path, method=method):
                        status, result = self.call("/assistant/" + path, method, {"id": "fixture"}, owner)
                        self.assertEqual(status, 405, result)
        confirm.assert_not_called()


@unittest.skipUnless(os.getenv("SMETRA_TEST_ADMIN_URL"), "requires disposable PostgreSQL")
class PostgresPoolPressureTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "DATABASE_URL": os.environ["SMETRA_TEST_ADMIN_URL"],
            "SMETRA_LOCAL_POSTGRES": "1", "SMETRA_DB_POOL_MAX": "2",
            "REDIS_ENABLED": "0",
        })
        self.env.start()
        self.pools = patch.dict(postgres._POOLS, {}, clear=True)
        self.pools.start()
        import uuid
        self.key = "stability:" + uuid.uuid4().hex

    def tearDown(self):
        try:
            con = postgres.Connection()
            try:
                con.execute("DELETE FROM rate_limits WHERE key=?", (
                    hashlib.sha256(self.key.encode()).hexdigest(),
                ))
            finally:
                con.close()
        finally:
            for pool in list(postgres._POOLS.values()):
                pool.close()
            self.pools.stop()
            self.env.stop()

    def test_two_requests_do_not_exhaust_the_pool_during_redis_outage(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        barrier = Barrier(2)

        def request():
            con = postgres.Connection()
            try:
                barrier.wait(timeout=5)
                Handler.throttle(SimpleNamespace(_request_db=con), self.key, 10, 60)
                return con.execute("SELECT 1").fetchone()[0]
            finally:
                con.close()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: request(), range(2)))
        self.assertEqual(results, [1, 1])

    def test_concurrent_fallback_limit_is_atomic(self):
        from concurrent.futures import ThreadPoolExecutor

        def request(_):
            con = postgres.Connection()
            try:
                return postgres.throttle(self.key, 10, 60, 100, connection=con)
            finally:
                con.close()
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(request, range(100)))
        self.assertEqual(sum(results), 10)

    def test_fallback_does_not_commit_the_callers_transaction(self):
        import psycopg

        con = postgres.Connection()
        try:
            con.execute("BEGIN")
            self.assertTrue(postgres.throttle(self.key, 10, 60, 100, connection=con))
            hashed = hashlib.sha256(self.key.encode()).hexdigest()
            with psycopg.connect(os.environ["SMETRA_TEST_ADMIN_URL"], autocommit=True) as observer:
                self.assertIsNone(observer.execute(
                    "SELECT count FROM smetra.rate_limits WHERE key=%s", (hashed,),
                ).fetchone())
            con.execute("ROLLBACK")
            self.assertIsNone(con.execute("SELECT count FROM rate_limits WHERE key=?", (hashed,)).fetchone())
        finally:
            con.close()


    @unittest.skipUnless(os.getenv("SMETRA_TEST_RUNTIME_URL"), "requires limited runtime role")
    def test_stream_result_is_visible_to_another_connection_before_done(self):
        import secrets
        import time
        import uuid
        import psycopg
        from backend.business import transaction

        uid, wid, cid = (uuid.uuid4().hex for _ in range(3))
        session = secrets.token_hex(32)
        admin_url = os.environ["SMETRA_TEST_ADMIN_URL"]
        with psycopg.connect(admin_url, autocommit=True) as admin:
            try:
                admin.execute(
                    "INSERT INTO smetra.users(id,email,password_hash,name,created_at) VALUES(%s,%s,'fixture','QA',0)",
                    (uid, uid + "@test.invalid"),
                )
                admin.execute("INSERT INTO smetra.workspaces(id,owner_id,name,created_at) VALUES(%s,%s,'QA',0)", (wid, uid))
                admin.execute("INSERT INTO smetra.workspace_members VALUES(%s,%s,'owner')", (wid, uid))
                admin.execute(
                    "INSERT INTO smetra.sessions VALUES(%s,%s,%s,%s)",
                    (uuid.uuid4().hex, uid, session, int(time.time()) + 3600),
                )
                admin.execute(
                    "INSERT INTO smetra.clients(id,workspace_id,name,created_at,updated_at) VALUES(%s,%s,'Before',0,0)",
                    (cid, wid),
                )
                with patch.dict(os.environ, RUNTIME_DATABASE_URL=os.environ["SMETRA_TEST_RUNTIME_URL"]):
                    runtime = postgres.Connection(runtime=True)
                runtime.scope(session, wid)
                service = SimpleNamespace(con=runtime, runtime_connection=runtime)
                observed = []

                class Writer(io.BytesIO):
                    def write(self, data):
                        if b"event: done" in data:
                            observed.append(admin.execute(
                                "SELECT name FROM smetra.clients WHERE id=%s", (cid,),
                            ).fetchone()[0])
                        return super().write(data)

                handler = SimpleNamespace(
                    wfile=Writer(), request_id="pg-stream-fixture",
                    send_response=Mock(), send_header=Mock(), end_headers=Mock(),
                )

                def answer(*args, **kwargs):
                    with transaction(runtime):
                        runtime.execute("UPDATE clients SET name='After' WHERE id=?", (cid,))
                    return {"answer": "Готово", "quota": {"remaining": 40}}

                try:
                    with patch("backend.assistant.public_quota", return_value={"remaining": 50}), \
                            patch("backend.assistant.answer_chat", side_effect=answer):
                        ChatStream(service, "Проверка", {}).write(handler)
                    self.assertEqual(observed, ["After"])
                    self.assertIsNone(service.runtime_connection)
                finally:
                    runtime.close()
            finally:
                admin.execute("DELETE FROM smetra.workspaces WHERE id=%s", (wid,))
                admin.execute("DELETE FROM smetra.users WHERE id=%s", (uid,))
