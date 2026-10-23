import os
import unittest
from unittest.mock import patch

from tests import test_business


class CommunicationTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    account = test_business.BusinessFlows.account
    call = test_business.BusinessFlows.call

    def public_id(self, token):
        status, result = self.call("/me", token=token)
        self.assertEqual(status, 200, result)
        return result["user"]["public_id"]

    def test_registration_creates_searchable_public_id_without_leaking_email(self):
        first, first_id = self.account("directory-first")
        second, _ = self.account("directory-second")
        first_public = self.public_id(first)
        second_public = self.public_id(second)
        self.assertRegex(first_public, r"^SM-[A-F0-9]{16}$")
        self.assertRegex(second_public, r"^SM-[A-F0-9]{16}$")
        self.assertNotEqual(first_public, second_public)

        status, result = self.call("/people?q=" + first_public, token=second)
        self.assertEqual(status, 200, result)
        self.assertEqual(len(result["items"]), 1)
        person = result["items"][0]
        self.assertEqual(person["id"], first_id)
        self.assertEqual(person["public_id"], first_public)
        self.assertEqual(person["name"], "directory-first")
        self.assertNotIn("email", person)
        self.assertNotIn("password_hash", person)

        status, result = self.call("/profile", token=first)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["profile"]["public_id"], first_public)

    def test_direct_chat_is_private_and_pair_creation_is_idempotent(self):
        one, _ = self.account("direct-one")
        two, two_id = self.account("direct-two")
        stranger, _ = self.account("direct-stranger")
        target_id = self.public_id(two)
        status, created = self.call("/conversations", "POST", {
            "kind": "direct", "target_public_id": target_id,
        }, one)
        self.assertEqual(status, 200, created)
        self.assertTrue(created["created"])
        conversation_id = created["conversation_id"]

        status, existing = self.call("/conversations", "POST", {
            "kind": "direct", "target_public_id": self.public_id(one),
        }, two)
        self.assertEqual(status, 200, existing)
        self.assertEqual(existing["conversation_id"], conversation_id)
        self.assertFalse(existing["created"])

        status, sent = self.call("/conversations/" + conversation_id + "/messages", "POST", {
            "message": "Проверьте, пожалуйста, строку по электрике.",
        }, one)
        self.assertEqual(status, 200, sent)
        self.assertTrue(any(m["body"].startswith("Проверьте") for m in sent["messages"]))

        status, received = self.call("/conversations/" + conversation_id + "/messages", token=two)
        self.assertEqual(status, 200, received)
        self.assertTrue(any(m["sender_id"] != two_id and m["body"].startswith("Проверьте") for m in received["messages"]))
        self.assertEqual(self.call("/conversations/" + conversation_id + "/messages", token=stranger)[0], 404)
        self.assertEqual(self.call("/conversations/" + conversation_id + "/messages", "POST", {
            "message": "Чужое сообщение",
        }, stranger)[0], 404)

    def test_support_is_a_free_ai_chat_with_reliable_human_escalation(self):
        token, user_id = self.account("support-customer")
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            status, created = self.call("/support", "POST", {
                "subject": "Не открывается смета",
                "message": "После нажатия на смету вижу пустую страницу.",
            }, token)
            self.assertEqual(status, 201, created)
            ticket = created["ticket"]
            self.assertEqual(ticket["user_id"], user_id)
            self.assertGreaterEqual(len(created["messages"]), 2)
            self.assertEqual(created["messages"][0]["sender_role"], "user")
            self.assertEqual(created["messages"][1]["sender_role"], "ai")
            ticket_id = ticket["id"]

            status, replied = self.call("/support/" + ticket_id + "/messages", "POST", {
                "message": "Я использую браузер на компьютере.",
            }, token)
            self.assertEqual(status, 200, replied)
            self.assertTrue(any(m["sender_role"] == "ai" for m in replied["messages"]))

            stranger, _ = self.account("support-stranger")
            self.assertEqual(self.call("/support/" + ticket_id + "/messages", token=stranger)[0], 404)

            status, escalated = self.call("/support/" + ticket_id + "/escalate", "POST", {}, token)
            self.assertEqual(status, 200, escalated)
            self.assertTrue(escalated["ticket"]["needs_human"])
            self.assertEqual(escalated["ticket"]["ai_state"], "human")

            admin_token, admin_id = self.account("support-admin")
            with self.mod.db() as con:
                con.execute("UPDATE users SET role='admin' WHERE id=?", (admin_id,))
            status, admin_thread = self.call("/admin/support/" + ticket_id + "/messages", token=admin_token)
            self.assertEqual(status, 200, admin_thread)
            status, answer = self.call("/admin/support/" + ticket_id + "/messages", "POST", {
                "message": "Я подключился к обращению. Давайте проверим это вместе.",
            }, admin_token)
            self.assertEqual(status, 200, answer)
            self.assertTrue(any(m["sender_role"] == "admin" for m in answer["messages"]))
            self.assertTrue(answer["ticket"]["needs_human"])

            status, items = self.call("/support", token=token)
            self.assertEqual(status, 200, items)
            self.assertTrue(any(item["id"] == ticket_id and item["needs_human"] for item in items["items"]))

    def test_community_rooms_are_joined_before_reading_and_posting(self):
        member, _ = self.account("community-member")
        stranger, _ = self.account("community-stranger")
        status, listed = self.call("/community", token=member)
        self.assertEqual(status, 200, listed)
        self.assertEqual({room["id"] for room in listed["items"]}, {
            "community_general", "community_finishing", "community_electrical",
            "community_plumbing", "community_subcontract",
        })
        room = next(row for row in listed["items"] if row["id"] == "community_electrical")
        status, joined = self.call("/community/" + room["id"] + "/join", "POST", {}, member)
        self.assertEqual(status, 200, joined)
        conversation_id = joined["conversation_id"]
        self.assertEqual(self.call("/conversations/" + conversation_id + "/messages", "POST", {
            "message": "Коллеги, какой кабель закладываете на этот участок?",
        }, member)[0], 200)
        self.assertEqual(self.call("/conversations/" + conversation_id + "/messages", token=stranger)[0], 404)

    def test_quote_publish_creates_a_private_quote_conversation(self):
        token, _ = self.account("quote-chat-owner")
        status, created = self.call("/quotes", "POST", {
            "title": "Электромонтаж",
            "client": "Заказчик",
            "amount": 125000,
        }, token)
        self.assertEqual(status, 201, created)
        quote = created["quote"]
        status, published = self.call("/quotes/" + quote["id"] + "/publish", "POST", {
            "revision": quote["revision"],
        }, token)
        self.assertEqual(status, 200, published)
        status, chats = self.call("/conversations", token=token)
        self.assertEqual(status, 200, chats)
        self.assertTrue(any(item["kind"] == "quote" and item["quote_id"] == quote["id"] for item in chats["items"]))

    def test_object_chat_requires_active_team_subscription(self):
        token, owner_id = self.account("team-chat-owner")
        status, workspace_result = self.call("/workspace", token=token)
        self.assertEqual(status, 200, workspace_result)
        workspace_id = workspace_result["workspace"]["id"]
        status, project_result = self.call("/projects", "POST", {"name": "ЖК Октябрьский"}, token, workspace_id)
        self.assertEqual(status, 201, project_result)
        project_id = project_result["item"]["id"]
        status, denied = self.call("/conversations", "POST", {
            "kind": "workspace", "workspace_id": workspace_id, "object_id": project_id,
        }, token)
        self.assertEqual(status, 403, denied)

        with self.mod.db() as con:
            con.execute(
                "UPDATE workspaces SET plan='pro_team',subscription_status='active',entitlement_until=?,seat_limit=5 WHERE id=?",
                (self.mod.now()+86400, workspace_id),
            )
        status, created = self.call("/conversations", "POST", {
            "kind": "workspace", "workspace_id": workspace_id, "object_id": project_id,
        }, token)
        self.assertEqual(status, 200, created)
        status, chats = self.call("/conversations", token=token)
        self.assertTrue(any(item["id"] == created["conversation_id"] and item["kind"] == "workspace" for item in chats["items"]))


if __name__ == "__main__":
    unittest.main()
