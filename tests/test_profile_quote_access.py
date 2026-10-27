"""Regression checks for sharing authored quotes after workspace access changes."""
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import patch
from tests.test_business import BusinessFlows as Flows


class ProfileQuoteAccessTests(unittest.TestCase):
    setUpClass = classmethod(Flows.setUpClass.__func__)
    tearDownClass = classmethod(Flows.tearDownClass.__func__)
    setUp = Flows.setUp
    call = Flows.call
    account = Flows.account
    quote = Flows.quote
    publish = Flows.publish

    def team_quote(self):
        owner, _ = self.account("share-owner-" + uuid.uuid4().hex[:8])
        author, author_id = self.account("share-author-" + uuid.uuid4().hex[:8])
        client, client_id = self.account("share-client-" + uuid.uuid4().hex[:8])
        quote = self.publish(author, self.quote(author))
        wid = self.call("/workspace", token=owner)[1]["workspace"]["id"]
        with self.mod.db() as con:
            con.execute("UPDATE quotes SET workspace_id=? WHERE id=?", (wid, quote["id"]))
            con.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(?,?,'manager')", (wid, author_id))
        return author, author_id, client, client_id, quote, wid

    def test_revoked_author_cannot_list_or_send_team_quotes(self):
        author, author_id, _, client_id, quote, wid = self.team_quote()
        payload = {"quote_id": quote["id"], "public_id": "SM-" + client_id.replace("-", "").upper()}
        self.assertIn(quote["id"], [q["id"] for q in self.call("/profile/shareable-quotes", token=author)[1]["quotes"]])
        with self.mod.db() as con:
            con.execute("DELETE FROM workspace_members WHERE workspace_id=? AND user_id=?", (wid, author_id))
        self.assertNotIn(quote["id"], [q["id"] for q in self.call("/profile/shareable-quotes", token=author)[1]["quotes"]])
        self.assertEqual(self.call("/profile/quote-chats", "POST", payload, author)[0], 404)
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM chat_conversations WHERE quote_id=?", (quote["id"],)).fetchone()[0], 0)

    def test_downgraded_author_cannot_share_using_profile_api(self):
        author, author_id, _, client_id, quote, wid = self.team_quote()
        with self.mod.db() as con:
            con.execute("UPDATE workspace_members SET role='viewer' WHERE workspace_id=? AND user_id=?", (wid, author_id))
        self.assertNotIn(quote["id"], [q["id"] for q in self.call("/profile/shareable-quotes", token=author)[1]["quotes"]])
        self.assertEqual(self.call("/profile/quote-chats", "POST", {"quote_id": quote["id"], "public_id": "SM-" + client_id.replace("-", "").upper()}, author)[0], 404)

    def test_private_draft_cannot_be_shared_until_republished(self):
        author, _ = self.account("published-author")
        _, recipient_id = self.account("published-recipient")
        published = self.publish(author, self.quote(author, title="Published customer title"))
        code, result = self.call("/quotes/" + published["id"], "PATCH", {"revision": published["revision"], "title": "PRIVATE DRAFT TITLE"}, author)
        self.assertEqual(code, 200, result)
        choices = self.call("/profile/shareable-quotes", token=author)[1]["quotes"]
        self.assertNotIn(published["id"], [q["id"] for q in choices])
        code, result = self.call("/profile/quote-chats", "POST", {"quote_id": published["id"], "version": published["published_version"], "public_id": "SM-" + recipient_id.replace("-", "").upper()}, author)
        self.assertEqual(code, 409, result)

    def test_membership_is_rechecked_after_the_initial_quote_lookup(self):
        from backend.business import transaction

        author, author_id, _, client_id, quote, wid = self.team_quote()

        @contextmanager
        def revoked_before_lock(con, **kwargs):
            con.execute("DELETE FROM workspace_members WHERE workspace_id=? AND user_id=?", (wid, author_id))
            with transaction(con, **kwargs):
                yield

        with patch("backend.business.transaction", revoked_before_lock):
            code, result = self.call("/profile/quote-chats", "POST", {"quote_id": quote["id"], "public_id": "SM-" + client_id.replace("-", "").upper()}, author)
        self.assertEqual(code, 404, result)
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM chat_conversations WHERE quote_id=?", (quote["id"],)).fetchone()[0], 0)

    def test_unverified_sender_cannot_send_quote(self):
        author, author_id = self.account("unverified-author")
        _, client_id = self.account("unverified-client")
        quote = self.publish(author, self.quote(author))
        with self.mod.db() as con:
            con.execute("UPDATE users SET email_verified_at=NULL WHERE id=?", (author_id,))
        self.assertEqual(self.call("/profile/quote-chats", "POST", {"quote_id": quote["id"], "public_id": "SM-" + client_id.replace("-", "").upper()}, author)[0], 403)


del Flows
