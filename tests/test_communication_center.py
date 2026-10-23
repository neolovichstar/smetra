import sqlite3
import unittest

from backend.community import (
    _add_member,
    _add_message,
    _list_conversations,
    _new_conversation,
    ensure_sqlite_schema,
    make_public_id,
    normalize_public_id,
    wants_human,
)


class CommunicationHelpersTests(unittest.TestCase):
    def test_public_id_is_stable_and_normalized(self):
        user_id = "8c745181-e71d-4b90-9c51-d89f9017a0fe"
        public_id = make_public_id(user_id)
        self.assertEqual(public_id, "SM-8C745181E71D4B909C51D89F9017A0FE")
        self.assertEqual(normalize_public_id(public_id), user_id.replace("-", "").upper())
        self.assertEqual(normalize_public_id(public_id.lower()), user_id.replace("-", "").upper())
        self.assertIsNone(normalize_public_id("user@example.com"))
        self.assertIsNone(normalize_public_id("SM-123"))

    def test_explicit_human_requests_are_detected(self):
        self.assertTrue(wants_human("Позови сотрудника поддержки"))
        self.assertTrue(wants_human("Соедини меня с человеком"))
        self.assertTrue(wants_human("Хочу поговорить с оператором"))
        self.assertFalse(wants_human("Как изменить название сметы?"))

    def test_conversation_membership_and_message_list(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(
            "CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user')"
        )
        con.executemany(
            "INSERT INTO users(id,name,email,role) VALUES(?,?,?,?)",
            [
                ("user-a", "Алексей", "a@example.test", "user"),
                ("user-b", "Мария", "b@example.test", "user"),
            ],
        )
        ensure_sqlite_schema(con)
        chat_id = _new_conversation(
            con, "direct", "Мария", "user-a", direct_key="user-a:user-b"
        )
        _add_member(con, chat_id, "user-a", "member")
        _add_member(con, chat_id, "user-b", "member")
        saved = _add_message(con, chat_id, "user-a", "user", "Проверим правки?")
        self.assertEqual(saved["body"], "Проверим правки?")
        visible = _list_conversations(con, "user-b", ("direct",))
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["id"], chat_id)
        self.assertEqual(visible[0]["last_message"], "Проверим правки?")
        self.assertEqual(_list_conversations(con, "user-a", ("support",)), [])
        con.close()


if __name__ == "__main__":
    unittest.main()
