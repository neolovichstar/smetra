"""Concurrent auth-token transactions must remain single-use under parallel requests."""

import hashlib
import secrets
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

from backend.app import begin_atomic_write, lock_user_row
from tests import test_business


class AuthTokenTransactionTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    account = test_business.BusinessFlows.account
    call = test_business.BusinessFlows.call

    def test_postgres_row_scoped_write_is_opt_in_and_sqlite_keeps_immediate_lock(self):
        postgres = Mock()
        postgres.is_postgres = True
        begin_atomic_write(postgres, row_scoped=True)
        postgres.execute.assert_called_once_with("BEGIN ROW")

        sqlite = Mock()
        sqlite.is_postgres = False
        begin_atomic_write(sqlite, row_scoped=True)
        sqlite.execute.assert_called_once_with("BEGIN IMMEDIATE")

    def test_user_row_lock_is_postgres_only(self):
        postgres = Mock()
        postgres.is_postgres = True
        lock_user_row(postgres, "user-1")
        postgres.execute.assert_called_once_with(
            "SELECT id FROM users WHERE id=? FOR UPDATE", ("user-1",)
        )
        postgres.execute.return_value.fetchone.assert_called_once_with()

        sqlite = Mock()
        sqlite.is_postgres = False
        lock_user_row(sqlite, "user-1")
        sqlite.execute.assert_not_called()

    def test_verification_token_is_consumed_once_under_concurrent_requests(self):
        _, user_id = self.account("verify-race-" + secrets.token_hex(4))
        with self.mod.db() as con:
            con.execute("UPDATE users SET email_verified_at=NULL WHERE id=?", (user_id,))
            token = self.mod.create_email_token(con, user_id, "verify", 3600)
        barrier = threading.Barrier(6)

        def verify(_):
            barrier.wait(timeout=5)
            return self.call("/auth/verify", "POST", {"token": token})[0]

        with ThreadPoolExecutor(max_workers=6) as executor:
            statuses = list(executor.map(verify, range(6)))

        self.assertEqual(statuses.count(200), 1, statuses)
        self.assertTrue(set(statuses).issubset({200, 400, 409}), statuses)
        with self.mod.db() as con:
            stored = con.execute(
                "SELECT consumed_at FROM email_tokens WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
            count = con.execute(
                "SELECT count(*) FROM events WHERE user_id=? AND name='email_verified'",
                (user_id,),
            ).fetchone()[0]
        self.assertIsNotNone(stored["consumed_at"])
        self.assertEqual(count, 1)

    def test_password_reset_token_is_consumed_once_under_concurrent_requests(self):
        _, user_id = self.account("reset-race-" + secrets.token_hex(4))
        with self.mod.db() as con:
            token = self.mod.create_email_token(con, user_id, "reset", 1800)
        passwords = ["New secure password " + str(i) + "!" for i in range(6)]
        barrier = threading.Barrier(len(passwords))

        def reset(password):
            barrier.wait(timeout=5)
            return self.call(
                "/auth/reset/confirm", "POST",
                {"token": token, "password": password},
            )[0], password

        with ThreadPoolExecutor(max_workers=len(passwords)) as executor:
            results = list(executor.map(reset, passwords))

        successful = [password for status, password in results if status == 200]
        statuses = [status for status, _ in results]
        self.assertEqual(len(successful), 1, statuses)
        self.assertTrue(set(statuses).issubset({200, 400, 409}), statuses)
        with self.mod.db() as con:
            stored = con.execute(
                "SELECT consumed_at FROM email_tokens WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
            user = con.execute(
                "SELECT password_hash FROM users WHERE id=?", (user_id,)
            ).fetchone()
            sessions = con.execute(
                "SELECT count(*) FROM sessions WHERE user_id=?", (user_id,)
            ).fetchone()[0]
        self.assertIsNotNone(stored["consumed_at"])
        self.assertTrue(self.mod.verify_password(successful[0], user["password_hash"]))
        self.assertEqual(sessions, 0)


if __name__ == "__main__":
    unittest.main()
