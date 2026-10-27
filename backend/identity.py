"""Russian OAuth providers, shared web/native accounts and one-use PKCE handoff."""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie
from backend.business import DomainError, identity, stamp, transaction

try:
    from backend.estimate_safety import REGISTRATION_CONSENT_VERSION
except ModuleNotFoundError:
    from estimate_safety import REGISTRATION_CONSENT_VERSION


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def challenge(value):
    return (
        base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest())
        .decode()
        .rstrip("=")
    )


def config(provider):
    if provider == "yandex":
        return os.getenv("YANDEX_CLIENT_ID"), os.getenv("YANDEX_CLIENT_SECRET")
    if provider == "google":
        auth_client = os.getenv("GOOGLE_AUTH_CLIENT_ID")
        auth_secret = os.getenv("GOOGLE_AUTH_CLIENT_SECRET")
        if auth_client or auth_secret:
            # Never combine an incomplete auth pair with the Drive client.
            return auth_client, auth_secret
        return os.getenv("GOOGLE_DRIVE_CLIENT_ID"), os.getenv("GOOGLE_DRIVE_CLIENT_SECRET")
    if provider in ("vk", "mail", "ok"):
        return os.getenv("VK_CLIENT_ID"), ""
    raise DomainError(404, "Способ входа не найден")


def providers():
    return [
        {"id": key, "name": name, "enabled": bool(config(key)[0]) and (key != "google" or bool(config(key)[1]))}
        for key, name in (("yandex", "Яндекс ID"), ("google", "Google"), ("vk", "VK ID"), ("mail", "Mail ID"), ("ok", "Одноклассники"))
    ]


def redirect(h, url, cookie=None):
    h.send_response(303)
    h.send_header("Location", url)
    h.send_header("Cache-Control", "no-store")
    h.send_header("Referrer-Policy", "no-referrer")
    if cookie:
        h.send_header("Set-Cookie", cookie)
    h.send_header("Content-Length", "0")
    h.end_headers()


def remote(url, data=None, headers=None):
    request = urllib.request.Request(
        url,
        urllib.parse.urlencode(data).encode() if data is not None else None,
        headers or {},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read(100000))


def profile(provider, code, state, verifier, callback, device):
    client, secret = config(provider)
    params = dict(
        grant_type="authorization_code",
        code=code,
        client_id=client,
        redirect_uri=callback,
        code_verifier=verifier,
    )
    if provider == "yandex":
        if secret:
            params["client_secret"] = secret
        token = remote("https://oauth.yandex.ru/token", params)["access_token"]
        user = remote(
            "https://login.yandex.ru/info?format=json",
            headers={"Authorization": "OAuth " + token},
        )
        if user.get("client_id") and str(user["client_id"]) != client:
            raise ValueError("wrong client")
        avatar_id = str(user.get("default_avatar_id") or "")
        if user.get("is_avatar_empty") or not re.fullmatch(r"[A-Za-z0-9_/-]{1,150}", avatar_id):
            avatar_id = ""
        return (
            str(user["id"]),
            user.get("real_name") or user.get("display_name") or "Пользователь",
            user.get("default_email", ""),
            avatar_id,
        )
    if provider == "google":
        if not secret:
            raise ValueError("Google login secret missing")
        params["client_secret"] = secret
        tokens = remote("https://oauth2.googleapis.com/token", params)
        access = tokens.get("access_token")
        if not isinstance(access, str) or not access:
            raise ValueError("Google did not issue access token")
        user = remote(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": "Bearer " + access},
        )
        subject = str(user.get("sub") or "")
        if not re.fullmatch(r"[0-9]{5,32}", subject):
            raise ValueError("Invalid Google account subject")
        email = user.get("email")
        if user.get("email_verified") is not True or not isinstance(email, str) or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("Google email not verified")
        name = user.get("name")
        return subject, name if isinstance(name, str) and name.strip() else "Пользователь", email
    if not device:
        raise ValueError('missing VK device binding')
    params.pop('code')
    params.update(device_id=device, state=state)
    token_result = remote('https://id.vk.com/oauth2/auth?'+urllib.parse.urlencode(params), {'code': code})
    if not hmac.compare_digest(str(token_result.get('state','')), state):
        raise ValueError('VK state mismatch')
    token = token_result['access_token']
    user = remote(
        'https://id.vk.com/oauth2/user_info?'+urllib.parse.urlencode({'client_id':client}),
        {'access_token':token},
    )["user"]
    return (
        str(user["user_id"]),
        (user.get("first_name", "") + " " + user.get("last_name", "")).strip()
        or "Пользователь",
        user.get("email", ""),
    )


def route(h, con, method, path, query, origin):
    if path == "/api/auth/providers" and method == "GET":
        return h.send_json(
            200, {
                "providers": providers(), "rustore_url": os.getenv("RUSTORE_URL", ""),
                "email_delivery_available": __import__("backend.email_otp",fromlist=["configured"]).configured(),
                "email_code_available": __import__("backend.email_otp",fromlist=["configured"]).configured(),
                "email_signup_available": __import__("backend.email_otp",fromlist=["configured"]).configured(),
            }
        )
    if path == "/api/auth/native/exchange" and method == "POST":
        h.throttle("native-exchange:" + h.client_address[0], 30, 300)
        data = h.body()
        verifier = str(data.get("verifier", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", verifier):
            raise DomainError(400, "Повторите вход из приложения")
        with transaction(con):
            row = con.execute(
                "SELECT * FROM oauth_tickets WHERE ticket_hash=? AND expires_at>?",
                (digest(str(data.get("ticket", ""))), stamp()),
            ).fetchone()
            if not row or not hmac.compare_digest(
                row["challenge"], challenge(verifier)
            ):
                raise DomainError(400, "Ссылка входа недействительна или устарела")
            con.execute(
                "DELETE FROM oauth_tickets WHERE ticket_hash=?", (row["ticket_hash"],)
            )
            user = con.execute(
                "SELECT * FROM users WHERE id=? AND deleted_at IS NULL AND blocked=0",
                (row["user_id"],),
            ).fetchone()
            if not user:
                raise DomainError(403, "Аккаунт недоступен")
        return h.login_response(con, row["user_id"])
    parts = path.strip("/").split("/")
    if len(parts) != 5 or parts[2] != "oauth" or method != "GET":
        raise DomainError(404, "Страница входа не найдена")
    provider, action = parts[3:]
    # Keep the state cookie, authorization redirect and token exchange on
    # the same verified host. PUBLIC_ORIGIN may point at a legacy Vercel alias.
    if provider in ("yandex", "google"):
        host = h.headers.get("Host", "").strip().lower()
        # Google login always uses one registered, canonical callback.
        if host == "www.smetra.online" and action == "start":
            safe_query = {key: value for key, value in query.items() if key != "path"}
            target = f"https://smetra.online/api/auth/oauth/{provider}/start"
            if safe_query:
                target += "?" + urllib.parse.urlencode(safe_query, doseq=True)
            return redirect(h, target)
        if provider == "yandex" and host in ("smetra.online", "smetra.vercel.app"):
            origin = "https://" + host
    client, _ = config(provider)
    if not client or (provider == "google" and not config(provider)[1]):
        return redirect(h, origin + "/app?auth_error=unavailable")
    callback = origin + "/api/auth/oauth/" + provider + "/callback"
    if action == "start":
        h.throttle("oauth:" + h.client_address[0], 20, 600)
        intent = query.get("intent", ["login"])[0]
        if intent not in ("login", "register"):
            return redirect(h, origin + "/app?auth_error=expired")
        legal_accepted = (
            intent == "register"
            and query.get("legal_acceptance", [""])[0] == "1"
            and query.get("legal_version", [""])[0] == REGISTRATION_CONSENT_VERSION
        )
        if intent == "register" and not legal_accepted:
            return redirect(h, origin + "/app?auth_error=registration_consent_required")
        app_challenge = query.get("app_challenge", [""])[0]
        if app_challenge and not re.fullmatch(r"[A-Za-z0-9_-]{43}", app_challenge):
            raise DomainError(400, "Неверный запрос приложения")
        linked = h.auth(con)["id"] if query.get("link") == ["1"] else None
        state, verifier, browser = (
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(48),
            secrets.token_urlsafe(32),
        )
        con.execute(
            "INSERT INTO oauth_states(state_hash,provider,verifier,browser_hash,app_challenge,link_user_id,expires_at,registration_intent,legal_acceptance,legal_version) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                digest(state),
                provider,
                verifier,
                digest(browser),
                app_challenge,
                linked,
                stamp() + 600,
                intent == "register",
                bool(legal_accepted),
                REGISTRATION_CONSENT_VERSION if legal_accepted else "",
            ),
        )
        params = dict(
            response_type="code",
            client_id=client,
            redirect_uri=callback,
            state=state,
            code_challenge=challenge(verifier),
            code_challenge_method="S256",
        )
        if provider == "yandex":
            url = "https://oauth.yandex.ru/authorize"
            params["scope"] = "login:info login:email login:avatar"
            if linked:
                # Re-ask for consent so an account linked before the avatar
                # scope existed can grant access to its profile photo.
                params["force_confirm"] = "yes"
        elif provider == "google":
            url = "https://accounts.google.com/o/oauth2/v2/auth"
            params["scope"] = "openid email profile"
        else:
            url = "https://id.vk.com/authorize"
            params.update(scope="vkid.personal_info email", code_challenge_method='s256', provider={"mail": "mail_ru", "ok": "ok_ru"}.get(provider, "vkid"))
        secure = "; Secure" if origin.startswith("https://") else ""
        return redirect(
            h,
            url + "?" + urllib.parse.urlencode(params),
            "smetra_oauth="
            + browser
            + "; HttpOnly; SameSite=Lax; Path=/api/auth/oauth; Max-Age=600"
            + secure,
        )
    if action != "callback":
        raise DomainError(404, "Страница входа не найдена")
    h.throttle("oauth-callback:" + h.client_address[0], 30, 300)
    state = query.get("state", [""])[0]
    cookies = SimpleCookie()
    cookies.load(h.headers.get("Cookie", ""))
    browser = cookies.get("smetra_oauth")
    with transaction(con):
        row = con.execute(
            "SELECT * FROM oauth_states WHERE state_hash=? AND provider=? AND expires_at>?",
            (digest(state), provider, stamp()),
        ).fetchone()
        if (
            not row
            or not browser
            or not hmac.compare_digest(row["browser_hash"], digest(browser.value))
        ):
            return redirect(h, origin + "/app?auth_error=expired")
        con.execute("DELETE FROM oauth_states WHERE state_hash=?", (row["state_hash"],))
    if query.get("error"):
        return redirect(h, origin + "/app?auth_error=cancelled")
    try:
        details = profile(
            provider,
            query.get("code", [""])[0],
            state,
            row["verifier"],
            callback,
            query.get("device_id", [""])[0],
        )
        # Backward compatible with three-field VK provider responses.
        subject, name, email = details[:3]
        avatar_id = details[3] if len(details) > 3 and provider == "yandex" else None
    except Exception:
        return redirect(h, origin + "/app?auth_error=provider")
    # All VK ID methods use the same VK application identity namespace.
    namespace = "vk" if provider in ("mail", "ok") else provider
    with transaction(con):
        account = con.execute(
            "SELECT u.* FROM external_identities i JOIN users u ON u.id=i.user_id WHERE i.provider=? AND i.subject=?",
            (namespace, subject),
        ).fetchone()
        if account and (account["blocked"] or account["deleted_at"]):
            return redirect(h, origin + "/app?auth_error=blocked")
        if row["link_user_id"]:
            current = h.auth(con)
            if (
                current["id"] != row["link_user_id"]
                or account
                and account["id"] != current["id"]
            ):
                return redirect(h, origin + "/app?auth_error=conflict")
            user_id = current["id"]
        elif account:
            user_id = account["id"]
        else:
            if (
                row["registration_intent"] != 1
                or row["legal_acceptance"] != 1
                or row["legal_version"] != REGISTRATION_CONSENT_VERSION
            ):
                return redirect(h, origin + "/app?auth_error=registration_consent_required")
            # Never merge accounts just because provider emails match.
            if (
                email
                and con.execute(
                    "SELECT id FROM users WHERE email=?", (email.lower(),)
                ).fetchone()
            ):
                return redirect(h, origin + "/app?auth_error=link_required")
            user_id = identity()
            email = (
                email.lower()
                if "@" in email
                else namespace + "-" + digest(subject)[:24] + "@identity.smetra.invalid"
            )
            # Random inaccessible local credential; password reset still requires verified mailbox access.
            from backend.app import hash_password

            con.execute(
                "INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES(?,?,?,?,?,?)",
                (
                    user_id,
                    email,
                    hash_password(secrets.token_urlsafe(64)),
                    name[:80],
                    stamp(),
                    stamp() if not email.endswith('@identity.smetra.invalid') else None,
                ),
            )
        if avatar_id is not None:
            con.execute("UPDATE users SET avatar_id=? WHERE id=?", (avatar_id, user_id))
        if (
            row["legal_acceptance"] == 1
            and row["legal_version"] == REGISTRATION_CONSENT_VERSION
            and not row["link_user_id"]
        ):
            con.execute(
                "INSERT INTO legal_acceptances(id,user_id,document_version,accepted_at,source) "
                "VALUES(?,?,?,?,?) ON CONFLICT(user_id,document_version) DO NOTHING",
                (identity(), user_id, REGISTRATION_CONSENT_VERSION, stamp(), "registration"),
            )
        if not account and not row['link_user_id']:
            from backend.revenue import record
            record(con,user_id,'signup_completed',key='signup:'+user_id)
        if not account:
            con.execute(
                "INSERT INTO external_identities(provider,subject,user_id,created_at) VALUES(?,?,?,?)",
                (namespace, subject, user_id, stamp()),
            )
        if row["app_challenge"]:
            ticket = secrets.token_urlsafe(32)
            con.execute(
                "INSERT INTO oauth_tickets(ticket_hash,user_id,challenge,expires_at) VALUES(?,?,?,?)",
                (digest(ticket), user_id, row["app_challenge"], stamp() + 120),
            )
            return redirect(h, "smetra://auth?ticket=" + ticket)
        token = secrets.token_urlsafe(32)
        con.execute(
            "INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)",
            (identity(), user_id, digest(token), stamp() + 30 * 86400),
        )
    return redirect(h, origin + "/app" + ("#settings" if row["link_user_id"] else ""), h.cookie(token, 30 * 86400))
