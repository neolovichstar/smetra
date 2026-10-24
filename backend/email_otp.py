"""Six-digit, server-verified email sign-in using VK WorkSpace SMTP.

A code proves access to a mailbox, not possession of a user-supplied name.
No code, mailbox password, or bearer token is exposed in logs or databases.
"""
import hashlib
import logging
import hmac
import os
import re
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from html import escape

logger = logging.getLogger("smetra.email")

TTL_SECONDS = 600
MAX_ATTEMPTS = 5
_EMAIL_RE = re.compile(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+\Z")
_CODE_RE = re.compile(r"[0-9]{6}\Z")


def configured():
    required = ("SMTP_HOST", "SMTP_FROM", "SMTP_USER", "SMTP_PASSWORD",
                "EMAIL_CODE_HMAC_SECRET")
    return all(os.getenv(name) for name in required) and len(
        os.getenv("EMAIL_CODE_HMAC_SECRET", "")
    ) >= 32


def _mailbox(value, error):
    email = str(value or "").strip().lower()
    if len(email) > 254 or not _EMAIL_RE.fullmatch(email):
        raise error(400, "Укажите корректную электронную почту")
    return email


def _digest(identifier, code):
    key = os.getenv("EMAIL_CODE_HMAC_SECRET", "")
    if len(key) < 32:
        raise RuntimeError("Email OTP secret is not configured")
    return hmac.new(key.encode(), (identifier + ":" + code).encode(), "sha256").hexdigest()


def email_content(code, intent):
    """Accessible HTML: separate visual digits plus selectable full code."""
    title = "Подтверждение регистрации" if intent == "register" else "Вход в Сметру"
    digits = "".join(
        '<td style="width:41px;height:52px;border:1px solid #34343a;'
        'border-radius:9px;background:#17171a;color:#f7f7f8;'
        'font:700 28px/52px Arial,sans-serif;text-align:center">' + escape(d) + '</td>'
        + ('<td style="width:7px"></td>' if i != 5 else "")
        for i, d in enumerate(code)
    )
    html = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:35px 14px;background:#09090b;color:#f5f5f6;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table role="presentation" width="100%" style="max-width:520px;border-collapse:collapse">
<tr><td style="padding:12px 0 28px;color:#fff;font-weight:800;font-size:25px;letter-spacing:-1px">сметра<span style="color:#babac1">.</span></td></tr>
<tr><td style="padding:26px 0 12px;border-top:1px solid #303034">
<p style="margin:0 0 14px;font-size:11px;letter-spacing:1.5px;color:#a5a5ae">ПОДТВЕРЖДЕНИЕ ПОЧТЫ</p>
<h1 style="font-size:30px;letter-spacing:-1px;line-height:1.18;margin:0 0 14px;color:#fff">{title}</h1>
<p style="font-size:14px;color:#b9b9c1;line-height:1.65;margin:0 0 25px">Введите этот код на сайте smetra.online. Он действует 10 минут.</p>
<table role="presentation" cellspacing="0" cellpadding="0"><tr>{digits}</tr></table>
<p style="font-size:13px;color:#a9a9b1;line-height:1.6;margin:22px 0 5px">Чтобы удобно скопировать код целиком:</p>
<p style="font:700 19px/1.6 Arial,sans-serif;letter-spacing:3px;color:#fff;margin:0 0 26px;user-select:all">{escape(code)}</p>
<p style="color:#94949e;font-size:12px;line-height:1.6;margin:0 0 26px">Не запрашивали код? Просто проигнорируйте письмо. Никому не сообщайте эти цифры.</p>
</td></tr>
<tr><td style="padding:22px 0;border-top:1px solid #303034;color:#888893;font-size:12px;line-height:1.7">Сметра · сметы и управление объектами<br>
Поддержка: <a href="mailto:support@smetra.online" style="color:#d2d2d9">support@smetra.online</a></td></tr>
</table></td></tr></table></body></html>"""
    plain = (
        f"сметра. — {title}\\n\\nКод подтверждения: {code}\\n"
        "Код действует 10 минут. Никому не сообщайте его.\\n"
        "Если вы не запрашивали код, проигнорируйте письмо.\\n\\n"
        "Поддержка: support@smetra.online"
    )
    return title + " · Сметра", plain.replace("\\n", "\n"), html


def deliver(address, code, intent):
    if not configured():
        raise RuntimeError("VK WorkSpace SMTP is not configured")
    subject, plain, html = email_content(code, intent)
    msg = EmailMessage()
    msg["To"] = address
    from backend.mail_headers import configure
    configure(msg, os.environ["SMTP_FROM"])
    msg["Subject"] = subject
    msg["Reply-To"] = "support@smetra.online"
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")
    port = int(os.getenv("SMTP_PORT", "465"))
    if port not in (465, 587):
        raise ValueError("SMTP port must use TLS (465 or 587)")
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, timeout=12, context=context) as smtp:
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=12) as smtp:
            smtp.starttls(context=context)
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)


def start(handler, con, app):
    if not configured():
        raise app.ApiError(503, "Регистрация по почте временно недоступна")
    data = handler.body()
    email = _mailbox(data.get("email"), app.ApiError)
    intent = data.get("intent")
    if intent not in ("login", "register"):
        raise app.ApiError(400, "Выберите вход или регистрацию")
    name = str(data.get("name", "")).strip()
    if intent == "register" and not 1 <= len(name) <= 80:
        raise app.ApiError(400, "Укажите имя")
    if intent == "register" and (
        data.get("legal_acceptance") is not True
        or data.get("legal_version") != app.REGISTRATION_CONSENT_VERSION
    ):
        raise app.ApiError(400, "Для регистрации примите условия сервиса")
    ip = handler.client_address[0]
    handler.throttle("email-start-ip:" + ip, 6, 600)
    handler.throttle("email-start-address:" + hashlib.sha256(email.encode()).hexdigest(),
                     4, 3600)
    existing = con.execute(
        "SELECT id FROM users WHERE email=? AND deleted_at IS NULL", (email,)
    ).fetchone()
    # Existing email owners may sign in through the registration tab.
    real_intent = "login" if existing else intent
    identifier = app.uid()
    code = f"{secrets.randbelow(1_000_000):06d}"
    moment = app.now()
    # Keep earlier still-valid codes until SMTP actually accepts the new
    # message. A transient mail outage must not lock someone out.
    con.execute(
        "INSERT INTO email_login_challenges "
        "(id,email,code_hash,intent,name,legal_version,attempts,expires_at,created_at,consumed_at) "
        "VALUES(?,?,?,?,?,?,0,?,?,NULL)",
        (identifier,email,_digest(identifier,code),real_intent,
         name if real_intent == "register" else "",
         app.REGISTRATION_CONSENT_VERSION if real_intent == "register" else "",
         moment + TTL_SECONDS,moment)
    )
    # Unknown login addresses receive a generic response; never reveal user enumeration.
    should_send = bool(existing) or intent == "register"
    if should_send:
        try:
            deliver(email,code,real_intent)
        except (OSError, smtplib.SMTPException, TimeoutError, ValueError) as exc:
            # Never log exception strings, raw SMTP responses, email addresses,
            # OTPs or credentials. Only a safe error category and numeric code
            # are needed to identify TLS, network and login failures.
            if isinstance(exc, smtplib.SMTPAuthenticationError):
                category = "authentication"
            elif isinstance(exc, smtplib.SMTPRecipientsRefused):
                category = "recipient_refused"
            elif isinstance(exc, smtplib.SMTPSenderRefused):
                category = "sender_refused"
            elif isinstance(exc, ssl.SSLError):
                category = "tls"
            elif isinstance(exc, (TimeoutError, ConnectionError)):
                category = "network"
            elif isinstance(exc, smtplib.SMTPException):
                category = "smtp_protocol"
            elif isinstance(exc, ValueError):
                category = "configuration"
            else:
                category = "transport"
            smtp_code = getattr(exc, "smtp_code", None)
            logger.warning(
                "email_otp_delivery_failed category=%s smtp_code=%s request_id=%s",
                category, smtp_code if isinstance(smtp_code, int) else "-",
                getattr(handler, "request_id", "-"),
            )
            con.execute("DELETE FROM email_login_challenges WHERE id=?", (identifier,))
            if category == "authentication":
                raise app.ApiError(
                    503, "Почтовый сервер отклонил авторизацию отправителя. Попробуйте позже"
                ) from None
            raise app.ApiError(503, "Не удалось отправить письмо. Попробуйте позже") from None
        # The new code was delivered; only now invalidate previous challenges.
        # Exclude the new ID so the same database update works across SQLite
        # and PostgreSQL (which commits individual statements in autocommit).
        con.execute(
            "UPDATE email_login_challenges SET consumed_at=? "
            "WHERE email=? AND id<>? AND consumed_at IS NULL",
            (app.now(), email, identifier),
        )
    return handler.send_json(200, {
        "ok": True, "challenge_id": identifier, "expires_in": TTL_SECONDS,
        "retry_after": 60, "message": "Если адрес доступен для этого действия, письмо отправлено",
    })


def confirm(handler, con, app):
    if not configured():
        raise app.ApiError(503, "Вход по почте временно недоступен")
    data = handler.body()
    identifier = str(data.get("challenge_id", ""))
    code = str(data.get("code", ""))
    if not re.fullmatch(r"[0-9a-f-]{36}\Z", identifier) or not _CODE_RE.fullmatch(code):
        raise app.ApiError(400, "Проверьте шестизначный код")
    handler.throttle("email-confirm-ip:" + handler.client_address[0], 40, 900)
    row = con.execute("SELECT * FROM email_login_challenges WHERE id=?", (identifier,)).fetchone()
    if not row or row["consumed_at"] is not None or row["expires_at"] <= app.now() or row["attempts"] >= MAX_ATTEMPTS:
        raise app.ApiError(400, "Код истёк или уже использован")
    # Conditional atomic update protects against competing guesses.
    attempts = con.execute(
        "UPDATE email_login_challenges SET attempts=attempts+1 WHERE id=? "
        "AND consumed_at IS NULL AND expires_at>? AND attempts<?",
        (identifier,app.now(),MAX_ATTEMPTS)
    )
    if attempts.rowcount != 1:
        raise app.ApiError(400, "Код истёк или уже использован")
    if not hmac.compare_digest(_digest(identifier,code), row["code_hash"]):
        raise app.ApiError(400, "Неверный код. Проверьте цифры")
    consumed = con.execute(
        "UPDATE email_login_challenges SET consumed_at=? WHERE id=? "
        "AND consumed_at IS NULL AND expires_at>? AND attempts<=?",
        (app.now(),identifier,app.now(),MAX_ATTEMPTS)
    )
    if consumed.rowcount != 1:
        raise app.ApiError(409, "Код уже использован")
    user = con.execute("SELECT * FROM users WHERE email=? AND deleted_at IS NULL",
                       (row["email"],)).fetchone()
    if user:
        if user["blocked"]:
            raise app.ApiError(403, "Аккаунт заблокирован")
        if user["email_verified_at"] is None:
            con.execute("UPDATE users SET email_verified_at=? WHERE id=?",
                        (app.now(),user["id"]))
        user_id=user["id"]
    else:
        if row["intent"] != "register" or row["legal_version"] != app.REGISTRATION_CONSENT_VERSION:
            raise app.ApiError(400, "Сначала зарегистрируйтесь")
        user_id = app.uid()
        # OTP-only identities get an unguessable unused legacy password hash.
        con.execute(
            "INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at)"
            " VALUES(?,?,?,?,?,?)",
            (user_id,row["email"],app.hash_password(secrets.token_urlsafe(40)),
             row["name"],app.now(),app.now())
        )
        con.execute(
            "INSERT INTO legal_acceptances(id,user_id,document_version,accepted_at,source) "
            "VALUES(?,?,?,?,?)",
            (app.uid(),user_id,row["legal_version"],app.now(),"registration")
        )
        app.event(con,user_id,"signup_completed")
        app.revenue.record(con,user_id,"signup_completed",key="signup:"+user_id)
    return handler.login_response(con,user_id)
