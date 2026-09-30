import concurrent.futures
import base64
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from backend.business import DomainError, Service, calculate


class CalculationTests(unittest.TestCase):
    def test_construction_formula_is_bounded_and_safe(self):
        from backend.construction_math import evaluate, zone_values

        values = zone_values(5, 4, 3, 2)
        self.assertEqual(str(evaluate('area - openings', values)), '18.0000')
        for expression in ('__import__("os")', '2 ** 1000', '1 / 0', '-1', 'missing'):
            with self.subTest(expression=expression), self.assertRaises(DomainError):
                evaluate(expression, values)

    def test_decimal_rounding_discount_markup_tax_and_optional(self):
        items, total, cost = calculate(
            [
                {
                    "name": "Work",
                    "quantity": "1.5",
                    "unit_price": 10001,
                    "cost_price": 4000,
                    "markup": "10",
                    "discount": "5",
                    "tax": "20",
                },
                {
                    "name": "Extra",
                    "quantity": "1",
                    "unit_price": 99900,
                    "optional": True,
                    "included": False,
                },
            ]
        )
        self.assertEqual(items[0]["subtotal"], 18812)
        self.assertEqual(total, 18812)
        self.assertEqual(cost, 6000)

    def test_rejects_nonfinite_bool_overflow_and_empty(self):
        for value in ("NaN", "Infinity", "-1", "0", "0.00001", True):
            with self.subTest(value=value), self.assertRaises(DomainError):
                calculate([{"name": "x", "quantity": value, "unit_price": 100}])
        for items in (
            [],
            [{"name": "x", "unit_price": True}],
            [{"name": "x", "quantity": "1000000", "unit_price": 10000000000}],
        ):
            with self.assertRaises(DomainError):
                calculate(items)


class BusinessFlows(unittest.TestCase):
    def test_construction_measure_to_quote_and_workspace_isolation(self):
        token, _ = self.account('builder-' + os.urandom(4).hex())
        other, _ = self.account('other-builder-' + os.urandom(4).hex())
        status, result = self.call('/construction/objects', 'POST', {'name': 'Квартира'}, token)
        self.assertEqual(status, 201, result)
        obj = result['object']['id']
        status, result = self.call(f'/construction/objects/{obj}/zones', 'POST', {
            'name': 'Кухня', 'length': '5', 'width': '4', 'height': '2.8',
        }, token)
        self.assertEqual(status, 201, result)
        zone = result['zone']['id']
        self.assertEqual(result['calculated']['area'], '20')
        status, result = self.call(f'/construction/objects/{obj}/quantities', 'POST', {
            'zone_id': zone, 'title': 'Покраска', 'formula': 'area', 'unit_price': 15000,
        }, token)
        self.assertEqual(status, 201, result)
        work = result['quantity']
        self.assertEqual(work['planned_total_kopecks'], 300000)
        status, result = self.call(f'/construction/objects/{obj}/quantities', 'POST', {
            'parent_work_id': work['id'], 'kind': 'material', 'title': 'Краска',
            'unit': 'л', 'consumption_rate': '0.2', 'waste_percent': 10,
            'unit_price': 80000,
        }, token)
        self.assertEqual(status, 201, result)
        self.assertEqual(result['quantity']['quantity'], '4.4000')
        status, result = self.call(f'/construction/objects/{obj}/facts', 'POST', {
            'quantity_id': work['id'], 'quantity': '8',
        }, token)
        self.assertEqual(status, 201, result)
        status, result = self.call(f'/construction/objects/{obj}', token=token)
        self.assertEqual(status, 200, result)
        self.assertEqual(result['totals']['actual_kopecks'], 120000)
        status, result = self.call(f'/construction/objects/{obj}/quote', 'POST', {}, token)
        self.assertEqual(status, 201, result)
        self.assertEqual(result['quote']['amount_kopecks'], 652000)
        status, recalculated = self.call(f'/construction/objects/{obj}/zones/{zone}', 'PATCH', {
            'width': '480', 'dimension_unit': 'см',
        }, token)
        self.assertEqual(status, 200, recalculated)
        self.assertIsNone(recalculated['object']['quote_id'])
        amounts = {row['id']: row['quantity'] for row in recalculated['quantities']}
        self.assertEqual(amounts[work['id']], '24.0000')
        self.assertIn('5.2800', amounts.values())
        status, updated = self.call(f'/construction/objects/{obj}/quantities/{work["id"]}', 'PATCH', {
            'unit_price': 16000,
        }, token)
        self.assertEqual(status, 200, updated)
        self.assertEqual(next(row for row in updated['quantities'] if row['id'] == work['id'])['planned_total_kopecks'], 384000)
        status, sheet = self.call(f'/construction/objects/{obj}/xlsx', token=token, raw=True)
        self.assertEqual(status, 200)
        self.assertTrue(sheet.startswith(b'PK'))
        status, result = self.call('/files', 'POST', {
            'construction_id': obj, 'name': 'замер.txt',
            'content': base64.b64encode('Кухня 5 × 4 м'.encode()).decode(),
        }, token)
        self.assertEqual(status, 201, result)
        status, result = self.call('/files?construction_id=' + obj, token=token)
        self.assertEqual(status, 200, result)
        self.assertEqual(len(result['items']), 1)
        status, _ = self.call(f'/construction/objects/{obj}', token=other)
        self.assertEqual(status, 404)
        status, _ = self.call('/files?construction_id=' + obj, token=other)
        self.assertEqual(status, 404)

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.environ = dict(os.environ)
        os.environ["UPLOAD_DIR"] = str(Path(cls.temp.name) / "uploads")
        os.environ.update(
            DB_PATH=str(Path(cls.temp.name) / "business.sqlite3"),
            PORT="0",
            PUBLIC_ORIGIN="http://localhost:0",
        )
        os.environ.pop("SMTP_HOST", None)
        spec = importlib.util.spec_from_file_location(
            "business_app", Path(__file__).resolve().parents[1] / "backend/app.py"
        )
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        cls.mod.migrate()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), cls.mod.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.server.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()
        os.environ.clear()
        os.environ.update(cls.environ)

    def setUp(self):
        self.mod.RATE.clear()

    def call(
        self,
        path,
        method="GET",
        data=None,
        token=None,
        workspace=None,
        key=None,
        raw=False,
    ):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if workspace:
            headers["X-Workspace-Id"] = workspace
        if key:
            headers["Idempotency-Key"] = key
        req = urllib.request.Request(
            self.base + "/api" + path,
            json.dumps(data).encode() if data is not None else None,
            headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, response.read() if raw else json.load(response)
        except urllib.error.HTTPError as response:
            with response:
                return response.code, json.load(response)

    def account(self, name):
        code, result = self.call(
            "/auth/register",
            "POST",
            {
                "email": name + "@test.invalid",
                "name": name,
                "password": "secure twelve password",
            },
        )
        self.assertEqual(code, 200, result)
        return result["token"], result["user"]["id"]

    def quote(self, token, **extra):
        data = {
            "title": "Project",
            "client": "Client",
            "items": [
                {
                    "name": "Service",
                    "quantity": "2.5",
                    "unit": "hour",
                    "unit_price": 12000,
                    "cost_price": 4000,
                }
            ],
        }
        data.update(extra)
        code, result = self.call("/quotes", "POST", data, token)
        self.assertEqual(code, 201, result)
        return result["quote"]

    def publish(self, token, quote):
        code, result = self.call(
            "/quotes/" + quote["id"] + "/publish",
            "POST",
            {"revision": quote["revision"]},
            token,
        )
        self.assertEqual(code, 200, result)
        return result["quote"]

    def test_dashboard_returns_five_lightweight_quotes_in_own_workspace(self):
        token, _ = self.account("dashboard-owner")
        other_token, _ = self.account("dashboard-other")
        for number in range(6):
            self.quote(token, title=f"Estimate {number}")
        self.quote(other_token, title="Private estimate")

        code, dashboard = self.call("/dashboard", token=token)
        self.assertEqual(code, 200)
        self.assertEqual(dashboard["workspace"]["role"], "owner")
        self.assertEqual(dashboard["overview"]["quotes"]["total"], 6)
        self.assertEqual(len(dashboard["quotes"]), 5)
        self.assertTrue(all(quote["title"].startswith("Estimate ") for quote in dashboard["quotes"]))
        self.assertTrue(all("items" not in quote for quote in dashboard["quotes"]))
        self.assertTrue(all("public_token" not in quote for quote in dashboard["quotes"]))
        self.assertNotIn("Private estimate", [q["title"] for q in dashboard["quotes"]])
        self.assertIn("ai_drafting", dashboard["capabilities"])
        code, full_list = self.call("/quotes", token=token)
        self.assertEqual(code, 200)
        self.assertEqual(len(full_list["quotes"]), 6)
        self.assertTrue(all(len(quote["items"]) == 1 for quote in full_list["quotes"]))
        self.assertEqual(self.call("/dashboard")[0], 401)

        with self.mod.db() as con:
            user_id = dashboard["workspace"]["owner_id"]
            handler = SimpleNamespace(
                headers={},
                auth=lambda connection: connection.execute(
                    "SELECT * FROM users WHERE id=?", (user_id,)
                ).fetchone(),
            )
            statements = []
            con.set_trace_callback(statements.append)
            Service(handler, con, self.base).handle("GET", "/api/quotes", {})
            item_reads = [
                sql for sql in statements if sql.lstrip().upper().startswith("SELECT")
                and "quote_items" in sql
            ]
            self.assertEqual(len(item_reads), 1)
            statements.clear()
            Service(handler, con, self.base).handle("GET", "/api/dashboard", {})
            self.assertFalse(any("quote_items" in sql for sql in statements))

    def test_today_lists_real_followups_without_other_workspace_data(self):
        token, _ = self.account("today-owner")
        other_token, _ = self.account("today-other")
        quote = self.publish(token, self.quote(token, title="Approved work"))
        public_token = quote["public_url"].split("quote=")[1]
        self.assertEqual(self.call("/public/accept", "POST", {
            "token": public_token, "version": 1, "name": "Client"
        })[0], 200)
        self.quote(other_token, title="Private work")
        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        task_status, task = self.call("/tasks", "POST", {
            "name": "Call the client", "due_date": yesterday
        }, token)
        self.assertEqual(task_status, 201, task)

        code, dashboard = self.call("/dashboard", token=token)
        self.assertEqual(code, 200, dashboard)
        actions = dashboard["actions"]
        self.assertEqual(actions["summary"]["approved_this_month"], 1)
        self.assertEqual(actions["summary"]["active_projects"], 0)
        self.assertIn(quote["id"], [a["entity_id"] for a in actions["items"]])
        self.assertIn(task["item"]["id"], [a["entity_id"] for a in actions["items"]])
        self.assertNotIn("Private work", json.dumps(actions))

        code, project = self.call("/quotes/" + quote["id"] + "/project", "POST", {}, token)
        self.assertEqual(code, 201, project)
        _, dashboard = self.call("/dashboard", token=token)
        self.assertEqual(dashboard["actions"]["summary"]["active_projects"], 1)
        self.assertEqual(dashboard["actions"]["summary"]["waiting_payments"], 1)
        self.assertNotIn(quote["id"], [a["entity_id"] for a in dashboard["actions"]["items"]])

    def test_public_intake_creates_private_client_lead_request_and_attachment(self):
        owner, _ = self.account("intake-owner")
        outsider, _ = self.account("intake-outsider")
        code, result = self.call("/intake", "POST", {}, owner)
        self.assertEqual(code, 200, result)
        form = result["form"]
        token = form["public_url"].split("intake=")[1]
        self.assertEqual(self.call("/public/intake?token=" + token)[0], 200)
        payload = {
            "token": token, "name": "Ирина", "email": "irina@example.ru",
            "details": "Нужен фирменный сайт", "budget_kopecks": 7500000,
            "due_date": "2026-12-15", "comment": "Напишите после обеда",
            "file": {"name": "brief.txt", "content": base64.b64encode(b"Project brief").decode()},
        }
        self.assertEqual(self.call("/public/intake", "POST", {**payload, "email": ""})[0], 400)
        self.assertEqual(self.call("/public/intake", "POST", {**payload, "file": {
            "name": "active.html", "content": base64.b64encode(b"<script></script>").decode()
        }})[0], 400)
        self.assertEqual(self.call("/leads", token=owner)[1]["items"], [])
        code, submitted = self.call("/public/intake", "POST", payload)
        self.assertEqual(code, 201, submitted)
        self.assertEqual(submitted, {"ok": True})
        _, leads = self.call("/leads", token=owner)
        self.assertEqual(len(leads["items"]), 1)
        lead_id = leads["items"][0]["id"]
        _, today = self.call("/dashboard", token=owner)
        self.assertIn(lead_id, [action["entity_id"] for action in today["actions"]["items"]])
        _, detail = self.call("/leads/" + lead_id, token=owner)
        self.assertEqual(detail["item"]["request"]["details"], payload["details"])
        self.assertEqual(detail["item"]["request"]["budget_kopecks"], 7500000)
        client_id = detail["item"]["request"]["client_id"]
        _, client = self.call("/clients/" + client_id, token=owner)
        self.assertEqual(len(client["item"]["requests"]), 1)
        self.assertTrue(any(event["action"] == "Новая заявка" for event in client["item"]["timeline"]))
        _, files = self.call("/files?client_id=" + client_id, token=owner)
        self.assertEqual([file["name"] for file in files["items"]], ["brief.txt"])
        self.assertEqual(self.call("/leads/" + lead_id, token=outsider)[0], 404)
        self.assertEqual(self.call("/files?client_id=" + client_id, token=outsider)[0], 404)
        self.assertEqual(self.call("/intake", "PATCH", {"enabled": 0}, owner)[0], 200)
        self.assertEqual(self.call("/public/intake?token=" + token)[0], 404)

    def test_unknown_intake_tokens_are_rate_limited(self):
        for index in range(60):
            self.assertEqual(
                self.call("/public/intake", "POST", {"token": f"missing-{index}"})[0],
                404,
            )
        self.assertEqual(
            self.call("/public/intake", "POST", {"token": "missing-last"})[0],
            429,
        )

    def test_full_client_quote_project_partial_payments_expense_document(self):
        token, _ = self.account("lifecycle")
        code, c = self.call(
            "/clients",
            "POST",
            {"name": "Client", "type": "company", "company": "Studio"},
            token,
        )
        self.assertEqual(code, 201)
        q = self.quote(token, client_id=c["item"]["id"])
        public_token = q["public_url"].split("quote=")[1]
        self.assertEqual(self.call("/public/quote?token=" + public_token)[0], 404)
        q = self.publish(token, q)
        code, public = self.call("/public/quote?token=" + public_token)
        self.assertEqual(code, 200)
        self.assertNotIn("cost_price", json.dumps(public))
        self.assertNotIn("internal_cost", json.dumps(public))
        self.assertNotIn("markup", json.dumps(public))
        self.assertEqual(public["quote"]["approval_state"], "viewed")
        code, _ = self.call(
            "/public/accept",
            "POST",
            {"token": public_token, "version": 1, "name": "Client"},
        )
        self.assertEqual(code, 200)
        code, project = self.call("/quotes/" + q["id"] + "/project", "POST", {}, token)
        self.assertEqual(code, 201)
        p = project["project"]
        self.assertEqual(
            self.call("/quotes/" + q["id"] + "/project", "POST", {}, token)[1][
                "project"
            ]["id"],
            p["id"],
        )
        receipt = {
            "project_id": p["id"],
            "amount_kopecks": 10000,
            "method": "bank_transfer",
        }
        self.assertEqual(
            self.call("/receipts", "POST", receipt, token, key="lifecycle-payment-key")[
                0
            ],
            201,
        )
        self.assertEqual(
            self.call("/receipts", "POST", receipt, token, key="lifecycle-payment-key")[
                0
            ],
            200,
        )
        self.assertEqual(
            self.call(
                "/receipts",
                "POST",
                {**receipt, "amount_kopecks": 30000},
                token,
                key="another-payment-key",
            )[0],
            409,
        )
        self.assertEqual(
            self.call(
                "/expenses",
                "POST",
                {"project_id": p["id"], "amount_kopecks": 2000, "category": "Tools"},
                token,
                key="lifecycle-expense-key",
            )[0],
            201,
        )
        overview = self.call("/overview", token=token)[1]["currencies"][0]
        self.assertEqual(
            (overview["paid"], overview["unpaid"], overview["cash_profit"]),
            (10000, 20000, 8000),
        )
        self.assertEqual(
            self.call(
                "/projects/" + p["id"],
                "PATCH",
                {"revision": 1, "status": "completed"},
                token,
            )[0],
            200,
        )
        code, document = self.call(
            "/documents", "POST", {"quote_id": q["id"], "kind": "act"}, token
        )
        self.assertEqual(code, 201, document)
        code, content = self.call(
            "/documents/" + document["document"]["id"] + "/pdf", token=token, raw=True
        )
        self.assertEqual(code, 200)
        self.assertTrue(content.startswith(b"%PDF-"))
        from pypdf import PdfReader

        self.assertIn("Client", PdfReader(io.BytesIO(content)).pages[0].extract_text())

    def test_version_immutability_stale_response_and_optimistic_lock(self):
        token, _ = self.account("versions")
        q = self.publish(token, self.quote(token))
        link = q["public_url"].split("quote=")[1]
        code, _ = self.call(
            "/quotes/" + q["id"],
            "PATCH",
            {"revision": q["revision"] - 1, "title": "stale"},
            token,
        )
        self.assertEqual(code, 409)
        code, updated = self.call(
            "/quotes/" + q["id"],
            "PATCH",
            {
                "revision": q["revision"],
                "title": "Revised",
                "items": [{"name": "New", "unit_price": 70000}],
            },
            token,
        )
        self.assertEqual(code, 200)
        old = self.call("/public/quote?token=" + link)[1]["quote"]
        self.assertEqual((old["title"], old["amount_kopecks"]), ("Project", 30000))
        for private_key in ("id", "client_id", "internal_cost", "revision", "custom_fields", "view_count"):
            self.assertNotIn(private_key, old)
        self.assertEqual(
            self.call("/public/accept", "POST", {"token": link, "version": 1})[0], 409
        )
        latest = self.publish(token, updated["quote"])
        self.assertEqual(latest["published_version"], 2)
        self.assertEqual(
            self.call("/public/accept", "POST", {"token": link, "version": 1})[0], 409
        )
        self.assertEqual(
            self.call("/public/accept", "POST", {"token": link, "version": 2})[0], 200
        )
        code, current = self.call("/quotes/" + q["id"], token=token)
        self.assertEqual(
            self.call(
                "/quotes/" + q["id"],
                "PATCH",
                {"revision": current["quote"]["revision"], "title": "cannot edit"},
                token,
            )[0],
            409,
        )

    def test_tenant_isolation_viewer_rbac_and_revocation(self):
        owner, _ = self.account("team-owner")
        viewer, viewer_id = self.account("team-viewer")
        wid = self.call("/workspace", token=owner)[1]["workspace"]["id"]
        q = self.quote(owner)
        self.assertEqual(self.call("/quotes/" + q["id"], token=viewer)[0], 404)
        self.assertEqual(self.call("/workspace", token=viewer, workspace=wid)[0], 404)
        self.assertEqual(
            self.call(
                "/workspace/members",
                "POST",
                {"email": "team-viewer@test.invalid", "role": "viewer"},
                owner,
            )[0],
            200,
        )
        self.assertEqual(
            self.call("/quotes/" + q["id"], token=viewer, workspace=wid)[0], 200
        )
        self.assertEqual(
            self.call("/clients", "POST", {"name": "Denied"}, viewer, wid)[0], 403
        )
        self.assertEqual(self.call("/intake", "POST", {}, viewer, wid)[0], 403)
        self.assertEqual(self.call("/intake", "PATCH", {"enabled": 0}, viewer, wid)[0], 403)
        attachment = {"quote_id": q["id"], "name": "scope.txt", "content": base64.b64encode(b"Private scope").decode()}
        file_status, file_result = self.call("/files", "POST", attachment, owner)
        self.assertEqual(file_status, 201, file_result)
        file_id = file_result["file"]["id"]
        self.assertEqual(self.call("/files/" + file_id, "DELETE", token=viewer, workspace=wid)[0], 403)
        self.assertEqual(self.call("/files/" + file_id, token=viewer, workspace=wid, raw=True)[0], 200)
        self.assertEqual(
            self.call(
                "/workspace/members",
                "POST",
                {"email": "team-viewer@test.invalid", "role": "admin"},
                viewer,
                wid,
            )[0],
            403,
        )
        self.assertEqual(
            self.call("/workspace/members/" + viewer_id, "DELETE", token=owner)[0], 200
        )
        self.assertEqual(
            self.call("/quotes/" + q["id"], token=viewer, workspace=wid)[0], 404
        )

    def test_parallel_creation_cannot_bypass_free_quota(self):
        token, _ = self.account("concurrent")
        payload = {"title": "Parallel", "client": "Client", "amount": 1000}
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            codes = list(
                pool.map(
                    lambda _: self.call("/quotes", "POST", payload, token)[0], range(14)
                )
            )
        self.assertEqual(codes.count(201), 10)
        self.assertEqual(codes.count(402), 4)

    def test_csv_atomicity_and_spreadsheet_formula_escape(self):
        token, _ = self.account("import")
        code, _ = self.call(
            "/transfer/catalog",
            "POST",
            {"csv": "name,price\nGood,100\nBad,nope"},
            token,
        )
        self.assertEqual(code, 400)
        self.assertEqual(self.call("/catalog", token=token)[1]["items"], [])
        self.assertEqual(
            self.call(
                "/transfer/clients",
                "POST",
                {"csv": 'name,email\n=HYPERLINK("bad"),client@test.invalid'},
                token,
            )[0],
            201,
        )
        code, csv = self.call("/transfer/clients", token=token, raw=True)
        self.assertEqual(code, 200)
        self.assertIn(b"'=HYPERLINK", csv)

    def test_logs_redact_public_tokens(self):
        token, _ = self.account("logging")
        q = self.publish(token, self.quote(token))
        secret = q["public_url"].split("quote=")[1]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.call("/public/quote?token=" + secret)
        self.assertNotIn(secret, output.getvalue())
        self.assertIn("request_id", output.getvalue())

    def test_private_attachment_public_opt_in_and_invalid_format(self):
        owner, _ = self.account("file-owner")
        other, _ = self.account("file-other")
        q = self.publish(owner, self.quote(owner))
        link = q["public_url"].split("quote=")[1]
        payload = {
            "quote_id": q["id"],
            "name": "notes.txt",
            "content": base64.b64encode(b"Customer notes").decode(),
        }
        code, private = self.call("/files", "POST", payload, owner)
        self.assertEqual(code, 201, private)
        fid = private["file"]["id"]
        self.assertEqual(self.call("/files/" + fid, token=other)[0], 404)
        self.assertEqual(self.call("/public/file?token=" + link + "&id=" + fid)[0], 404)
        self.assertEqual(
            self.call("/files", "POST", {**payload, "name": "bad.png"}, owner)[0], 400
        )
        code, shared = self.call("/files", "POST", {**payload, "public": 1}, owner)
        self.assertEqual(code, 201)
        public_id = shared["file"]["id"]
        code, content = self.call(
            "/public/file?token=" + link + "&id=" + public_id, raw=True
        )
        self.assertEqual((code, content), (200, b"Customer notes"))
        self.assertEqual(
            self.call("/files/" + public_id, "DELETE", token=owner)[0], 200
        )
        self.assertEqual(
            self.call("/public/file?token=" + link + "&id=" + public_id)[0], 404
        )

    def test_ai_disabled_is_explicit_and_does_not_create_quotes(self):
        token, _ = self.account("ai-disabled")
        saved_key = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            self.assertFalse(self.call("/capabilities", token=token)[1]["ai_drafting"])
            self.assertEqual(
                self.call("/ai/draft", "POST", {"text": "Create a project"}, token)[0],
                503,
            )
            self.assertEqual(self.call("/quotes", token=token)[1]["quotes"], [])
        finally:
            if saved_key is not None:
                os.environ["OPENROUTER_API_KEY"] = saved_key

    def test_custom_field_validation_and_cross_workspace_references(self):
        one, _ = self.account("custom-owner")
        two, _ = self.account("custom-other")
        foreign = self.call("/clients", "POST", {"name": "Other"}, two)[1]["item"]["id"]
        self.assertEqual(
            self.call(
                "/projects",
                "POST",
                {"name": "Invalid", "amount_kopecks": 100, "client_id": foreign},
                one,
            )[0],
            404,
        )
        code, field = self.call(
            "/custom-fields",
            "POST",
            {
                "name": "Level",
                "type": "select",
                "entity_type": "clients",
                "options": ["A", "B"],
            },
            one,
        )
        self.assertEqual(code, 201)
        self.assertEqual(
            self.call(
                "/clients",
                "POST",
                {"name": "Test", "custom_fields": {field["id"]: "C"}},
                one,
            )[0],
            400,
        )
        self.assertEqual(
            self.call(
                "/clients",
                "POST",
                {"name": "Test", "custom_fields": {field["id"]: "A"}},
                one,
            )[0],
            201,
        )


if __name__ == "__main__":
    unittest.main()
