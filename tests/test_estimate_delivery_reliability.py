"""Publication privacy, delivery idempotency and in-flight authority changes."""
import concurrent.futures
import hashlib
import json
import os
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from backend import assistant
from backend.business import DomainError, Service, ensure_workspace, transaction
from tests import test_business


class EstimateDeliveryReliabilityTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account
    quote = test_business.BusinessFlows.quote
    publish = test_business.BusinessFlows.publish

    def shared(self, label):
        owner, _ = self.account(label + "-owner")
        recipient, recipient_id = self.account(label + "-recipient")
        quote = self.publish(owner, self.quote(owner, title="Published customer title"))
        code, share = self.call("/shares", "POST", {
            "quote_id": quote["id"], "email": label + "-recipient@test.invalid",
        }, owner)
        self.assertEqual(code, 201, share)
        return owner, recipient, recipient_id, quote, share["id"]

    def test_inbox_and_details_never_disclose_private_draft_fields(self):
        owner, recipient, _, quote, share_id = self.shared("immutable-inbox")
        code, edited = self.call("/quotes/" + quote["id"], "PATCH", {
            "revision": quote["revision"], "title": "PRIVATE INTERNAL DRAFT",
            "currency": "EUR", "description": "PRIVATE INTERNAL NOTES",
        }, owner)
        self.assertEqual(code, 200, edited)
        inbox = self.call("/shared-inbox", token=recipient)[1]["inbox"]
        self.assertEqual(len(inbox), 1)
        self.assertEqual((inbox[0]["title"], inbox[0]["currency"]), ("Published customer title", "RUB"))
        details = self.call("/shared-inbox/" + share_id, token=recipient)
        self.assertEqual(details[0], 200, details)
        for result in (inbox, details):
            self.assertNotIn("PRIVATE INTERNAL", json.dumps(result))
            self.assertNotIn("cost_price", json.dumps(result))

    def test_missing_snapshot_is_hidden_instead_of_using_current_quote(self):
        _, recipient, _, quote, share_id = self.shared("missing-snapshot")
        with self.mod.db() as con:
            con.execute("DELETE FROM quote_versions WHERE quote_id=?", (quote["id"],))
        self.assertEqual(self.call("/shared-inbox", token=recipient)[1]["inbox"], [])
        self.assertEqual(self.call("/shared-inbox/" + share_id, token=recipient)[0], 409)

    def test_expired_share_is_renewed_and_previous_url_stays_invalid(self):
        owner, recipient, _, quote, old_id = self.shared("renew-invite")
        with self.mod.db() as con:
            con.execute("UPDATE estimate_shares SET expires_at=? WHERE id=?", (self.mod.now() - 1, old_id))
        code, fresh = self.call("/shares", "POST", {
            "quote_id": quote["id"], "email": "renew-invite-recipient@test.invalid",
        }, owner)
        self.assertEqual(code, 201, fresh)
        self.assertNotEqual(fresh["id"], old_id)
        self.assertEqual(self.call("/shared-inbox/" + old_id, token=recipient)[0], 404)
        self.assertEqual(self.call("/shared-inbox/" + fresh["id"], token=recipient)[0], 200)

    def response_race(self, label, mutation, endpoint="selection"):
        _, recipient, recipient_id, quote, share_id = self.shared(label)

        @contextmanager
        def changed_before_lock(con, **kwargs):
            mutation(con, quote, share_id, recipient_id)
            with transaction(con, **kwargs):
                yield

        data = {"revision": 0, "included_optional": [], "action": "request_changes"}
        with patch("backend.business.transaction", changed_before_lock):
            code, result = self.call("/shared-inbox/" + share_id + "/" + endpoint,
                                     "POST", data, recipient)
        self.assertIn(code, (401, 403, 404, 409), result)
        with self.mod.db() as con:
            self.assertEqual(con.execute(
                "SELECT count(*) FROM estimate_share_responses WHERE share_id=?", (share_id,),
            ).fetchone()[0], 0)
            self.assertEqual(con.execute(
                "SELECT count(*) FROM notifications WHERE entity_id=? AND message='Клиент предложил изменения'",
                (quote["id"],),
            ).fetchone()[0], 0)

    def test_invitation_revoked_while_selection_waits_cannot_be_used(self):
        self.response_race("revoke-selection", lambda con, q, sid, uid: con.execute(
            "UPDATE estimate_shares SET status='revoked' WHERE id=?", (sid,)))

    def test_invitation_expiring_while_approval_waits_cannot_be_used(self):
        self.response_race("expire-approval", lambda con, q, sid, uid: con.execute(
            "UPDATE estimate_shares SET expires_at=1 WHERE id=?", (sid,)), "approve")

    def test_republished_quote_cannot_receive_stale_change_request(self):
        self.response_race("republish-response", lambda con, q, sid, uid: con.execute(
            "UPDATE quotes SET published_version=published_version+1 WHERE id=?", (q["id"],)), "approve")

    def test_recipient_blocked_during_request_cannot_save_selection(self):
        self.response_race("blocked-response", lambda con, q, sid, uid: con.execute(
            "UPDATE users SET blocked=1 WHERE id=?", (uid,)))

    def test_recipient_losing_verification_cannot_save_selection(self):
        self.response_race("unverified-response", lambda con, q, sid, uid: con.execute(
            "UPDATE users SET email_verified_at=NULL WHERE id=?", (uid,)))

    def test_first_concurrent_response_returns_conflict_without_500(self):
        _, recipient, _, _, share_id = self.shared("parallel-selection")
        def select(_):
            return self.call("/shared-inbox/" + share_id + "/selection", "POST",
                             {"revision": 0, "included_optional": []}, recipient)[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(select, range(2))), [200, 409])

    def test_new_publication_reaches_existing_chat_once_per_version(self):
        owner, _ = self.account("versioned-chat-owner")
        recipient, rid = self.account("versioned-chat-recipient")
        quote = self.publish(owner, self.quote(owner, title="Version one"))
        request = {"quote_id": quote["id"], "public_id": "SM-" + rid.replace("-", "").upper(),
                   "version": quote["published_version"]}
        first = self.call("/profile/quote-chats", "POST", request, owner)
        self.assertEqual(first[0], 200, first)
        chat_id = first[1]["chat"]["id"]
        second = self.call("/profile/quote-chats", "POST", request, owner)
        self.assertEqual(second[0], 200, second)
        self.assertTrue(second[1]["chat"]["replayed"])
        edited = self.call("/quotes/" + quote["id"], "PATCH", {
            "revision": quote["revision"], "title": "Version two",
        }, owner)[1]["quote"]
        newer = self.publish(owner, edited)
        request["version"] = newer["published_version"]
        third = self.call("/profile/quote-chats", "POST", request, owner)
        self.assertEqual(third[0], 200, third)
        self.assertEqual(third[1]["chat"]["id"], chat_id)
        self.assertFalse(third[1]["chat"]["replayed"])
        messages = self.call("/profile/chats/" + chat_id + "/messages", token=recipient)[1]["messages"]
        sent = [m for m in messages if m["metadata"].get("event") == "estimate_shared_in_chat"]
        self.assertEqual(sorted(m["metadata"]["quote_version"] for m in sent), [1, 2])
        self.assertNotIn("cost_price", json.dumps(messages))

    def test_chat_retry_is_serialized_across_parallel_requests(self):
        owner, _ = self.account("parallel-chat-owner")
        _, rid = self.account("parallel-chat-recipient")
        quote = self.publish(owner, self.quote(owner))
        request = {"quote_id": quote["id"], "public_id": "SM-" + rid.replace("-", "").upper()}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            replies = list(executor.map(lambda _: self.call("/profile/quote-chats", "POST", request, owner), range(2)))
        self.assertEqual([r[0] for r in replies], [200, 200], replies)
        self.assertEqual(len({r[1]["chat"]["id"] for r in replies}), 1)
        with self.mod.db() as con:
            self.assertEqual(con.execute(
                "SELECT count(*) FROM chat_messages WHERE conversation_id=?", (replies[0][1]["chat"]["id"],),
            ).fetchone()[0], 1)

    def service(self, con, token, uid):
        service = Service(SimpleNamespace(session_token_hash=hashlib.sha256(token.encode()).hexdigest(),
                                          headers={}), con, self.mod.ORIGIN)
        service.user = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        service.wid = ensure_workspace(con, service.user)
        service.role = "owner"
        return service

    def test_equivalent_pending_proposals_reuse_id_within_same_conversation(self):
        token, uid = self.account("dedup-proposals")
        with self.mod.db() as con:
            service = self.service(con, token, uid)
            first = assistant.prepare(service, "create_clients", {"name": "Same client"})
            second = assistant.prepare(service, "create_clients", {"name": "Same client", "ignored": "discard"})
            self.assertEqual(first["id"], second["id"])
            assistant.confirm(service, first["id"])
            self.assertEqual(con.execute("SELECT count(*) FROM clients WHERE workspace_id=?", (service.wid,)).fetchone()[0], 1)

    def test_dismissed_expired_and_other_conversation_proposals_are_not_reused(self):
        token, uid = self.account("dedup-scope")
        with self.mod.db() as con:
            service = self.service(con, token, uid)
            args = {"name": "Client"}
            first = assistant.prepare(service, "create_clients", args)
            con.execute("UPDATE assistant_actions SET status='dismissed' WHERE id=?", (first["id"],))
            second = assistant.prepare(service, "create_clients", args)
            self.assertNotEqual(first["id"], second["id"])
            con.execute("UPDATE assistant_actions SET expires_at=0 WHERE id=?", (second["id"],))
            third = assistant.prepare(service, "create_clients", args)
            self.assertNotEqual(second["id"], third["id"])
            # Use real conversation IDs to preserve the foreign-key contract.
            thread = self.call("/assistant/conversations", "POST", {"title": "Other"}, token)[1]["conversation"]
            service.assistant_conversation_id = thread["id"]
            fourth = assistant.prepare(service, "create_clients", args)
            self.assertNotEqual(third["id"], fourth["id"])

    def test_canonical_tool_calls_produce_one_card_in_a_model_turn(self):
        token, _ = self.account("dedup-model-turn")
        calls = [{"id": "same-" + str(i), "type": "function", "function": {
            "name": "create_clients", "arguments": json.dumps({"name": "Client", **extra}),
        }} for i, extra in enumerate(({}, {"discarded": "a"}, {"discarded": "b"}))]
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch(
            "backend.assistant.query_model", return_value={"content": None, "tool_calls": calls},
        ):
            code, reply = self.call("/assistant/chat", "POST", {"text": "Создай клиента"}, token)
        self.assertEqual(code, 200, reply)
        self.assertEqual(len(reply["actions"]), 1, reply)

    def action_race(self, label, mutation, undo=False):
        token, uid = self.account(label)
        with self.mod.db() as con:
            service = self.service(con, token, uid)
            action = assistant.prepare(service, "create_clients", {"name": "Protected"})
            if undo:
                # Use a reversible edit rather than creation for the undo path.
                assistant.confirm(service, action["id"])
                client = con.execute("SELECT * FROM clients WHERE workspace_id=?", (service.wid,)).fetchone()
                action = assistant.prepare(service, "update_clients", {"id": client["id"], "name": "Changed"})
                assistant.confirm(service, action["id"])
            mutation(con, uid, service.wid)
            with self.assertRaises(DomainError) as caught:
                if undo:
                    from backend.assistant_edits import undo as undo_action
                    undo_action(service, action["id"])
                else:
                    assistant.confirm(service, action["id"])
            self.assertIn(caught.exception.status, (401, 403))
            status = con.execute("SELECT status FROM assistant_actions WHERE id=?", (action["id"],)).fetchone()[0]
            self.assertEqual(status, "applied" if undo else "pending")

    def test_cached_owner_role_cannot_apply_after_membership_removed(self):
        self.action_race("remove-member", lambda con, uid, wid: con.execute(
            "DELETE FROM workspace_members WHERE workspace_id=? AND user_id=?", (wid, uid)))

    def test_cached_owner_role_cannot_apply_after_demotion(self):
        self.action_race("demote-member", lambda con, uid, wid: con.execute(
            "UPDATE workspace_members SET role='viewer' WHERE workspace_id=? AND user_id=?", (wid, uid)))

    def test_revoked_session_cannot_apply_pending_proposal(self):
        self.action_race("revoke-session", lambda con, uid, wid: con.execute(
            "DELETE FROM sessions WHERE user_id=?", (uid,)))

    def test_cached_finance_grant_is_rechecked_before_confirmation(self):
        token, uid = self.account("finance-cache-guard")
        item = self.call("/catalog", "POST", {"name": "Paint", "price": 10000, "cost_price": 4000}, token)[1]["item"]
        with self.mod.db() as con:
            service = self.service(con, token, uid)
            con.execute("UPDATE workspace_members SET role='member' WHERE workspace_id=? AND user_id=?", (service.wid, uid))
            con.execute("UPDATE workspaces SET settings=? WHERE id=?", (json.dumps({"finance_access": [uid]}), service.wid))
            service.role = "member"
            self.assertTrue(service.finance_visible())
            action = assistant.prepare(service, "update_catalog", {"id": item["id"], "cost_price": 5000})
            con.execute("UPDATE workspaces SET settings='{}' WHERE id=?", (service.wid,))
            with self.assertRaises(DomainError) as caught:
                assistant.confirm(service, action["id"])
            self.assertEqual(caught.exception.status, 403)
            self.assertEqual(con.execute("SELECT cost_price FROM catalog_items WHERE id=?", (item["id"],)).fetchone()[0], 4000)

    def test_blocked_account_cannot_undo_an_applied_action(self):
        self.action_race("block-undo", lambda con, uid, wid: con.execute(
            "UPDATE users SET blocked=1 WHERE id=?", (uid,)), undo=True)
