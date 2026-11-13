"""Real HTTP tests of email OTP; never call external SMTP."""
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import unittest
from unittest.mock import patch

from tests import test_business
from backend import email_otp

BusinessFlows = test_business.BusinessFlows


CONFIG = {
    "SMTP_HOST": "smtp.mail.ru",
    "SMTP_USER": "noreply@smetra.online",
    "SMTP_FROM": "noreply@smetra.online",
    "SMTP_PASSWORD": "local-fixture-never-send",
    "EMAIL_CODE_HMAC_SECRET": "test-otp-secret-for-smetra-123456789abcdef",
}

class EmailOTPTests(unittest.TestCase):
    setUpClass=classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass=classmethod(BusinessFlows.tearDownClass.__func__)
    setUp=BusinessFlows.setUp
    call=BusinessFlows.call
    account=BusinessFlows.account

    def test_six_digit_registration_and_one_time_use(self):
        email="otp-register@local.test"
        payload={
            "email":email,"intent":"register","name":"Строитель",
            "legal_acceptance":True,
            "legal_version":"2026-10-19-registration-v1",
        }
        with patch.dict(os.environ,CONFIG),patch(
            "backend.email_otp.secrets.randbelow",return_value=12345
        ),patch("backend.email_otp.deliver") as sender:
            status,data=self.call("/auth/email/start","POST",payload)
            self.assertEqual(status,200,data)
            challenge=data["challenge_id"]
            sender.assert_called_once_with(email,"012345","register")
            with self.mod.db() as con:
                stored=con.execute("SELECT * FROM email_login_challenges WHERE id=?",(challenge,)).fetchone()
                self.assertNotEqual(stored["code_hash"],"012345")
                self.assertEqual(con.execute("SELECT count(*) FROM users WHERE email=?",(email,)).fetchone()[0],0)
            self.assertEqual(self.call("/auth/email/confirm","POST",{
                "challenge_id":challenge,"code":"012345",
            })[0],200)
            with self.mod.db() as con:
                user=con.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
                self.assertIsNotNone(user["email_verified_at"])
                self.assertEqual(con.execute("SELECT count(*) FROM legal_acceptances WHERE user_id=?",(user["id"],)).fetchone()[0],1)
            self.assertEqual(self.call("/auth/email/confirm","POST",{
                "challenge_id":challenge,"code":"012345",
            })[0],400)

    def test_existing_email_login_reuses_account(self):
        session, user_id = self.account("otp-existing")
        email="otp-existing@test.invalid"
        with patch.dict(os.environ,CONFIG),patch(
            "backend.email_otp.secrets.randbelow",return_value=987654
        ),patch("backend.email_otp.deliver") as sender:
            status,start=self.call("/auth/email/start","POST",{
                "email":email,"intent":"register","name":"Новая запись",
                "legal_acceptance":True,"legal_version":"2026-10-19-registration-v1",
            })
            self.assertEqual(status,200,start)
            sender.assert_called_once_with(email,"987654","login")
            status,data=self.call("/auth/email/confirm","POST",{
                "challenge_id":start["challenge_id"],"code":"987654",
            })
            self.assertEqual(status,200,data)
            self.assertEqual(data["user"]["id"],user_id)
            with self.mod.db() as con:
                self.assertEqual(con.execute("SELECT count(*) FROM users WHERE email=?",(email,)).fetchone()[0],1)

    def test_smtp_failure_keeps_previous_unexpired_code_valid(self):
        from smtplib import SMTPException
        email="otp-mail-outage@local.test"
        request={
            "email":email,"intent":"register","name":"Монтажник",
            "legal_acceptance":True,"legal_version":"2026-10-19-registration-v1",
        }
        with patch.dict(os.environ,CONFIG),patch(
            "backend.email_otp.secrets.randbelow",return_value=246810
        ),patch("backend.email_otp.deliver"):
            status,first=self.call("/auth/email/start","POST",request)
            self.assertEqual(status,200,first)
        with patch.dict(os.environ,CONFIG),patch(
            "backend.email_otp.deliver",side_effect=SMTPException("temporary outage")
        ):
            self.assertEqual(self.call("/auth/email/start","POST",request)[0],503)
        with patch.dict(os.environ,CONFIG):
            result,data=self.call("/auth/email/confirm","POST",{
                "challenge_id":first["challenge_id"],"code":"246810",
            })
        self.assertEqual(result,200,data)

    def test_successful_resend_revokes_old_code(self):
        email="otp-resend@local.test"
        request={
            "email":email,"intent":"register","name":"Монтажник",
            "legal_acceptance":True,"legal_version":"2026-10-19-registration-v1",
        }
        with patch.dict(os.environ,CONFIG),patch(
            "backend.email_otp.deliver"
        ),patch("backend.email_otp.secrets.randbelow",side_effect=(111111,222222)):
            status,first=self.call("/auth/email/start","POST",request)
            self.assertEqual(status,200)
            status,second=self.call("/auth/email/start","POST",request)
            self.assertEqual(status,200)
        with patch.dict(os.environ,CONFIG):
            self.assertEqual(self.call("/auth/email/confirm","POST",{
                "challenge_id":first["challenge_id"],"code":"111111",
            })[0],400)
            self.assertEqual(self.call("/auth/email/confirm","POST",{
                "challenge_id":second["challenge_id"],"code":"222222",
            })[0],200)

    def test_overlapping_resends_leave_one_delivered_code_active(self):
        email = "otp-parallel-resend@local.test"
        payload = {
            "email": email, "intent": "register", "name": "Монтажник",
            "legal_acceptance": True, "legal_version": "2026-10-19-registration-v1",
        }
        first_sending, release_first = threading.Event(), threading.Event()

        def deliver(address, code, intent):
            if code == "111111":
                first_sending.set()
                if not release_first.wait(5):
                    raise TimeoutError("test delivery synchronization")

        with patch.dict(os.environ, CONFIG), \
                patch("backend.email_otp.secrets.randbelow", side_effect=(111111, 222222)), \
                patch("backend.email_otp.deliver", side_effect=deliver), \
                ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.call, "/auth/email/start", "POST", payload)
            try:
                self.assertTrue(first_sending.wait(5))
                status, second = pool.submit(self.call, "/auth/email/start", "POST", payload).result(5)
                self.assertEqual(status, 200, second)
            finally:
                release_first.set()
            status, last = first.result(5)
            self.assertEqual(status, 200, last)
            self.assertEqual(self.call("/auth/email/confirm", "POST", {
                "challenge_id": second["challenge_id"], "code": "222222",
            })[0], 400)
            self.assertEqual(self.call("/auth/email/confirm", "POST", {
                "challenge_id": last["challenge_id"], "code": "111111",
            })[0], 200)

    def test_session_failure_rolls_back_registration_and_leaves_code_usable(self):
        email = "otp-session-retry@local.test"
        with patch.dict(os.environ, CONFIG), patch("backend.email_otp.deliver"), \
                patch("backend.email_otp.secrets.randbelow", return_value=143625):
            status, started = self.call("/auth/email/start", "POST", {
                "email": email, "intent": "register", "name": "Монтажник",
                "legal_acceptance": True, "legal_version": "2026-10-19-registration-v1",
            })
            self.assertEqual(status, 200, started)
            payload = {"challenge_id": started["challenge_id"], "code": "143625"}
            with patch.object(self.mod.Handler, "create_login", side_effect=RuntimeError("fixture session failure")):
                self.assertEqual(self.call("/auth/email/confirm", "POST", payload)[0], 500)
            with self.mod.db() as con:
                self.assertIsNone(con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone())
            self.assertEqual(self.call("/auth/email/confirm", "POST", payload)[0], 200)

    def test_wrong_code_burns_limited_attempts(self):
        with patch.dict(os.environ,CONFIG),patch(
            "backend.email_otp.secrets.randbelow",return_value=123456
        ),patch("backend.email_otp.deliver"):
            status,result=self.call("/auth/email/start","POST",{
                "email":"otp-wrong@local.test","intent":"register","name":"Иван",
                "legal_acceptance":True,"legal_version":"2026-10-19-registration-v1",
            })
            self.assertEqual(status,200)
            challenge=result["challenge_id"]
            for index in range(5):
                self.assertEqual(self.call("/auth/email/confirm","POST",{
                    "challenge_id":challenge,"code":"888888",
                })[0],400)
            # The correct code no longer works: per-code limit (429) or burnt attempts (400).
            self.assertIn(self.call("/auth/email/confirm","POST",{
                "challenge_id":challenge,"code":"123456",
            })[0],(400,429))
            with self.mod.db() as con:
                self.assertEqual(con.execute("SELECT attempts FROM email_login_challenges WHERE id=?",
                                             (challenge,)).fetchone()[0],5)

    def test_login_unknown_does_not_leak_user_existence(self):
        with patch.dict(os.environ,CONFIG),patch("backend.email_otp.deliver") as sender:
            status,result=self.call("/auth/email/start","POST",{
                "email":"otp-unknown@local.test","intent":"login",
            })
            self.assertEqual(status,200,result)
            self.assertIn("challenge_id",result)
            sender.assert_not_called()

    def test_delivery_error_does_not_leave_usable_challenge(self):
        from smtplib import SMTPException
        with patch.dict(os.environ,CONFIG),patch(
            "backend.email_otp.deliver",side_effect=SMTPException("no smtp")
        ):
            self.assertEqual(self.call("/auth/email/start","POST",{
                "email":"otp-failed@local.test","intent":"register","name":"Иван",
                "legal_acceptance":True,"legal_version":"2026-10-19-registration-v1",
            })[0],503)
            with self.mod.db() as con:
                self.assertEqual(con.execute(
                    "SELECT count(*) FROM email_login_challenges WHERE email=?",
                    ("otp-failed@local.test",)).fetchone()[0],0)

    def test_smtp_auth_failure_is_classified_without_logging_secrets(self):
        from smtplib import SMTPAuthenticationError
        email="otp-smtp-diagnostics@local.test"
        payload={
            "email":email,"intent":"register","name":"Диагностика",
            "legal_acceptance":True,
            "legal_version":"2026-10-19-registration-v1",
        }
        with patch.dict(os.environ,CONFIG), patch(
            "backend.email_otp.deliver",
            side_effect=SMTPAuthenticationError(535,b"super-secret-provider-message"),
        ), patch("backend.email_otp.logger.warning") as log:
            status,body=self.call("/auth/email/start","POST",payload)
        self.assertEqual(status,503,body)
        self.assertIn("авторизацию отправителя",body["error"])
        log.assert_called_once()
        rendered=repr(log.call_args)
        self.assertIn("authentication",rendered)
        self.assertIn("535",rendered)
        self.assertNotIn("super-secret-provider-message",rendered)
        self.assertNotIn(email,rendered)
        with self.mod.db() as con:
            self.assertEqual(con.execute(
                "SELECT count(*) FROM email_login_challenges WHERE email=?",(email,)
            ).fetchone()[0],0)

    def test_malformed_code_consent_and_missing_smtp(self):
        with patch.dict(os.environ,CONFIG):
            self.assertEqual(self.call("/auth/email/start","POST",{
                "email":"bad","intent":"register","name":"И",
                "legal_acceptance":True,"legal_version":"2026-10-19-registration-v1",
            })[0],400)
            self.assertEqual(self.call("/auth/email/start","POST",{
                "email":"otp-missing@local.test","intent":"register","name":"Иван",
            })[0],400)
            self.assertEqual(self.call("/auth/email/confirm","POST",{
                "challenge_id":"bad","code":"012345",
            })[0],400)
        with patch.dict(os.environ,{"SMTP_PASSWORD":""}):
            self.assertEqual(self.call("/auth/email/start","POST",{
                "email":"otp-disabled@local.test","intent":"login",
            })[0],503)

    def test_smtp_mail_has_stable_sender_identity_and_standard_headers(self):
        from email.utils import parseaddr
        with patch.dict(os.environ,CONFIG),patch(
            "backend.email_otp.smtplib.SMTP_SSL"
        ) as transport:
            email_otp.deliver("user@example.org","047281","register")
        message=transport.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertEqual(parseaddr(message["From"])[1],"noreply@smetra.online")
        self.assertIn("Сметра",str(message["From"]))
        self.assertIn("@smetra.online>",str(message["Message-ID"]))
        self.assertEqual(message["Auto-Submitted"],"auto-generated")
        self.assertEqual(message["Reply-To"],"support@smetra.online")
        self.assertIsNotNone(message["Date"])
        self.assertTrue(message.is_multipart())
        self.assertIn("047281",message.get_body(preferencelist=("plain",)).get_content())
        self.assertIn("047281",message.get_body(preferencelist=("html",)).get_content())

    def test_email_template_has_code_boxes_and_selectable_code(self):
        subject,text,html=email_otp.email_content("036925","register")
        self.assertEqual(html.count('font:700 28px/52px'),6)
        self.assertIn('036925',html)
        self.assertIn('036925',text)
        self.assertIn('support@smetra.online',html)
        self.assertNotIn("<script",html)

    def test_temporary_email_shutdown_preserves_password_and_oauth_routes(self):
        # Establish an account before pausing new registration.
        token, _ = self.account("email-existing-after-pause")
        with patch.dict(os.environ, {**CONFIG, "EMAIL_OTP_ENABLED": "0", "EMAIL_SIGNUP_ENABLED": "0"}):
            status, capabilities = self.call("/auth/providers")
            self.assertEqual(status, 200, capabilities)
            self.assertFalse(capabilities["email_code_available"])
            self.assertFalse(capabilities["email_delivery_available"])
            self.assertFalse(capabilities["email_signup_available"])
            self.assertEqual(self.call("/auth/email/start", "POST", {
                "email": "closed@example.org", "intent": "register", "name": "Tester",
                "legal_acceptance": True, "legal_version": "2026-10-19-registration-v1",
            })[0], 503)
            self.assertEqual(self.call("/auth/register", "POST", {
                "email": "closed@example.org", "name": "Tester", "password": "longpassword123",
            })[0], 503)
            # Existing account/password authentication must remain available.
            self.assertEqual(self.call("/me", token=token)[0], 200)

    def test_email_signup_can_be_disabled_without_disabling_existing_code_logins(self):
        with patch.dict(os.environ, {**CONFIG, "EMAIL_OTP_ENABLED": "1", "EMAIL_SIGNUP_ENABLED": "0"}):
            status, capabilities = self.call("/auth/providers")
            self.assertEqual(status, 200, capabilities)
            self.assertTrue(capabilities["email_code_available"])
            self.assertFalse(capabilities["email_signup_available"])
            self.assertEqual(self.call("/auth/email/start", "POST", {
                "email": "closed@example.org", "intent": "register", "name": "Tester",
                "legal_acceptance": True, "legal_version": "2026-10-19-registration-v1",
            })[0], 503)

    def test_frontend_has_paste_and_accessible_digits(self):
        from pathlib import Path
        web=Path(__file__).resolve().parents[1]/"apps/web"
        html=(web/"app.html").read_text(encoding="utf-8")
        js=(web/"auth-email.js").read_text(encoding="utf-8")
        self.assertEqual(html.count('inputmode="numeric"'),6)
        self.assertIn("clipboardData",js)
        self.assertIn('autocomplete="one-time-code"',html)
        # Capability/method transitions are exercised by dom_auth_email.cjs.


if __name__ == "__main__":
    unittest.main()
