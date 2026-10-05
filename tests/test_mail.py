import os
import ssl
import unittest
from unittest.mock import patch

from backend import app


class MailTransportTests(unittest.TestCase):
    def send(self, port):
        settings = {
            "SMTP_HOST": "smtp.yandex.ru",
            "SMTP_PORT": str(port),
            "SMTP_USER": "sender@yandex.ru",
            "SMTP_PASSWORD": "fixture-app-password",
            "SMTP_FROM": "sender@yandex.ru",
        }
        with patch.dict(os.environ, settings), patch.object(
            app.smtplib, "SMTP"
        ) as plain, patch.object(app.smtplib, "SMTP_SSL") as implicit:
            app.mail("recipient@example.invalid", "Subject", "Message")
        return plain, implicit

    def test_yandex_465_uses_verified_implicit_tls(self):
        plain, implicit = self.send(465)
        plain.assert_not_called()
        context = implicit.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        client = implicit.return_value.__enter__.return_value
        client.starttls.assert_not_called()
        client.login.assert_called_once_with(
            "sender@yandex.ru", "fixture-app-password"
        )
        message = client.send_message.call_args.args[0]
        self.assertEqual(message["From"], "sender@yandex.ru")
        self.assertEqual(message["To"], "recipient@example.invalid")

    def test_587_upgrades_tls_before_authentication(self):
        plain, implicit = self.send(587)
        implicit.assert_not_called()
        client = plain.return_value.__enter__.return_value
        self.assertEqual(
            [call[0] for call in client.mock_calls],
            ["starttls", "login", "send_message"],
        )
        context = client.starttls.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_missing_password_does_not_connect(self):
        with patch.dict(os.environ, {"SMTP_PASSWORD": ""}), patch.object(
            app.smtplib, "SMTP"
        ) as plain, patch.object(app.smtplib, "SMTP_SSL") as implicit:
            with self.assertRaises(app.ApiError) as error:
                app.mail("recipient@example.invalid", "Subject", "Message")
            self.assertEqual(error.exception.status, 503)
            plain.assert_not_called()
            implicit.assert_not_called()
