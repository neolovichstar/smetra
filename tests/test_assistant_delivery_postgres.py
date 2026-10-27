"""PostgreSQL/RLS checks for the handoff from the browser transaction to a worker."""
import io
import json
import os
import secrets
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from backend import assistant_jobs
from backend.assistant_delivery import DurableChatStream
from backend.business import Service, transaction
from backend.postgres import Connection, _POOLS
from backend.redis_infra import Lease


def tearDownModule():
    pools = list(_POOLS.values())
    _POOLS.clear()
    for pool in pools:
        pool.close()


@unittest.skipUnless(os.getenv("SMETRA_TEST_ADMIN_URL") and os.getenv("SMETRA_TEST_RUNTIME_URL"),
                     "requires isolated PostgreSQL queue schema and limited runtime role")
class DurableChatPostgresTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, DATABASE_URL=os.environ["SMETRA_TEST_ADMIN_URL"],
                                 RUNTIME_DATABASE_URL=os.environ["SMETRA_TEST_RUNTIME_URL"],
                                 SMETRA_LOCAL_POSTGRES="1")
        environment.start()
        self.addCleanup(environment.stop)
        self.admin = Connection()
        self.addCleanup(self.admin.close)
        self.addCleanup(self.clean)
        self.uid, self.wid, self.job = (str(uuid.uuid4()) for _ in range(3))
        self.session = secrets.token_hex(32)
        moment = int(time.time())
        self.admin.execute("INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES(?,?,'unused','Queue QA',?,?)",
                           (self.uid, self.uid + "@test.invalid", moment, moment))
        self.admin.execute("INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)",
                           (str(uuid.uuid4()), self.uid, self.session, moment + 3600))
        self.admin.execute("INSERT INTO workspaces(id,owner_id,name,created_at) VALUES(?,?,'Queue QA',?)", (self.wid, self.uid, moment))
        self.admin.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(?,?,'owner')", (self.wid, self.uid))
        self.admin.execute("INSERT INTO assistant_jobs(id,workspace_id,user_id,session_hash,request_key,request_hash,prompt,quota_key,next_attempt_at,created_at,updated_at) VALUES(?,?,?,?,?,?,'Проверка очереди','fixture',0,?,?)",
                           (self.job, self.wid, self.uid, self.session, secrets.token_hex(16), "fixture", moment, moment))

    def clean(self):
        if hasattr(self, "wid"):
            self.admin.execute("DELETE FROM workspaces WHERE id=?", (self.wid,))
            self.admin.execute("DELETE FROM users WHERE id=?", (self.uid,))

    def service(self):
        handler = SimpleNamespace(wfile=io.BytesIO(), request_id="pg-durable-fixture", headers={},
                                  send_response=lambda *_: None, send_header=lambda *_: None, end_headers=lambda: None)
        service = Service(handler, self.admin, "https://example.test")
        service.user = self.admin.execute("SELECT * FROM users WHERE id=?", (self.uid,)).fetchone()
        service.wid, service.role = self.wid, "owner"
        runtime = Connection(runtime=True)
        runtime.scope(self.session, self.wid)
        service.con = service.runtime_connection = runtime
        return service, handler

    def test_handoff_releases_initial_runtime_and_commits_job_and_messages_once(self):
        def answer(service, prompt, **callbacks):
            result = {"answer": "Сохранено один раз", "actions": [], "quota": {"remaining": 100}}
            with transaction(service.con):
                callbacks["on_commit"](result)
                service.con.execute("INSERT INTO assistant_messages(id,workspace_id,user_id,role,content,created_at) VALUES(?,?,?,'assistant',?,?)",
                                    (str(uuid.uuid4()), self.wid, self.uid, result["answer"], int(time.time()) * 1000))
            return result

        service, handler = self.service()
        with patch("backend.assistant_jobs.assistant.answer_chat", side_effect=answer) as model, patch("backend.redis_infra.acquire_lock", side_effect=lambda *args, **kwargs: Lease(None, "", "")):
            DurableChatStream(service, self.job).write(handler)
            self.assertIsNone(service.runtime_connection)
            replay, replay_handler = self.service()
            DurableChatStream(replay, self.job).write(replay_handler)
            self.assertEqual(model.call_count, 1)
            self.assertIn(b"event: done", replay_handler.wfile.getvalue())
        row = self.admin.execute("SELECT status,result FROM assistant_jobs WHERE id=?", (self.job,)).fetchone()
        self.assertEqual(row["status"], "completed")
        self.assertEqual(json.loads(row["result"])["answer"], "Сохранено один раз")
        self.assertEqual(self.admin.execute("SELECT count(*) FROM assistant_messages WHERE workspace_id=?", (self.wid,)).fetchone()[0], 1)

    def test_revoked_membership_cannot_commit_a_pending_answer(self):
        def revoked(service, prompt, **callbacks):
            self.admin.execute("DELETE FROM workspace_members WHERE workspace_id=? AND user_id=?", (self.wid, self.uid))
            with transaction(service.con):
                callbacks["on_commit"]({"answer": "Не сохранять", "actions": []})
            return {"answer": "Не сохранять"}

        service, handler = self.service()
        with patch("backend.assistant_jobs.assistant.answer_chat", side_effect=revoked), patch("backend.redis_infra.acquire_lock", side_effect=lambda *args, **kwargs: Lease(None, "", "")):
            DurableChatStream(service, self.job).write(handler)
        row = self.admin.execute("SELECT status FROM assistant_jobs WHERE id=?", (self.job,)).fetchone()
        self.assertEqual(row["status"], "failed")
        self.assertNotIn(b"event: done", handler.wfile.getvalue())
        self.assertEqual(self.admin.execute("SELECT count(*) FROM assistant_messages WHERE workspace_id=?", (self.wid,)).fetchone()[0], 0)

    def test_scoped_runtime_cannot_claim_another_users_job(self):
        outsider, wid = str(uuid.uuid4()), str(uuid.uuid4())
        moment = int(time.time())
        session = secrets.token_hex(32)
        self.admin.execute("INSERT INTO users(id,email,password_hash,name,created_at) VALUES(?,?,'unused','Other',?)", (outsider, outsider + "@test.invalid", moment))
        self.admin.execute("INSERT INTO workspaces(id,owner_id,name,created_at) VALUES(?,?,'Other',?)", (wid, outsider, moment))
        self.admin.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(?,?,'owner')", (wid, outsider))
        self.admin.execute("INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)", (str(uuid.uuid4()), outsider, session, moment + 3600))
        runtime = Connection(runtime=True)
        try:
            runtime.scope(session, wid)
            self.assertIsNone(assistant_jobs.claim(runtime, self.job))
            runtime.finish(True)
        finally:
            runtime.close()
            self.admin.execute("DELETE FROM workspaces WHERE id=?", (wid,))
            self.admin.execute("DELETE FROM users WHERE id=?", (outsider,))
        self.assertEqual(self.admin.execute("SELECT status FROM assistant_jobs WHERE id=?", (self.job,)).fetchone()["status"], "queued")
