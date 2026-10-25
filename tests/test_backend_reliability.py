"""Provider failures must not become crashes, fake success, or partial writes."""

import base64
import io
import json
import os
import unittest
from unittest.mock import patch

from backend import app, assistant
from backend.business import DomainError
from tests import test_business, office_fixtures


class ProviderBoundaryTests(unittest.TestCase):
    def response(self, value):
        return io.BytesIO(json.dumps(value).encode())

    def test_assistant_rejects_truncated_and_empty_model_answers(self):
        for value in (
            {"choices": [{"finish_reason": "length", "message": {"content": "Partial answer"}}]},
            {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]},
            {"choices": [{"finish_reason": "stop", "message": {"content": {"unexpected": "object"}}}]},
            {"choices": [{"finish_reason": "stop", "message": {"tool_calls": [{"id": "x", "function": None}]}}]},
        ):
            with self.subTest(value=value), patch.dict(os.environ, OPENROUTER_API_KEY="fixture"), patch(
                "backend.assistant.urllib.request.urlopen", return_value=self.response(value)
            ):
                with self.assertRaises(DomainError) as error:
                    assistant.query_model([])
                self.assertEqual(error.exception.status, 502)

    def test_payment_client_bounds_and_validates_provider_json(self):
        handler = app.Handler.__new__(app.Handler)
        settings = {"YOOKASSA_SHOP_ID": "fixture-shop", "YOOKASSA_SECRET_KEY": "fixture-secret"}
        for raw in (b'[]', b'{"id":"one","id":"two"}', b'{"amount":1e999}', b' ' * 100001 + b'{}'):
            with self.subTest(raw=raw[:60]), patch.dict(os.environ, settings), patch(
                "backend.app.urllib.request.urlopen", return_value=io.BytesIO(raw)
            ):
                with self.assertRaises(app.ApiError) as error:
                    handler.provider_call("/payments/fixture")
                self.assertEqual(error.exception.status, 502)

    def test_stream_rejects_nonobject_events_and_truncation(self):
        for event in ([], {"choices": [{"delta": {}, "finish_reason": "length"}]}):
            raw = b"data: " + json.dumps(event).encode() + b"\n" + b"data: [DONE]\n"
            with self.subTest(event=event), patch.dict(os.environ, OPENROUTER_API_KEY="fixture"), patch(
                "backend.assistant.urllib.request.urlopen", return_value=io.BytesIO(raw)
            ):
                with self.assertRaises(DomainError) as error:
                    assistant.query_model_stream([], lambda text: None)
                self.assertEqual(error.exception.status, 502)

    def test_strict_json_rejects_ambiguous_and_unsafe_values(self):
        from backend.validation import load_json
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}',
                    b'{"x":"\\ud800"}', b'{"x":"\\u0000"}', b'[]',
                    '{"x":"data"}'.encode("utf-16"), '{"x":"data"}'.encode("utf-32"),
                    b'{"x":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}'):
            with self.subTest(raw=raw[:80]), self.assertRaises(ValueError):
                load_json(raw)
        self.assertEqual(load_json('{"name":"Сметра","ok":true}'), {"name": "Сметра", "ok": True})

    def test_response_reads_are_bounded_and_valid_objects_are_preserved(self):
        from backend.validation import read_json_response
        response = unittest.mock.Mock()
        response.read.return_value = b'{"ok":true}'
        self.assertEqual(read_json_response(response, 100), {"ok": True})
        response.read.assert_called_once_with(101)

    def test_oauth_rejects_oversized_and_duplicate_provider_payloads(self):
        from backend.identity import remote
        for raw in (b' ' * 100001 + b'{}', b'{"access_token":"one","access_token":"two"}', b'[]'):
            with self.subTest(raw=raw[:50]), patch("backend.identity.urllib.request.urlopen", return_value=io.BytesIO(raw)):
                with self.assertRaises(ValueError):
                    remote("https://provider.invalid/token")

    def test_payment_network_errors_do_not_log_credentials(self):
        from contextlib import redirect_stdout
        handler = app.Handler.__new__(app.Handler)
        capture = io.StringIO()
        with patch.dict(os.environ, YOOKASSA_SHOP_ID="fixture", YOOKASSA_SECRET_KEY="fixture-secret"), patch(
            "backend.app.urllib.request.urlopen", side_effect=OSError("secret-value-from-upstream")
        ), redirect_stdout(capture):
            with self.assertRaises(app.ApiError) as error:
                handler.provider_call("/payments/fixture")
        self.assertEqual(error.exception.status, 502)
        self.assertNotIn("secret-value", capture.getvalue())
        self.assertNotIn("fixture-secret", capture.getvalue())

    def test_stream_bounds_lines_and_requires_done_marker(self):
        good = {"choices": [{"delta": {"content": "Answer"}}]}
        for raw in (b"data: " + b" " * 65537 + b"{}\n",
                    b"data: " + json.dumps(good).encode() + b"\n",
                    b"data: [DONE]\n"):
            with self.subTest(raw=raw[:60]), patch.dict(os.environ, OPENROUTER_API_KEY="fixture"), patch(
                "backend.assistant.urllib.request.urlopen", return_value=io.BytesIO(raw)
            ):
                with self.assertRaises(DomainError) as error:
                    assistant.query_model_stream([], lambda text: None)
                self.assertEqual(error.exception.status, 502)

    def test_stream_rejects_invalid_fragment_types_and_indices(self):
        for part in ({"index": True}, {"index": 4}, {"index": 0, "function": []},
                     {"index": 0, "id": 42}, None):
            event = {"choices": [{"delta": {"tool_calls": [part]}}]}
            raw = b"data: " + json.dumps(event).encode() + b"\ndata: [DONE]\n"
            with self.subTest(part=part), patch.dict(os.environ, OPENROUTER_API_KEY="fixture"), patch(
                "backend.assistant.urllib.request.urlopen", return_value=io.BytesIO(raw)
            ):
                with self.assertRaises(DomainError):
                    assistant.query_model_stream([], lambda text: None)

    def test_tool_calls_require_unique_ids_and_strict_object_arguments(self):
        base = {"id": "tool-1", "function": {"name": "overview", "arguments": "{}"}}
        for calls in ([base, base], [{**base, "function": {"name": "overview", "arguments": "[]"}}],
                      [{**base, "function": {"name": "overview", "arguments": '{"id":"a","id":"b"}'}}]):
            with self.subTest(calls=calls), self.assertRaises(ValueError):
                assistant.model_message({"tool_calls": calls})
        self.assertEqual(assistant.model_message({"tool_calls": [base]})["tool_calls"], [base])

    def test_ocr_rejects_nonobject_and_truncated_results(self):
        from backend import file_ocr, receipt_ocr
        for finish, content in (("stop", "[]"), ("length", '{"text":"partial"}')):
            value = {"choices": [{"finish_reason": finish, "message": {"content": content}}]}
            for target, call in (
                ("backend.file_ocr.urllib.request.urlopen", lambda: file_ocr.request_page("data:image/jpeg;base64,fixture")),
                ("backend.receipt_ocr.urllib.request.urlopen", lambda: receipt_ocr._request(None, "data:image/jpeg;base64,fixture")),
            ):
                with self.subTest(target=target, finish=finish), patch.dict(os.environ, OPENROUTER_API_KEY="fixture"), patch(target, return_value=self.response(value)):
                    with self.assertRaises(DomainError) as error:
                        call()
                    self.assertEqual(error.exception.status, 502)

    def test_request_body_timeout_returns_408_and_closes_connection(self):
        from email.message import Message
        handler = app.Handler.__new__(app.Handler)
        handler.headers = Message()
        handler.headers["Content-Type"] = "application/json"
        handler._body_length = 2
        handler.rfile = unittest.mock.Mock()
        handler.rfile.read.side_effect = TimeoutError()
        with self.assertRaises(app.ApiError) as error:
            handler.body()
        self.assertEqual(error.exception.status, 408)
        self.assertTrue(handler.close_connection)

    def test_database_outages_are_distinct_from_programming_errors(self):
        import sqlite3
        import psycopg
        from psycopg_pool import PoolTimeout
        from backend.database_errors import unavailable
        for error in (psycopg.OperationalError("private DSN"), PoolTimeout("private DSN"),
                      sqlite3.OperationalError("database is locked")):
            self.assertTrue(unavailable(error))
        for error in (psycopg.ProgrammingError("bad SQL"), sqlite3.OperationalError("no such table: typo"), ValueError("bug")):
            self.assertFalse(unavailable(error))

    def test_redis_never_combines_credentials_from_different_databases(self):
        from backend.redis_infra import credentials, RedisUnavailable
        for partial in ({"UPSTASH_REDIS_REST_URL": "https://new.invalid"},
                        {"UPSTASH_REDIS_REST_TOKEN": "new-token"}):
            settings = {"REDIS_KV_REST_API_URL": "https://old.invalid", "REDIS_KV_REST_API_TOKEN": "old-token", **partial}
            with self.subTest(partial=partial), patch.dict(os.environ, settings, clear=True):
                with self.assertRaises(RedisUnavailable):
                    credentials()

    def test_production_lock_cannot_silently_become_noop(self):
        from backend.redis_infra import acquire_lock, RedisUnavailable
        for settings in ({"VERCEL_ENV": "production"}, {"REDIS_ENV": "production", "REDIS_ENABLED": "0"}):
            with self.subTest(settings=settings), patch.dict(os.environ, settings, clear=True):
                with self.assertRaises(RedisUnavailable):
                    acquire_lock("assistant", "fixture")
        with patch.dict(os.environ, {"REDIS_ENV": "test"}, clear=True):
            lease = acquire_lock("assistant", "fixture")
            lease.release()

    def test_provider_token_counts_cannot_overflow_database_integer_columns(self):
        from backend.validation import usage_counts
        for value in (None, {}, {"prompt_tokens": -1, "completion_tokens": 5},
                      {"prompt_tokens": True, "completion_tokens": 5},
                      {"prompt_tokens": 10 ** 100, "completion_tokens": 5}):
            with self.subTest(value=value):
                self.assertIsNone(usage_counts(value))
        self.assertEqual(usage_counts({"prompt_tokens": 0, "completion_tokens": 50}), (0, 50))

    def test_malformed_payment_and_refund_structures_fail_before_database_writes(self):
        handler = app.Handler.__new__(app.Handler)
        con = unittest.mock.Mock()
        settings = {"YOOKASSA_MODE": "test", "YOOKASSA_SHOP_ID": "fixture-shop",
                    "YOOKASSA_SECRET_KEY": "fixture-secret", "YOOKASSA_MERCHANT_TYPE": "self_employed"}
        remote = {"test": True, "recipient": {"account_id": "fixture-shop"},
                  "amount": {"value": "490.00", "currency": "RUB"}, "metadata": {"user_id": "fixture"}}
        with patch.dict(os.environ, settings):
            for key in ("amount", "metadata"):
                for value in (None, [], "bad"):
                    with self.subTest(key=key, value=value), self.assertRaises(app.ApiError) as error:
                        handler.apply_payment(con, {}, {**remote, key: value})
                    self.assertEqual(error.exception.status, 502)
        for value in (None, [], "bad"):
            with self.subTest(refund_amount=value), self.assertRaises(app.ApiError) as error:
                handler.apply_refund(con, {"id": "refund", "payment_id": "payment", "status": "succeeded", "amount": value})
            self.assertEqual(error.exception.status, 502)
        con.execute.assert_not_called()


class ReliabilityFlows(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def test_empty_model_reply_is_an_error_and_does_not_persist_fake_success(self):
        token, user_id = self.account("empty-provider")
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture"), patch(
            "backend.assistant.query_model", return_value={"content": ""}
        ):
            code, result = self.call("/assistant/chat", "POST", {"text": "Check my records"}, token)
        self.assertEqual(code, 502, result)
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM assistant_messages WHERE user_id=?", (user_id,)).fetchone()[0], 0)
        self.assertEqual(self.call("/assistant", token=token)[1]["quota"]["used"], 0)

    def test_xlsx_with_missing_dimensions_imports_bounded_rows(self):
        from openpyxl import Workbook
        from tests.office_fixtures import rewrite

        token, _ = self.account("missing-xlsx-dimension")
        book = Workbook()
        sheet = book.active
        sheet.append(["name", "price", "unit"])
        sheet.append(["Painting", 15000, "m2"])
        raw = io.BytesIO()
        book.save(raw)
        import zipfile
        with zipfile.ZipFile(io.BytesIO(raw.getvalue())) as package:
            xml = package.read("xl/worksheets/sheet1.xml")
        import re
        xml = re.sub(br"<dimension[^>]*/>", b"", xml)
        source = rewrite(raw.getvalue(), {"xl/worksheets/sheet1.xml": xml})
        code, result = self.call("/transfer/catalog", "POST", {
            "format": "xlsx", "file": base64.b64encode(source).decode(),
        }, token)
        self.assertEqual(code, 201, result)
        self.assertEqual(self.call("/catalog", token=token)[1]["items"][0]["price"], 15000)

    def test_xlsx_active_content_is_rejected_without_creating_records(self):
        token, _ = self.account("unsafe-xlsx-import")
        raw = office_fixtures.rewrite(office_fixtures.xlsx(), {"xl/vbaProject.bin": b"macro"})
        code, result = self.call("/transfer/catalog", "POST", {
            "format": "xlsx", "file": base64.b64encode(raw).decode(),
        }, token)
        self.assertEqual(code, 400, result)
        self.assertEqual(self.call("/catalog", token=token)[1]["items"], [])

    def test_database_outage_returns_503_without_exposing_driver_details(self):
        import psycopg
        with patch.object(self.mod, "db", side_effect=psycopg.OperationalError("postgres://secret-password@private-host/db")):
            code, result = self.call("/me")
        self.assertEqual(code, 503, result)
        self.assertEqual(result["code"], "database_unavailable")
        self.assertEqual(result["retryAfter"], 5)
        self.assertNotIn("private-host", json.dumps(result))

    def test_invalid_csv_headers_and_extra_cells_are_atomic(self):
        token, _ = self.account("ambiguous-csv")
        for text in ("name,price,price\nPaint,100,200",
                     "name,price\nPaint,100,unexpected",
                     "name,,price\nPaint,hidden,100"):
            with self.subTest(text=text):
                code, result = self.call("/transfer/catalog", "POST", {"csv": text}, token)
                self.assertEqual(code, 400, result)
                self.assertEqual(self.call("/catalog", token=token)[1]["items"], [])

    def workbook(self, rows):
        from openpyxl import Workbook
        book = Workbook()
        for row in rows:
            book.active.append(row)
        stream = io.BytesIO()
        book.save(stream)
        return stream.getvalue()

    def test_xlsx_does_not_truncate_fractional_kopecks_or_accept_booleans(self):
        token, _ = self.account("integer-import-money")
        for price in (100.9, True):
            raw = self.workbook([["name", "price"], ["Valid first", 100], ["Invalid second", price]])
            code, result = self.call("/transfer/catalog", "POST", {"format": "xlsx", "file": base64.b64encode(raw).decode()}, token)
            self.assertEqual(code, 400, result)
            self.assertEqual(self.call("/catalog", token=token)[1]["items"], [])

    def test_xlsx_duplicate_and_missing_headers_are_rejected(self):
        token, _ = self.account("xlsx-header")
        for rows in ([["name", "price", "price"], ["Paint", 100, 999]],
                     [["name", None, "price"], ["Paint", "hidden", 100]]):
            raw = self.workbook(rows)
            code, result = self.call("/transfer/catalog", "POST", {"format": "xlsx", "file": base64.b64encode(raw).decode()}, token)
            self.assertEqual(code, 400, result)
        self.assertEqual(self.call("/catalog", token=token)[1]["items"], [])

    def test_xlsx_lying_dimensions_cannot_hide_out_of_bounds_rows(self):
        import re
        import zipfile
        token, _ = self.account("xlsx-lying-dimensions")
        raw = self.workbook([["name", "price"], ["Paint", 100]])
        with zipfile.ZipFile(io.BytesIO(raw)) as package:
            xml = package.read("xl/worksheets/sheet1.xml")
        xml = re.sub(br'<dimension[^>]*/>', b'<dimension ref="A1:B2"/>', xml)
        xml = xml.replace(b'r="2"', b'r="202"').replace(b'r="A2"', b'r="A202"').replace(b'r="B2"', b'r="B202"')
        raw = office_fixtures.rewrite(raw, {"xl/worksheets/sheet1.xml": xml})
        code, result = self.call("/transfer/catalog", "POST", {"format": "xlsx", "file": base64.b64encode(raw).decode()}, token)
        self.assertEqual(code, 400, result)
        self.assertEqual(self.call("/catalog", token=token)[1]["items"], [])

    def test_invalid_draft_fields_do_not_emit_success_activity(self):
        token, user_id = self.account("invalid-draft-fields")
        value = {"title": "Valid title", "client": ["invalid"], "items": [
            {"name": "Paint", "unit": "m2", "quantity": 1, "unit_price": 10000}
        ]}
        response = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]}
        import urllib.request
        real_open = urllib.request.urlopen

        def provider_open(request, *args, **kwargs):
            if isinstance(request, urllib.request.Request) and request.full_url.startswith("https://openrouter.ai/"):
                return io.BytesIO(json.dumps(response).encode())
            return real_open(request, *args, **kwargs)

        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture"), patch(
            "backend.ai.urllib.request.urlopen", side_effect=provider_open
        ):
            code, result = self.call("/ai/draft", "POST", {"text": "Prepare a quote for painting"}, token)
        self.assertEqual(code, 502, result)
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM activity WHERE actor_id=? AND entity_type='ai'", (user_id,)).fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT status FROM ai_usage WHERE user_id=?", (user_id,)).fetchone()[0], "failed")

    def test_proposals_are_not_persisted_when_chat_commit_fence_rejects(self):
        from backend.business import Service
        token, user_id = self.account("proposal-commit-fence")
        self.assertEqual(self.call("/workspace", token=token)[0], 200)
        response = {"tool_calls": [{"id": "call-1", "type": "function", "function": {
            "name": "create_clients", "arguments": '{"name":"Proposed client"}'
        }}]}
        with self.mod.db() as con:
            service = Service(None, con, "https://smetra.invalid")
            service.user = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            service.wid = con.execute("SELECT workspace_id FROM workspace_members WHERE user_id=?", (user_id,)).fetchone()[0]
            service.role = "owner"

            def reject_commit(result):
                self.assertEqual(len(result["actions"]), 1)
                raise DomainError(409, "Cancelled before commit")

            with patch("backend.assistant.query_model", return_value=response):
                with self.assertRaises(DomainError) as error:
                    assistant.answer_chat(service, "Create a client", on_commit=reject_commit)
            self.assertEqual(error.exception.status, 409)
            self.assertEqual(con.execute("SELECT count(*) FROM assistant_actions WHERE user_id=?", (user_id,)).fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT count(*) FROM assistant_messages WHERE user_id=?", (user_id,)).fetchone()[0], 0)
            action = assistant.prepare(service, "create_clients", {"name": "Independent proposal"})
            self.assertIsNotNone(con.execute("SELECT id FROM assistant_actions WHERE id=?", (action["id"],)).fetchone())

    def test_invalid_provider_usage_does_not_crash_a_valid_chat(self):
        token, user_id = self.account("overflow-provider-usage")
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture"), patch(
            "backend.assistant.query_model", return_value={
                "content": "Ready", "_usage": {"prompt_tokens": 10 ** 100, "completion_tokens": 1}
            }
        ):
            code, result = self.call("/assistant/chat", "POST", {"text": "Hello"}, token)
        self.assertEqual(code, 200, result)
        with self.mod.db() as con:
            row = con.execute("SELECT status,input_tokens,output_tokens FROM ai_usage WHERE user_id=?", (user_id,)).fetchone()
            self.assertEqual(tuple(row), ("usage_unknown", 0, 0))

    def test_checkout_rejects_malformed_redirects_and_ids_before_persistence(self):
        from tests.test_security_hardening import SecurityHardeningTests
        token, user_id = self.account("checkout-provider-shape")
        with self.mod.db() as con:
            con.execute("UPDATE users SET email_verified_at=? WHERE id=?", (self.mod.now(), user_id))
        settings = {"YOOKASSA_MODE": "live", "YOOKASSA_SHOP_ID": "fixture-shop",
                    "YOOKASSA_SECRET_KEY": "fixture-secret", "YOOKASSA_MERCHANT_TYPE": "self_employed"}
        cases = [(None, "payment"), ({}, "payment"), ({"confirmation_url": 42}, "payment"),
                 ({"confirmation_url": "https:///"}, "payment"),
                 ({"confirmation_url": "https://example.test:invalid/pay"}, "payment"),
                 ({"confirmation_url": "https://example.test/pay"}, 42),
                 ({"confirmation_url": "https://example.test/pay"}, "payment-valid")]
        for index, (confirmation, ident) in enumerate(cases):
            def provider(path, method, payload, key):
                return {"id": ident, "test": False, "recipient": {"account_id": "fixture-shop"},
                        "amount": payload["amount"], "metadata": payload["metadata"], "confirmation": confirmation}
            with self.subTest(index=index), patch.dict(os.environ, settings), patch.object(self.mod.Handler, "provider_call", side_effect=provider):
                code, _, result = SecurityHardeningTests.request(self, "POST", "/api/billing/checkout",
                    json.dumps({"plan": "pro_month"}).encode(),
                    {"Content-Type": "application/json", "Authorization": "Bearer " + token,
                     "Idempotency-Key": "reliability-checkout-" + str(index)})
            self.assertEqual(code, 201 if index == len(cases) - 1 else 502, result)
            with self.mod.db() as con:
                self.assertEqual(con.execute("SELECT count(*) FROM payments WHERE user_id=?", (user_id,)).fetchone()[0],
                                 1 if index == len(cases) - 1 else 0)
