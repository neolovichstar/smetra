"""Regression proof for monetary history, legacy editing and input boundaries."""
import datetime as dt
import io
import sqlite3
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.app import ApiError, Handler
from tests import test_assistant_finance as finance
from tests import test_business


class JsonBoundaryTests(unittest.TestCase):
    def test_overflowing_numbers_and_lone_surrogates_are_client_errors(self):
        for body in (b'{"unused":1e999}', b'{"nested":[-1e999]}', b'{"name":"\\ud800"}', b'{"\\udfff":0}'):
            with self.subTest(body=body):
                handler = SimpleNamespace(_body_length=len(body), headers={"Content-Type": "application/json"}, rfile=io.BytesIO(body))
                with self.assertRaises(ApiError) as error:
                    Handler.body(handler)
                self.assertEqual(error.exception.status, 400)
        body = '{"name":"Иван 👋"}'.encode()
        handler = SimpleNamespace(_body_length=len(body), headers={"Content-Type": "application/json"}, rfile=io.BytesIO(body))
        self.assertEqual(Handler.body(handler)["name"], "Иван 👋")

    def test_database_lock_failures_are_retryable_and_leave_no_nested_boundary(self):
        import psycopg
        from backend.postgres import Connection
        from backend.service_errors import DatabaseBusyError
        con = Connection.__new__(Connection)
        con.runtime, con.scoped, con.nested = True, True, False
        con.schema, con.lock_key, con.lock_scopes = "smetra", 123, ()
        con.raw = Mock()
        def execute(sql, *args):
            if "pg_advisory" in sql:
                raise psycopg.errors.LockNotAvailable("fixture contention")
            return Mock()
        con.raw.execute.side_effect = execute
        with self.assertRaises(DatabaseBusyError):
            con.execute("BEGIN IMMEDIATE")
        self.assertFalse(con.nested)
        con.raw.execute.assert_any_call("ROLLBACK TO SAVEPOINT smetra_write")
        con.raw.execute.assert_any_call("RELEASE SAVEPOINT smetra_write")

    def test_sqlite_busy_is_translated_without_hiding_other_database_errors(self):
        from backend import app
        from backend.service_errors import DatabaseBusyError
        busy = sqlite3.OperationalError("fixture contention")
        busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
        raw = Mock()
        raw.execute.side_effect = busy
        with patch.dict("os.environ", {"DATABASE_URL": "", "VERCEL": "", "VERCEL_ENV": ""}), patch("backend.app.sqlite3.connect", return_value=raw):
            with self.assertRaises(DatabaseBusyError):
                with app.db():
                    self.fail("Busy database was entered")
        raw.close.assert_called_once()


class BackendDataIntegrityTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account
    team = finance.AssistantFinanceTests.team
    quote = finance.AssistantFinanceTests.quote

    def test_legacy_member_edits_preserve_hidden_cost_and_line_identity(self):
        owner, member, _, wid = self.team("legacy-hidden-cost")
        original = self.quote(owner)
        line = self.call("/quotes/" + original["id"], token=member, workspace=wid)[1]["quote"]["items"][0]
        line.pop("line_id")
        line.update(quantity="3", cost_price=1)
        status, result = self.call("/quotes/" + original["id"], "PATCH", {"revision": original["revision"], "items": [line]}, member, wid)
        self.assertEqual(status, 200, result)
        saved = self.call("/quotes/" + original["id"], token=owner)[1]["quote"]
        self.assertEqual(saved["items"][0]["cost_price"], 19763)
        self.assertEqual(saved["internal_cost"], 19763 * 3)
        self.assertEqual(saved["items"][0]["line_id"], original["items"][0]["line_id"])

    def test_invalid_line_id_does_not_crash_or_change_hidden_cost(self):
        owner, member, _, wid = self.team("invalid-hidden-id")
        original = self.quote(owner)
        for bad_id in ([], {}, None):
            with self.subTest(bad_id=bad_id):
                status, result = self.call("/quotes/" + original["id"], "PATCH", {"revision": 1, "items": [{**original["items"][0], "line_id": bad_id}]}, member, wid)
                self.assertEqual(status, 400, result)
        self.assertEqual(self.call("/quotes/" + original["id"], token=owner)[1]["quote"]["internal_cost"], original["internal_cost"])

    def test_ai_provenance_survives_creation_copy_template_and_publication(self):
        owner, owner_id = self.account("ai-copy-integrity")
        self.call("/workspace", token=owner)
        draft_id = str(uuid.uuid4())
        with self.mod.db() as con:
            wid = con.execute("SELECT id FROM workspaces WHERE owner_id=?", (owner_id,)).fetchone()[0]
            con.execute("INSERT INTO ai_usage(id,workspace_id,user_id,action,model,status,created_at) VALUES(?,?,?,'estimate_draft','fixture','succeeded',?)",
                        (draft_id, wid, owner_id, self.mod.now()))
        result = self.call("/quotes", "POST", {"title": "AI", "client": "Client", "ai_draft_usage_id": draft_id,
                          "items": [{"name": "Work", "unit_price": 10000}]}, owner)
        self.assertEqual(result[0], 201, result)
        quote = result[1]["quote"]
        self.assertEqual(quote["ai_generated"], 1)
        copied = self.call("/quotes/" + quote["id"] + "/copy", "POST", {}, owner)
        self.assertEqual(copied[1]["quote"]["ai_generated"], 1)
        template = self.call("/quotes/" + quote["id"] + "/template", "POST", {}, owner)[1]["id"]
        self.assertEqual(self.call("/templates/" + template, "POST", {}, owner)[1]["quote"]["ai_generated"], 1)
        self.assertEqual(self.call("/quotes/" + quote["id"] + "/publish", "POST", {"revision": 1, "review_confirmed": True}, owner)[0], 200)
        self.assertEqual(self.call("/quotes/" + quote["id"] + "/versions", token=owner)[1]["versions"][0]["snapshot"]["ai_generated"], 1)

    def test_unknown_action_and_collection_delete_never_delete_a_record(self):
        owner, _ = self.account("safe-route-integrity")
        quote = self.quote(owner)
        client = self.call("/clients", "POST", {"name": "Client"}, owner)[1]["item"]
        self.assertEqual(self.call("/clients/" + client["id"] + "/typo", "DELETE", token=owner)[0], 404)
        self.assertEqual(self.call("/quotes/" + quote["id"] + "/publish", "DELETE", token=owner)[0], 405)
        for route in ("/clients", "/quotes", "/projects"):
            self.assertEqual(self.call(route, "DELETE", token=owner)[0], 405)
        self.assertEqual(self.call("/clients/" + client["id"], token=owner)[0], 200)
        self.assertEqual(self.call("/quotes/" + quote["id"], token=owner)[0], 200)

    def test_money_retries_compare_normalized_fields_and_use_business_date(self):
        owner, _ = self.account("money-retry-normalized")
        project = self.call("/projects", "POST", {"name": "Order", "amount_kopecks": 100000}, owner)[1]["item"]
        for route, extra in (("receipts", {"stage_id": ""}), ("expenses", {"category": "  Материалы  "})):
            body = {"project_id": project["id"], "amount_kopecks": 1000, "comment": "  Учтено  ", **extra}
            with patch("backend.business.business_date", return_value=dt.date(2026, 12, 1)):
                first = self.call("/" + route, "POST", body, owner, key="normalized-money-" + route)
            second = self.call("/" + route, "POST", body, owner, key="normalized-money-" + route)
            self.assertEqual((first[0], second[0]), (201, 200), (first, second))
            self.assertEqual(first[1]["item"]["payment_date" if route == "receipts" else "expense_date"], "2026-12-01")

    def test_project_and_stage_financial_history_is_preserved(self):
        owner, _ = self.account("financial-history-integrity")
        project = self.call("/projects", "POST", {"name": "Order", "amount_kopecks": 100000}, owner)[1]["item"]
        stage = self.call("/stages", "POST", {"name": "Stage", "project_id": project["id"], "amount_kopecks": 60000}, owner)[1]["item"]
        self.assertEqual(self.call("/receipts", "POST", {"project_id": project["id"], "stage_id": stage["id"], "amount_kopecks": 50000}, owner, key="financial-history-payment")[0], 201)
        for update in ({"amount_kopecks": 49999}, {"currency": "USD"}):
            self.assertEqual(self.call("/projects/" + project["id"], "PATCH", {"revision": project["revision"], **update}, owner)[0], 409)
        self.assertEqual(self.call("/stages/" + stage["id"], "PATCH", {"revision": stage["revision"], "amount_kopecks": 49999}, owner)[0], 409)
        self.assertEqual(self.call("/stages/" + stage["id"], "DELETE", token=owner)[0], 409)

    def test_authority_is_revalidated_after_the_write_gate(self):
        from backend.business import Service
        owner, member, member_id, wid = self.team("write-revalidation")
        original = Service.write_access
        revoked = []

        def check(service, managerial=False):
            result = original(service, managerial)
            if service.user["id"] == member_id and not revoked:
                revoked.append(True)
                with self.mod.db() as con:
                    con.execute("UPDATE workspace_members SET role='viewer' WHERE workspace_id=? AND user_id=?", (wid, member_id))
            return result

        with patch.object(Service, "write_access", check):
            result = self.call("/tasks", "POST", {"name": "Must not be created"}, member, wid)
        self.assertEqual(result[0], 403, result)
        self.assertEqual(self.call("/tasks", token=owner)[1]["items"], [])
