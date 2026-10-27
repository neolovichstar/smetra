import copy
import json
import os
import unittest
from unittest.mock import patch

from backend.business import DomainError, Service, without_finance
from tests import test_business


class AssistantFinanceTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def team(self, label, granted=False):
        owner, _ = self.account(label + "-owner")
        member, member_id = self.account(label + "-member")
        wid = self.call("/workspace", token=owner)[1]["workspace"]["id"]
        with self.mod.db() as con:
            con.execute("UPDATE workspaces SET plan='team_month',subscription_status='active',entitlement_until=?,seat_limit=5 WHERE id=?",
                        (self.mod.now() + 86400, wid))
        status, result = self.call("/workspace/members", "POST",
                                  {"email": label + "-member@test.invalid", "role": "member"}, owner)
        self.assertEqual(status, 200, result)
        if granted:
            self.grant(owner, member_id, True)
        return owner, member, member_id, wid

    def grant(self, owner, member_id, allowed):
        result = self.call("/workspace/members/" + member_id, "PATCH", {"finance_access": allowed}, owner)
        self.assertEqual(result[0], 200, result)

    def catalog(self, owner):
        result = self.call("/catalog", "POST", {"name": "Paint", "price": 29001, "cost_price": 19763}, owner)
        self.assertEqual(result[0], 201, result)
        return result[1]["item"]

    def quote(self, owner):
        result = self.call("/quotes", "POST", {"title": "Room", "client": "Client", "items": [
            {"name": "Paint", "quantity": "2", "unit_price": 29001, "cost_price": 19763},
        ]}, owner)
        self.assertEqual(result[0], 201, result)
        return result[1]["quote"]

    def tool_chat(self, member, wid, name, args):
        tool = {"content": None, "tool_calls": [{"id": "finance-call", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)}}]}
        captured = []

        def model(messages, **_kwargs):
            captured.append(copy.deepcopy(messages))
            return tool if len(captured) == 1 else {"content": "Checked", "tool_calls": []}

        with patch.dict(os.environ, OPENROUTER_API_KEY="test-only"), patch("backend.assistant.query_model", side_effect=model):
            result = self.call("/assistant/chat", "POST", {"text": "Check the selected record"}, member, wid)
        self.assertEqual(result[0], 200, result)
        return result[1], captured

    def service(self, con, member_id, wid):
        service = Service(None, con, "http://localhost")
        service.user = con.execute("SELECT * FROM users WHERE id=?", (member_id,)).fetchone()
        service.wid, service.role = wid, "member"
        return service

    def test_expense_get_record_cannot_bypass_finance_gate(self):
        owner, member, _member_id, wid = self.team("ai-finance-read")
        project = self.call("/projects", "POST", {"name": "Room", "amount_kopecks": 29001}, owner)[1]["item"]
        status, expense = self.call("/expenses", "POST", {"project_id": project["id"], "amount_kopecks": 19763,
                                   "category": "Private supplier"}, owner, key="finance-read-expense-key")
        self.assertEqual(status, 201, expense)
        self.assertEqual(self.call("/expenses", token=member, workspace=wid)[0], 403)
        _result, captured = self.tool_chat(member, wid, "get_record", {"entity": "expenses", "id": expense["item"]["id"]})
        tool_messages = [message for turn in captured[1:] for message in turn if message["role"] == "tool"]
        self.assertTrue(tool_messages)
        for message in tool_messages:
            self.assertIn("error", json.loads(message["content"]))
            self.assertNotIn("19763", message["content"])
            self.assertNotIn("Private supplier", message["content"])

    def test_catalog_proposal_does_not_disclose_hidden_previous_cost(self):
        owner, member, _member_id, wid = self.team("ai-finance-preview")
        item = self.catalog(owner)
        result, _ = self.tool_chat(member, wid, "update_catalog",
                                  {"id": item["id"], "name": "Paint renamed", "cost_price": 1})
        self.assertEqual(len(result["actions"]), 1, result)
        serialized = json.dumps(result["actions"])
        self.assertNotIn("19763", serialized)
        self.assertNotIn("cost_price", serialized)
        action = result["actions"][0]
        applied = self.call("/assistant/confirm", "POST", {"id": action["id"]}, member, wid)
        self.assertEqual(applied[0], 200, applied)
        current = self.call("/catalog/" + item["id"], token=owner)[1]["item"]
        self.assertEqual((current["name"], current["cost_price"]), ("Paint renamed", 19763))

    def test_direct_prepare_does_not_expose_quote_costs_to_tool_result(self):
        from backend.assistant import prepare
        owner, _member, member_id, wid = self.team("ai-finance-tool-result")
        quote = self.quote(owner)
        with self.mod.db() as con:
            action = prepare(self.service(con, member_id, wid), "bulk_quote_items",
                             {"id": quote["id"], "rows": [1], "field": "quantity", "value": "3"})
            text = json.dumps(action)
            self.assertNotIn("cost_price", text)
            self.assertNotIn("internal_cost", text)
            self.assertNotIn("19763", text)
            stored = json.loads(con.execute("SELECT arguments FROM assistant_actions WHERE id=?", (action["id"],)).fetchone()[0])
            self.assertEqual(stored["items"][0]["cost_price"], 19763)

    def test_revoked_grant_hides_legacy_field_preview(self):
        owner, member, member_id, wid = self.team("ai-finance-revoke", granted=True)
        item = self.catalog(owner)
        result, _ = self.tool_chat(member, wid, "update_catalog", {"id": item["id"], "cost_price": 21001})
        action = result["actions"][0]
        self.assertEqual(action["preview"]["rows"][0]["before"], 19763)
        self.grant(owner, member_id, False)
        status, pending = self.call("/assistant", token=member, workspace=wid)
        self.assertEqual(status, 200, pending)
        text = json.dumps(pending["actions"])
        self.assertNotIn("19763", text)
        self.assertNotIn("21001", text)
        self.assertNotIn("cost_price", text)

    def test_granted_finance_keeps_catalog_review_apply_and_undo(self):
        owner, member, _member_id, wid = self.team("ai-finance-granted", granted=True)
        item = self.catalog(owner)
        result, _ = self.tool_chat(member, wid, "update_catalog", {"id": item["id"], "cost_price": 21001})
        action = result["actions"][0]
        self.assertEqual(action["preview"]["rows"][0]["before"], 19763)
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, member, wid)[0], 200)
        self.assertEqual(self.call("/catalog/" + item["id"], token=owner)[1]["item"]["cost_price"], 21001)
        self.assertEqual(self.call("/assistant/undo", "POST", {"id": action["id"]}, member, wid)[0], 200)
        self.assertEqual(self.call("/catalog/" + item["id"], token=owner)[1]["item"]["cost_price"], 19763)

    def test_sanitizer_hides_finance_field_descriptors_at_any_depth(self):
        data = {"preview": {"rows": [
            {"field": "cost_price", "before": 19763, "after": 21001},
            {"field": "name", "before": "Paint", "after": "Paint renamed"},
        ]}, "items": [{"unit_price": 29001, "cost_price": 19763}]}
        result = without_finance(data)
        self.assertEqual(result["preview"]["rows"], [{"field": "name", "before": "Paint", "after": "Paint renamed"}])
        self.assertEqual(result["items"], [{"unit_price": 29001}])
        self.assertEqual(data["preview"]["rows"][0]["before"], 19763)

    def test_expense_proposal_requires_finance_access(self):
        from backend.assistant import prepare
        owner, _member, member_id, wid = self.team("ai-finance-expense")
        with self.mod.db() as con:
            with self.assertRaises(DomainError) as error:
                prepare(self.service(con, member_id, wid), "create_expenses",
                        {"project_id": "anything", "name": "Private supplier", "amount_kopecks": 19763})
            self.assertEqual(error.exception.status, 403)

    def test_public_quote_edit_apply_replay_and_undo_preserve_private_costs(self):
        owner, member, _member_id, wid = self.team("ai-finance-public-edit")
        quote = self.quote(owner)
        result, _ = self.tool_chat(member, wid, "bulk_quote_items",
                                  {"id": quote["id"], "rows": [1], "field": "quantity", "value": "3"})
        action = result["actions"][0]
        applied = self.call("/assistant/confirm", "POST", {"id": action["id"]}, member, wid)
        self.assertEqual(applied[0], 200, applied)
        self.assertNotIn("cost_price", json.dumps(applied))
        self.assertEqual(applied, self.call("/assistant/confirm", "POST", {"id": action["id"]}, member, wid))
        current = self.call("/quotes/" + quote["id"], token=owner)[1]["quote"]
        self.assertEqual((current["items"][0]["quantity"], current["items"][0]["cost_price"]), ("3", 19763))
        undone = self.call("/assistant/undo", "POST", {"id": action["id"]}, member, wid)
        self.assertEqual(undone[0], 200, undone)
        self.assertNotIn("cost_price", json.dumps(undone))
        current = self.call("/quotes/" + quote["id"], token=owner)[1]["quote"]
        self.assertEqual(current["items"], quote["items"])

    def test_revoked_grant_rejects_pending_cost_confirmation_without_partial_change(self):
        owner, member, member_id, wid = self.team("ai-finance-pending", granted=True)
        item = self.catalog(owner)
        result, _ = self.tool_chat(member, wid, "update_catalog",
                                  {"id": item["id"], "name": "Paint renamed", "cost_price": 21001})
        action = result["actions"][0]
        self.grant(owner, member_id, False)
        rejected = self.call("/assistant/confirm", "POST", {"id": action["id"]}, member, wid)
        self.assertEqual(rejected[0], 403, rejected)
        current = self.call("/catalog/" + item["id"], token=owner)[1]["item"]
        self.assertEqual((current["name"], current["cost_price"]), ("Paint", 19763))
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT status FROM assistant_actions WHERE id=?", (action["id"],)).fetchone()[0], "pending")

    def test_revoked_grant_rejects_cost_replay_and_undo(self):
        owner, member, member_id, wid = self.team("ai-finance-applied", granted=True)
        item = self.catalog(owner)
        result, _ = self.tool_chat(member, wid, "update_catalog", {"id": item["id"], "cost_price": 21001})
        action = result["actions"][0]
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, member, wid)[0], 200)
        self.grant(owner, member_id, False)
        for path in ("/assistant/confirm", "/assistant/undo"):
            rejected = self.call(path, "POST", {"id": action["id"]}, member, wid)
            self.assertEqual(rejected[0], 403, rejected)
            self.assertNotIn("19763", json.dumps(rejected))
            self.assertNotIn("21001", json.dumps(rejected))
        self.assertEqual(self.call("/catalog/" + item["id"], token=owner)[1]["item"]["cost_price"], 21001)
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT status FROM assistant_actions WHERE id=?", (action["id"],)).fetchone()[0], "applied")

    def test_revoked_expense_proposals_and_cached_results_are_private(self):
        from backend.assistant import prepare
        owner, member, member_id, wid = self.team("ai-finance-old-expense", granted=True)
        with self.mod.db() as con:
            action = prepare(self.service(con, member_id, wid), "create_expenses",
                             {"project_id": "old-project", "name": "Private supplier", "amount_kopecks": 19763})
        self.grant(owner, member_id, False)
        pending = self.call("/assistant", token=member, workspace=wid)
        self.assertEqual(pending[0], 200, pending)
        self.assertNotIn(action["id"], json.dumps(pending[1]["actions"]))
        rejected = self.call("/assistant/confirm", "POST", {"id": action["id"]}, member, wid)
        self.assertEqual(rejected[0], 403, rejected)
        with self.mod.db() as con:
            con.execute("UPDATE assistant_actions SET status='applied',result=? WHERE id=?",
                        (json.dumps({"ok": True, "result": {"item": {"amount_kopecks": 19763, "category": "Private supplier"}}}),
                         action["id"]))
        rejected = self.call("/assistant/confirm", "POST", {"id": action["id"]}, member, wid)
        self.assertEqual(rejected[0], 403, rejected)
        self.assertNotIn("19763", json.dumps(rejected))

    def test_expense_read_remains_available_with_explicit_finance_grant(self):
        owner, member, _member_id, wid = self.team("ai-finance-allowed-read", granted=True)
        project = self.call("/projects", "POST", {"name": "Room", "amount_kopecks": 29001}, owner)[1]["item"]
        result = self.call("/expenses", "POST", {"project_id": project["id"], "amount_kopecks": 19763,
                           "category": "Supplier"}, owner, key="finance-allowed-expense-key")
        self.assertEqual(result[0], 201, result)
        _result, captured = self.tool_chat(member, wid, "get_record", {"entity": "expenses", "id": result[1]["item"]["id"]})
        messages = [message for turn in captured[1:] for message in turn if message["role"] == "tool"]
        self.assertEqual(json.loads(messages[0]["content"])["amount_kopecks"], 19763)


    def test_streamed_proposal_does_not_disclose_private_quote_costs(self):
        owner, member, _member_id, wid = self.team("ai-finance-sse")
        quote = self.quote(owner)

        def model(_messages, _on_delta, **_kwargs):
            return {"content": None, "tool_calls": [{"id": "finance-sse", "type": "function", "function": {
                "name": "bulk_quote_items",
                "arguments": json.dumps({"id": quote["id"], "rows": [1], "field": "quantity", "value": "3"}),
            }}]}

        with patch.dict(os.environ, OPENROUTER_API_KEY="test-only"), patch("backend.assistant.query_model_stream", side_effect=model):
            status, raw = self.call("/assistant/stream", "POST", {"text": "Update the quantity"}, member, wid, raw=True)
        self.assertEqual(status, 200, raw)
        text = raw.decode()
        self.assertIn("event: done", text)
        self.assertNotIn("cost_price", text)
        self.assertNotIn("internal_cost", text)
        self.assertNotIn("19763", text)
        frame = next(frame for frame in text.split("\n\n") if frame.startswith("event: done\n"))
        result = json.loads(frame.split("data: ", 1)[1])
        self.assertEqual(len(result["actions"]), 1, result)
        with self.mod.db() as con:
            stored = json.loads(con.execute("SELECT arguments FROM assistant_actions WHERE id=?",
                                           (result["actions"][0]["id"],)).fetchone()[0])
        self.assertEqual(stored["items"][0]["cost_price"], 19763)

    def test_revoked_grant_redacts_previously_applied_quote_result_and_undo_replay(self):
        owner, member, member_id, wid = self.team("ai-finance-old-quote", granted=True)
        quote = self.quote(owner)
        result, _ = self.tool_chat(member, wid, "bulk_quote_items",
                                  {"id": quote["id"], "rows": [1], "field": "quantity", "value": "3"})
        action = result["actions"][0]
        applied = self.call("/assistant/confirm", "POST", {"id": action["id"]}, member, wid)
        self.assertEqual(applied[0], 200, applied)
        self.assertIn("cost_price", json.dumps(applied))
        self.grant(owner, member_id, False)
        replay = self.call("/assistant/confirm", "POST", {"id": action["id"]}, member, wid)
        self.assertEqual(replay[0], 200, replay)
        self.assertNotIn("cost_price", json.dumps(replay))
        self.assertNotIn("19763", json.dumps(replay))
        # An old undone result also passes the response permission boundary.
        self.grant(owner, member_id, True)
        self.assertEqual(self.call("/assistant/undo", "POST", {"id": action["id"]}, member, wid)[0], 200)
        self.grant(owner, member_id, False)
        replay = self.call("/assistant/undo", "POST", {"id": action["id"]}, member, wid)
        self.assertEqual(replay[0], 200, replay)
        self.assertNotIn("cost_price", json.dumps(replay))
        self.assertNotIn("19763", json.dumps(replay))


if __name__ == "__main__":
    unittest.main()
