"""Public capability, version, export and recipient-identity regressions."""
import concurrent.futures
import io
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from backend.protected_estimates import digest
from tests import test_business


class ProtectedEstimateTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def setUp(self):
        self.mod.RATE.clear()
        label = "protected-" + uuid.uuid4().hex[:10]
        self.owner, self.owner_id = self.account(label)
        self.recipient, self.recipient_id = self.account(label + "-client")
        self.recipient_email = label + "-client@test.invalid"
        with self.mod.db() as con:
            con.execute("UPDATE users SET email_verified_at=? WHERE id=?", (self.mod.now(), self.recipient_id))
        status, result = self.call("/quotes", "POST", {
            "title": "Ремонт квартиры", "client": "Клиент",
            "description": "Не раскрывать эту скрытую технологию", "terms": "Срок выполнения — 30 дней",
            "items": [
                {"name": "Скрытая технология стен", "category": "Отделка", "quantity": "2", "unit": "м²", "unit_price": 10000, "cost_price": 4321, "markup": "20"},
                {"name": "Секретный артикул", "category": "Материалы", "quantity": "3", "unit_price": 20000, "cost_price": 12345},
            ],
        }, self.owner)
        self.assertEqual(status, 201, result)
        self.quote = result["quote"]
        self.legacy_token = self.quote["public_url"].split("quote=")[1]
        status, published = self.call("/quotes/" + self.quote["id"] + "/publish", "POST",
                                      {"revision": self.quote["revision"], "review_confirmed": True}, self.owner)
        self.assertEqual(status, 200, published)
        self.quote = published["quote"]

    def link(self, **changes):
        status, result = self.call("/protected-links", "POST", {
            "quote_id": self.quote["id"], "recipient_name": "Заказчик Иванов",
            "recipient_email": self.recipient_email, **changes,
        }, self.owner)
        self.assertEqual(status, 201, result)
        return result["link"], result["url"].split("#")[1]

    def public(self, action, token, view=None, **data):
        return self.call("/public/protected/" + action, "POST",
                         {"token": token, **({"view_token": view} if view else {}), **data}, raw=action in ("pdf", "xlsx"))

    def opened(self, token, **data):
        status, result = self.public("open", token, **data)
        self.assertEqual(status, 200, result)
        return result["view_token"], result["document"]

    def test_safe_defaults_and_no_secrets_in_database(self):
        link, token = self.link(access_code="private-code")
        view, document = self.opened(token, access_code="private-code")
        self.assertNotIn("items", document)
        self.assertNotIn("description", document)
        self.assertEqual(document["sections"], [{"name": "Отделка", "amount_kopecks": 24000}])
        self.assertEqual(document["amount_kopecks"], 84000)
        self.assertIn("Заказчик Иванов", document["watermark"])
        self.assertNotIn("127.0.0.1", document["watermark"])
        self.assertFalse(document["permissions"]["allow_pdf"])
        self.assertFalse(document["permissions"]["allow_excel"])
        with self.mod.db() as con:
            stored = dict(con.execute("SELECT * FROM protected_quote_links WHERE id=?", (link["id"],)).fetchone())
            views = [dict(row) for row in con.execute("SELECT * FROM protected_quote_views WHERE link_id=?", (link["id"],))]
            events = [dict(row) for row in con.execute("SELECT * FROM protected_quote_events WHERE link_id=?", (link["id"],))]
        stored_json = json.dumps([stored, views, events])
        for secret in (token, view, "private-code", "127.0.0.1"):
            self.assertNotIn(secret, stored_json)
        self.assertEqual(stored["token_hash"], digest(token))
        self.assertEqual(views[0]["token_hash"], digest(view))

    def test_invalid_token_code_expiration_and_revoke(self):
        self.assertEqual(self.public("open", secrets.token_urlsafe(32))[0], 404)
        self.assertEqual(self.public("open", "bad-token")[0], 404)
        link, token = self.link(access_code="secret-code")
        self.assertEqual(self.public("open", token)[0], 401)
        self.assertEqual(self.public("open", token, access_code="wrong-code")[0], 401)
        view, _ = self.opened(token, access_code="secret-code")
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT view_count FROM protected_quote_links WHERE id=?", (link["id"],)).fetchone()[0], 1)
            con.execute("UPDATE protected_quote_links SET expires_at=? WHERE id=?", (self.mod.now() - 1, link["id"]))
        self.assertEqual(self.public("view", token, view)[0], 410)
        other, other_token = self.link()
        self.assertEqual(self.call("/protected-links/" + other["id"], "DELETE", {"revision": other["revision"]}, self.owner)[0], 200)
        self.assertEqual(self.public("open", other_token)[0], 410)

    def test_counter_is_atomic_and_existing_view_refresh_does_not_consume_opening(self):
        link, token = self.link(max_views=2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.public("open", token), range(6)))
        self.assertEqual(sorted(status for status, _ in results), [200, 200, 410, 410, 410, 410], results)
        success = next(result for status, result in results if status == 200)
        for _ in range(3):
            self.assertEqual(self.public("view", token, success["view_token"])[0], 200)
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT view_count FROM protected_quote_links WHERE id=?", (link["id"],)).fetchone()[0], 2)

    def test_permissions_change_and_exports_are_rechecked_on_every_request(self):
        link, token = self.link(settings={"sections_only": False, "show_details": True, "show_quantities": True,
                                           "show_prices": True, "show_materials": True, "allow_pdf": True, "allow_excel": True})
        view, document = self.opened(token)
        self.assertEqual(len(document["items"]), 2)
        self.assertEqual(document["items"][0]["unit_price"], 12000)
        self.assertNotIn("markup", json.dumps(document))
        self.assertEqual(self.public("pdf", token, view)[0], 200)
        self.assertEqual(self.public("xlsx", token, view)[0], 200)
        status, changed = self.call("/protected-links/" + link["id"], "PATCH", {
            "revision": link["revision"], "settings": {"show_quantities": False, "show_prices": False,
                "show_materials": False, "allow_pdf": False, "allow_excel": False},
        }, self.owner)
        self.assertEqual(status, 200, changed)
        document = self.public("view", token, view)[1]["document"]
        self.assertEqual(document["items"], [{"name": "Скрытая технология стен", "category": "Отделка"}])
        for key in ("unit_price", "quantity", "cost_price", "internal_cost", "Секретный артикул"):
            self.assertNotIn(key, json.dumps(document, ensure_ascii=False))
        self.assertEqual(self.public("pdf", token, view)[0], 403)
        self.assertEqual(self.public("xlsx", token, view)[0], 403)

    def test_legacy_and_original_document_routes_cannot_bypass_protection(self):
        self.link()
        for route in ("quote", "file", "document"):
            self.assertEqual(self.call("/public/" + route + "?token=" + self.legacy_token + "&id=anything")[0], 404)
        self.assertEqual(self.call("/quotes/" + self.quote["id"])[0], 401)
        self.assertEqual(self.call("/transfer/quotes?format=xlsx")[0], 401)
        owner = self.call("/quotes/" + self.quote["id"], token=self.owner)[1]["quote"]
        self.assertIsNone(owner["public_url"])
        self.assertEqual(len(owner["items"]), 2)
        self.assertIn("cost_price", owner["items"][0])

    def test_tenant_isolation_and_managerial_permissions(self):
        link, _ = self.link()
        for method, path, data in (("GET", "/protected-links/" + link["id"], None),
                                   ("PATCH", "/protected-links/" + link["id"], {"revision": 1, "settings": {"allow_pdf": True}}),
                                   ("POST", "/protected-links", {"quote_id": self.quote["id"]})):
            self.assertEqual(self.call(path, method, data, self.recipient)[0], 404)
        wid = self.call("/workspace", token=self.owner)[1]["workspace"]["id"]
        with self.mod.db() as con:
            con.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(?,?,'member')", (wid, self.recipient_id))
        self.assertEqual(self.call("/protected-links/" + link["id"], token=self.recipient, workspace=wid)[0], 403)

    def test_decision_requires_verified_named_recipient_and_is_idempotent(self):
        link, token = self.link()
        view, document = self.opened(token)
        body = {"token": token, "view_token": view, "action": "approved", "confirmation": True,
                "snapshot_sha256": document["snapshot_sha256"], "permissions_revision": document["permissions_revision"]}
        self.assertEqual(self.call("/public/protected/respond", "POST", body)[0], 401)
        self.assertEqual(self.call("/public/protected/respond", "POST", body, self.owner)[0], 403)
        with self.mod.db() as con:
            con.execute("UPDATE users SET email_verified_at=NULL WHERE id=?", (self.recipient_id,))
        self.assertEqual(self.call("/public/protected/respond", "POST", body, self.recipient)[0], 403)
        with self.mod.db() as con:
            con.execute("UPDATE users SET email_verified_at=? WHERE id=?", (self.mod.now(), self.recipient_id))
        status, accepted = self.call("/public/protected/respond", "POST", body, self.recipient)
        self.assertEqual(status, 200, accepted)
        replay = self.call("/public/protected/respond", "POST", body, self.recipient)
        self.assertEqual(replay[0], 200, replay)
        self.assertTrue(replay[1]["replayed"])
        self.assertEqual(self.call("/public/protected/respond", "POST", {**body, "action": "rejected"}, self.recipient)[0], 409)
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM protected_quote_decisions WHERE link_id=?", (link["id"],)).fetchone()[0], 1)
        self.assertEqual(self.call("/quotes/" + self.quote["id"], token=self.owner)[1]["quote"]["approval_state"], "approved")

    def test_old_version_stays_immutable_and_cannot_accept_a_changed_draft(self):
        _, token = self.link()
        view, document = self.opened(token)
        current = self.call("/quotes/" + self.quote["id"], token=self.owner)[1]["quote"]
        self.assertEqual(self.call("/quotes/" + self.quote["id"], "PATCH", {"revision": current["revision"], "title": "Совсем другое предложение"}, self.owner)[0], 200)
        self.assertEqual(self.public("view", token, view)[1]["document"]["title"], "Ремонт квартиры")
        result = self.call("/public/protected/respond", "POST", {
            "token": token, "view_token": view, "action": "approved", "confirmation": True,
            "snapshot_sha256": document["snapshot_sha256"], "permissions_revision": document["permissions_revision"],
        }, self.recipient)
        self.assertEqual(result[0], 409, result)

    def test_code_change_and_token_reissue_invalidate_old_views(self):
        link, token = self.link()
        view, _ = self.opened(token)
        status, changed = self.call("/protected-links/" + link["id"], "PATCH", {"revision": 1, "access_code": "new-code"}, self.owner)
        self.assertEqual(status, 200, changed)
        self.assertEqual(self.public("view", token, view)[0], 401)
        view, _ = self.opened(token, access_code="new-code")
        status, rotated = self.call("/protected-links/" + link["id"] + "/reissue", "POST", {"revision": changed["link"]["revision"]}, self.owner)
        self.assertEqual(status, 200, rotated)
        self.assertEqual(self.public("view", token, view)[0], 404)
        self.opened(rotated["url"].split("#")[1], access_code="new-code")

    def test_exports_contain_only_redacted_data_and_printed_watermark(self):
        from backend.protected_estimate_exports import pdf, xlsx
        from openpyxl import load_workbook
        from pypdf import PdfReader
        _, token = self.link()
        _, document = self.opened(token)
        text = " ".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf(document))).pages)
        self.assertIn("Итого", text)
        self.assertIn("Заказчик Иванов", text)
        for secret in ("Скрытая технология стен", "Секретный артикул", "4321", "12345"):
            self.assertNotIn(secret, text)
        workbook = load_workbook(io.BytesIO(xlsx({**document, "title": "=HYPERLINK(\"https://evil.test\")"})))
        self.assertEqual(len(workbook.worksheets), 1)
        self.assertEqual(workbook.active["A2"].data_type, "s")
        self.assertNotIn("Секретный артикул", str(list(workbook.active.values)))

    def test_link_creation_retry_and_audit_history(self):
        body = {"quote_id": self.quote["id"], "recipient_email": self.recipient_email}
        first = self.call("/protected-links", "POST", body, self.owner, key="protected-create-key")
        second = self.call("/protected-links", "POST", body, self.owner, key="protected-create-key")
        self.assertEqual((first[0], second[0]), (201, 200))
        self.assertEqual(first[1]["link"]["id"], second[1]["link"]["id"])
        self.assertNotIn("url", second[1])
        link = first[1]["link"]
        detail = self.call("/protected-links/" + link["id"], token=self.owner)
        self.assertEqual(detail[1]["events"][0]["kind"], "created")

    def test_only_total_has_no_section_item_quantity_or_price_payload(self):
        _, token = self.link(settings={"sections_only": False, "show_details": False,
                                       "show_quantities": True, "show_prices": True, "show_materials": True})
        view, document = self.opened(token)
        self.assertNotIn("sections", document)
        self.assertNotIn("items", document)
        self.assertEqual(document["amount_kopecks"], 84000)
        self.assertEqual(self.public("pdf", token, view)[0], 403)
        self.assertEqual(self.call("/protected-links", "POST", {"quote_id": self.quote["id"], "settings": {"allow_pdf": "false"}}, self.owner)[0], 400)

    def test_view_capabilities_are_bound_to_one_link_and_needed_for_downloads(self):
        _, first = self.link(settings={"allow_pdf": True})
        _, second = self.link(settings={"allow_pdf": True})
        view, _ = self.opened(first)
        self.assertEqual(self.public("pdf", second, view)[0], 401)
        self.assertEqual(self.public("pdf", first)[0], 401)
        self.assertEqual(self.public("view", first, secrets.token_urlsafe(32))[0], 401)

    def test_access_code_guess_limit_is_durable_and_does_not_increment_views(self):
        link, token = self.link(access_code="guess-resistant")
        statuses = [self.public("open", token, access_code="wrong-value")[0] for _ in range(11)]
        self.assertEqual(statuses, [401] * 10 + [429])
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT view_count FROM protected_quote_links WHERE id=?", (link["id"],)).fetchone()[0], 0)

    def test_request_changes_and_rejection_are_version_bound_and_timestamped(self):
        for action in ("changes_requested", "rejected"):
            link, token = self.link()
            view, document = self.opened(token)
            body = {"token": token, "view_token": view, "action": action, "comment": "Уточнить состав",
                    "confirmation": True, "snapshot_sha256": document["snapshot_sha256"], "permissions_revision": 1}
            if action == "changes_requested":
                self.assertEqual(self.call("/public/protected/respond", "POST", {**body, "comment": ""}, self.recipient)[0], 400)
            status, result = self.call("/public/protected/respond", "POST", body, self.recipient)
            self.assertEqual(status, 200, result)
            detail = self.call("/protected-links/" + link["id"], token=self.owner)[1]
            self.assertEqual(detail["decision"]["action"], action)
            self.assertIsInstance(detail["decision"]["created_at"], int)

    def test_state_is_preserved_across_a_fresh_backend_process(self):
        link, token = self.link()
        view, _ = self.opened(token)
        script = r'''
import io,json,sys
from backend.app import Handler,db,migrate
from backend.business import Service,DomainError
data=json.load(sys.stdin)
migrate()
with db() as con:
 h=Handler.__new__(Handler)
 raw=json.dumps(data).encode()
 h.headers={"Content-Type":"application/json"}
 h.rfile=io.BytesIO(raw)
 h._body_length=len(raw)
 h.client_address=("127.0.0.1",0)
 h._request_db=con
 try:
  status,payload=Service(h,con,"http://fixture").handle("POST","/api/public/protected/view",{})
  print(json.dumps({"status":status,"title":payload["document"]["title"]}))
 except DomainError as error:
  print(json.dumps({"status":error.status}))
'''
        def cold_start():
            process = subprocess.run([sys.executable, "-c", script], input=json.dumps({"token": token, "view_token": view}),
                                     text=True, capture_output=True, timeout=20, cwd=Path(__file__).resolve().parents[1])
            self.assertEqual(process.returncode, 0, process.stderr)
            return json.loads(process.stdout)
        self.assertEqual(cold_start(), {"status": 200, "title": "Ремонт квартиры"})
        self.assertEqual(self.call("/protected-links/" + link["id"], "DELETE", {"revision": 1}, self.owner)[0], 200)
        self.assertEqual(cold_start(), {"status": 410})


@unittest.skipUnless(os.getenv("SMETRA_TEST_ADMIN_URL") and os.getenv("SMETRA_TEST_RUNTIME_URL"),
                     "requires disposable PostgreSQL with protected-estimate migration 72")
class ProtectedEstimatePostgresTests(ProtectedEstimateTests):
    @classmethod
    def setUpClass(cls):
        cls.pg_environment = patch.dict(os.environ, {
            "DATABASE_URL": os.environ["SMETRA_TEST_ADMIN_URL"],
            "RUNTIME_DATABASE_URL": os.environ["SMETRA_TEST_RUNTIME_URL"],
            "SMETRA_LOCAL_POSTGRES": "1",
        })
        cls.pg_environment.start()
        try:
            test_business.BusinessFlows.setUpClass.__func__(cls)
        except BaseException:
            cls.pg_environment.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            test_business.BusinessFlows.tearDownClass.__func__(cls)
        finally:
            cls.pg_environment.stop()

    def setUp(self):
        with self.mod.db() as con:
            con.execute("DELETE FROM rate_limits")
        super().setUp()

    def tearDown(self):
        with self.mod.db() as con:
            con.execute("DELETE FROM quotes WHERE user_id IN (?,?)", (self.owner_id, self.recipient_id))
            con.execute("DELETE FROM workspaces WHERE owner_id IN (?,?)", (self.owner_id, self.recipient_id))
            con.execute("DELETE FROM users WHERE id IN (?,?)", (self.owner_id, self.recipient_id))

    def test_database_rls_restricts_rows_roles_and_public_grants(self):
        import hashlib
        from backend.postgres import Connection
        link, _ = self.link()
        with self.mod.db() as con:
            wid = con.execute("SELECT workspace_id FROM protected_quote_links WHERE id=?", (link["id"],)).fetchone()[0]
            con.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(?,?,'member')", (wid, self.recipient_id))
            for table in ("protected_quote_links", "protected_quote_views", "protected_quote_events", "protected_quote_decisions"):
                flags = con.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=?::regclass", ("smetra." + table,)).fetchone()
                self.assertEqual((flags["relrowsecurity"], flags["relforcerowsecurity"]), (True, True))
                self.assertFalse(con.execute("SELECT has_table_privilege('anon',?,'SELECT')", ("smetra." + table,)).fetchone()[0])
        runtime = Connection(runtime=True)
        try:
            runtime.scope(hashlib.sha256(self.recipient.encode()).hexdigest(), wid)
            self.assertEqual(runtime.execute("SELECT count(*) FROM protected_quote_links WHERE workspace_id=?", (wid,)).fetchone()[0], 0)
            self.assertEqual(runtime.execute("SELECT count(*) FROM protected_quote_events WHERE workspace_id=?", (wid,)).fetchone()[0], 0)
        finally:
            runtime.finish(False)

    def test_database_rejects_cross_workspace_quote_and_audit_references(self):
        link, _ = self.link()
        workspace_status, workspace = self.call("/workspace", token=self.recipient)
        self.assertEqual(workspace_status, 200, workspace)
        other_workspace = workspace["workspace"]["id"]
        with self.mod.db() as con:
            source = dict(con.execute("SELECT * FROM protected_quote_links WHERE id=?", (link["id"],)).fetchone())
        # Even the maintenance connection cannot create a cross-company reference.
        with self.assertRaises(sqlite3.IntegrityError), self.mod.db() as con:
            invalid = {**source, "id": uuid.uuid4().hex, "workspace_id": other_workspace,
                       "token_hash": digest(secrets.token_urlsafe(32))}
            keys = tuple(invalid)
            con.execute(f"INSERT INTO protected_quote_links({','.join(keys)}) VALUES({','.join('?' for _ in keys)})",
                        tuple(invalid.values()))
        with self.assertRaises(sqlite3.IntegrityError), self.mod.db() as con:
            con.execute("INSERT INTO protected_quote_events(id,workspace_id,link_id,kind,created_at) VALUES(?,?,?,?,?)",
                        (uuid.uuid4().hex, other_workspace, link["id"], "opened", self.mod.now()))
