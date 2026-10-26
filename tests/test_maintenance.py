"""Expiry cleanup and protected cron tests across local database backend."""
import json
import os
import unittest
from unittest.mock import patch

from backend import maintenance
from tests.test_business import BusinessFlows
from tests.test_security_hardening import SecurityHardeningTests


class MaintenanceTests(SecurityHardeningTests):
    """Reuse the running local HTTP server and reset fixture DB per test."""
    account = BusinessFlows.account
    call = BusinessFlows.call

    def test_cron_requires_strong_secret_before_opening_database(self):
        with patch.dict(os.environ, {"CRON_SECRET": "a" * 48}):
            with patch.object(self.mod, "db", side_effect=AssertionError("DB opened")):
                for authorization in ("", "Bearer wrong", "Bearer " + "a" * 47):
                    status,_,_ = self.request(
                        "GET", "/api/cron/maintenance",
                        headers={"Authorization":authorization} if authorization else {},
                    )
                    self.assertEqual(status,401)
                status,_,_=self.request("POST","/api/cron/maintenance")
                self.assertEqual(status,404)

    def test_expired_records_are_removed_but_active_and_recent_are_safe(self):
        session, user_id = self.account("cleanup-person")
        now = int(__import__("time").time())
        expired = now - 125 * 86400
        recent = now + 86400
        with self.mod.db() as con:
            for suffix,until in (("old", expired),("new", recent)):
                con.execute(
                    "INSERT INTO email_login_challenges "
                    "(id,email,code_hash,intent,name,legal_version,attempts,expires_at,created_at) "
                    "VALUES(?,?,?,?,?,?,0,?,?)",
                    ("cleanup-code-"+suffix, "cleanup-"+suffix+"@example.test", "x"*64, "login", "", "", until, now-200*86400),
                )
                con.execute(
                    "INSERT INTO email_tokens(id,user_id,token_hash,purpose,expires_at) VALUES(?,?,?,?,?)",
                    ("cleanup-mail-"+suffix,user_id,"h-"+suffix,"verify",until),
                )
                con.execute(
                    "INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)",
                    ("cleanup-session-"+suffix,user_id,"session-"+suffix,until),
                )
                con.execute(
                    "INSERT INTO oauth_states(state_hash,provider,verifier,browser_hash,expires_at) "
                    "VALUES(?,?,?,?,?)",
                    ("cleanup-state-"+suffix,"yandex","verifier","browser",until),
                )
                con.execute(
                    "INSERT INTO oauth_tickets(ticket_hash,user_id,challenge,expires_at) VALUES(?,?,?,?)",
                    ("cleanup-ticket-"+suffix,user_id,"challenge",until),
                )
                con.execute(
                    "INSERT INTO rate_limits(key,count,started) VALUES(?,?,?)",
                    ("cleanup-quota-"+suffix,21,until),
                )
            result=maintenance.cleanup(con,now=now)
            self.assertEqual(set(result["removed"]),{r[0] for r in maintenance.RETENTION})
            # Only the six fixture tables above have cleanup-old/new records.
            # Newly added partner tables are tested separately.
            fixture_tables = {
                "sessions", "email_tokens", "email_login_challenges",
                "oauth_states", "oauth_tickets", "rate_limits",
            }
            for table,primary,_,_ in maintenance.RETENTION:
                if table not in fixture_tables:
                    continue
                old=con.execute(f"SELECT 1 FROM {table} WHERE {primary}=?",("cleanup-"+{
                    "sessions":"session","email_tokens":"mail",
                    "email_login_challenges":"code","oauth_states":"state",
                    "oauth_tickets":"ticket","rate_limits":"quota",
                }[table]+"-old",)).fetchone()
                new=con.execute(f"SELECT 1 FROM {table} WHERE {primary}=?",("cleanup-"+{
                    "sessions":"session","email_tokens":"mail",
                    "email_login_challenges":"code","oauth_states":"state",
                    "oauth_tickets":"ticket","rate_limits":"quota",
                }[table]+"-new",)).fetchone()
                self.assertIsNone(old,table)
                self.assertIsNotNone(new,table)
            self.assertIsNotNone(con.execute(
                "SELECT id FROM sessions WHERE token_hash=?", (__import__("hashlib").sha256(session.encode()).hexdigest(),)
            ).fetchone())

    def test_partner_sessions_and_clicks_retention_without_deleting_finance(self):
        from backend import partner_platform as partner
        now = int(__import__("time").time())
        with self.mod.db() as con:
            record = partner.create_partner(con, {
                "code": "cleanup-partner", "name": "Retention Test",
                "allowed_host": "cleanup.example.org",
            })
            key = record["api_key"]
            holder = partner.auth_partner(con, "Partner " + key)
            partner.begin_visit(con, holder["code"])
            old_session = partner.new_console_session(con, "Partner " + key)
            old_hash = __import__("hashlib").sha256(old_session["session_token"].encode()).hexdigest()
            con.execute("UPDATE partner_clicks SET expires_at=? WHERE partner_id=?",
                        (now - 30 * 86400, holder["id"]))
            con.execute("UPDATE partner_console_sessions SET expires_at=? WHERE partner_id=?",
                        (now - 20 * 86400, holder["id"]))
            outcome = maintenance.cleanup(con, now=now, per_table=20)
            self.assertGreaterEqual(outcome["removed"]["partner_clicks"], 1)
            self.assertGreaterEqual(outcome["removed"]["partner_console_sessions"], 1)
            self.assertIsNone(con.execute(
                "SELECT id FROM partner_console_sessions WHERE session_hash=?", (old_hash,)
            ).fetchone())
            self.assertIsNotNone(con.execute(
                "SELECT id FROM partner_accounts WHERE id=?", (holder["id"],)
            ).fetchone())

    def test_per_table_batch_caps_work_to_prevent_long_transactions(self):
        now=1_800_000_000
        with self.mod.db() as con:
            for index in range(7):
                con.execute("INSERT INTO rate_limits(key,count,started) VALUES(?,?,?)",
                            ("cleanup-batch-"+str(index),1,now-130*86400))
            first=maintenance.cleanup(con,now=now,per_table=2)
            self.assertEqual(first["removed"]["rate_limits"],2)
            last=con.execute("SELECT count(*) FROM rate_limits WHERE key LIKE 'cleanup-batch-%'").fetchone()[0]
            self.assertEqual(last,5)
            second=maintenance.cleanup(con,now=now,per_table=2)
            self.assertEqual(second["removed"]["rate_limits"],2)

    def test_authorized_cron_route_is_bounded_and_has_no_secrets(self):
        secret="q"*48
        with patch.dict(os.environ,{"CRON_SECRET":secret}):
            code,_,payload=self.request("GET","/api/cron/maintenance",
                headers={"Authorization":"Bearer "+secret})
        self.assertEqual(code,200,payload)
        self.assertEqual(payload["batch_limit"],4000)
        self.assertEqual(payload["ok"],True)
        self.assertNotIn(secret,json.dumps(payload))


if __name__=="__main__":
    unittest.main()
