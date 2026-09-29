import base64
import hashlib
import hmac
import http.server
import json
import os
import re
import secrets
import smtplib
import sqlite3
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path
from email.message import EmailMessage

try:
    from backend import business
except ModuleNotFoundError:
    import business

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "data" / "smetra.sqlite3")))
WEB = ROOT / "apps" / "web"
PORT = int(os.getenv("PORT", "8080"))
ORIGIN = os.getenv("PUBLIC_ORIGIN", "https://" + os.environ['VERCEL_URL'] if os.getenv('VERCEL_URL') else f"http://localhost:{PORT}").rstrip("/")
COOKIE_SECURE = ORIGIN.startswith("https://")
_LOCK = threading.RLock()
RATE = {}
PLANS = {"pro_month": (49000, 31), "pro_year": (490000, 366)}


def yookassa_mode(user=None):
    """Keep checkout closed until a store and its environment are explicit."""
    mode = os.getenv("YOOKASSA_MODE", "off").lower()
    if mode not in ("test", "live") or not all(
        os.getenv(key) for key in ("YOOKASSA_SHOP_ID", "YOOKASSA_SECRET_KEY")
    ) or os.getenv("YOOKASSA_MERCHANT_TYPE") != "self_employed":
        return "off"
    if mode == "test" and user is not None:
        tester = os.getenv("YOOKASSA_TEST_EMAIL", "").strip().lower()
        if not tester or user["email"].lower() != tester:
            return "off"
    return mode


@contextmanager
def db():
    if os.getenv("DATABASE_URL"):
        try:
            from backend.postgres import Connection
        except ModuleNotFoundError:
            from postgres import Connection
        con = Connection()
        try:
            with con:
                yield con
        finally:
            con.close()
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=10000")
        with con:
            yield con
    finally:
        con.close()


def migrate():
    if os.getenv("DATABASE_URL"):
        # Cloud schema changes are explicit, versioned Supabase migrations.
        with db() as con:
            version = con.execute(
                "SELECT version FROM schema_migrations WHERE version=6"
            ).fetchone()
            if not version:
                raise RuntimeError(
                    "Apply the Smetra PostgreSQL migration before starting"
                )
        return
    with db() as con:
        con.executescript((ROOT / "backend" / "schema.sql").read_text(encoding="utf-8"))
        # Older archives created these tables without the two optional columns.
        for table, column, definition in (
            ("users", "deleted_at", "INTEGER"),
            ("users", "email_verified_at", "INTEGER"),
            ("payments", "activated_at", "INTEGER"),
        ):
            columns = {
                row["name"] for row in con.execute(f"PRAGMA table_info({table})")
            }
            if column not in columns:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        con.execute("DELETE FROM email_tokens WHERE expires_at<?", (now() - 86400,))
        business.migrate(con)


def now():
    return int(time.time())


def uid():
    return str(uuid.uuid4())


def mail(to, subject, message):
    required = ("SMTP_HOST", "SMTP_FROM", "SMTP_USER", "SMTP_PASSWORD")
    if any(not os.getenv(name) for name in required):
        raise ApiError(503, "Почта сервиса временно недоступна")
    email = EmailMessage()
    email["From"], email["To"], email["Subject"] = os.environ["SMTP_FROM"], to, subject
    email.set_content(message)
    with smtplib.SMTP(
        os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=12
    ) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(email)


def create_email_token(con, user_id, purpose, lifetime):
    token = secrets.token_urlsafe(32)
    con.execute(
        "INSERT INTO email_tokens(id,user_id,token_hash,purpose,expires_at) VALUES(?,?,?,?,?)",
        (
            uid(),
            user_id,
            hashlib.sha256(token.encode()).hexdigest(),
            purpose,
            now() + lifetime,
        ),
    )
    return token


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + digest).decode()


def verify_password(password, encoded):
    try:
        value = base64.b64decode(encoded)
        return hmac.compare_digest(
            base64.b64decode(hash_password(password, value[:16]))[16:], value[16:]
        )
    except (ValueError, TypeError):
        return False


def audit(con, actor, action, target, detail=""):
    con.execute(
        "INSERT INTO audit(id,actor_id,action,target,detail,created_at) VALUES(?,?,?,?,?,?)",
        (uid(), actor, action, target, detail[:500], now()),
    )


def event(con, user_id, name):
    con.execute(
        "INSERT INTO events(id,user_id,name,created_at) VALUES(?,?,?,?)",
        (uid(), user_id, name, now()),
    )


def user_view(user, con):
    expiry = user["entitlement_until"] or 0
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "plan": user["plan"] if expiry > now() else "free",
        "entitlement_until": expiry,
        "email_verified": user["email_verified_at"] is not None,
        "quote_count": con.execute(
            "SELECT count(*) FROM quotes WHERE user_id=?", (user["id"],)
        ).fetchone()[0],
    }


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "Smetra/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, fmt, *args):
        path = urllib.parse.urlsplit(self.path).path
        path = re.sub(r"/p/[^/]+", "/p/[redacted]", path)
        print(
            json.dumps(
                {
                    "time": now(),
                    "request_id": getattr(self, "request_id", ""),
                    "method": self.command,
                    "path": path,
                    "status": str(args[1]) if len(args) > 1 else "",
                    "duration_ms": round(
                        (time.monotonic() - getattr(self, "started", time.monotonic()))
                        * 1000
                    ),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    def send_json(self, status, payload, cookie=None):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if status == 429:
            self.send_header("Retry-After", "60")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Request-ID", getattr(self, "request_id", ""))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; form-action 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'",
        )
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        size = getattr(self, "_body_length", None)
        if size is None:
            size = self.validate_body_length(urllib.parse.urlsplit(self.path).path)
        if size and self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise ApiError(415, "Отправьте данные в формате JSON")
        try:

            def reject_constant(value):
                raise ValueError("Non-finite JSON number")

            def unique_keys(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("Duplicate JSON key")
                    result[key] = value
                return result

            data = json.loads(
                self.rfile.read(size) or b"{}", parse_constant=reject_constant,
                object_pairs_hook=unique_keys,
            )
            if not isinstance(data, dict):
                raise ValueError("Expected object")
            return data
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "Некорректный JSON")

    def validate_body_length(self, path):
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) > 1 or self.headers.get("Transfer-Encoding"):
            raise ApiError(400, "Некорректная длина запроса")
        try:
            size = int(lengths[0]) if lengths else 0
        except ValueError:
            raise ApiError(400, "Некорректная длина запроса") from None
        maximum = 7_000_000 if path == "/api/files" else 3_000_000 if path == "/api/ai/draft" else 1_500_000 if path == "/api/public/intake" else 65536
        if size < 0 or size > maximum:
            raise ApiError(413, "Слишком большой запрос")
        if self.headers.get("Content-Encoding", "identity").lower() != "identity":
            raise ApiError(415, "Сжатые запросы не поддерживаются")
        return size

    def route(self):
        parsed = urllib.parse.urlsplit(self.path)
        return parsed.path, urllib.parse.parse_qs(parsed.query)

    def auth(self, con, admin=False):
        raw = self.headers.get("Authorization", "")
        token = raw[7:] if raw.startswith("Bearer ") else ""
        if not token:
            cookie = self.headers.get("Cookie", "")
            for part in cookie.split(";"):
                if part.strip().startswith("session="):
                    token = part.strip()[8:]
        if not token:
            raise ApiError(401, "Войдите в аккаунт")
        row = con.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.deleted_at IS NULL",
            (hashlib.sha256(token.encode()).hexdigest(), now()),
        ).fetchone()
        if not row:
            raise ApiError(401, "Сессия истекла")
        if row["blocked"]:
            raise ApiError(403, "Аккаунт заблокирован")
        if admin and row["role"] != "admin":
            raise ApiError(403, "Недостаточно прав")
        return row

    def throttle(self, key, limit=15, window=60):
        if os.getenv("DATABASE_URL"):
            try:
                from backend.postgres import throttle
            except ModuleNotFoundError:
                from postgres import throttle
            if not throttle(key, limit, window, now()):
                raise ApiError(429, "Слишком много запросов. Попробуйте позже")
            return
        with _LOCK:
            moment = now()
            if len(RATE) > 10000:
                for stale in [k for k, v in RATE.items() if moment - v[1] > 86400]:
                    RATE.pop(stale, None)
                if key not in RATE and len(RATE) > 10000:
                    raise ApiError(429, "Сервис занят. Попробуйте позже")
            count, start = RATE.get(key, (0, moment))
            if moment - start >= window:
                count, start = 0, moment
            if count >= limit:
                raise ApiError(429, "Слишком много запросов. Попробуйте позже")
            RATE[key] = (count + 1, start)

    def require_origin(self):
        origin = self.headers.get("Origin")
        if origin and origin != ORIGIN:
            raise ApiError(403, "Неверный источник запроса")
        fetch_site = self.headers.get("Sec-Fetch-Site")
        if fetch_site in ("cross-site", "same-site"):
            raise ApiError(403, "Запрос отклонён")
        has_session_cookie = any(
            part.strip().startswith("session=")
            for part in self.headers.get("Cookie", "").split(";")
        )
        if (
            has_session_cookie
            and not self.headers.get("Authorization", "").startswith("Bearer ")
            and not origin
            and fetch_site != "same-origin"
        ):
            raise ApiError(403, "Укажите источник запроса")

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PATCH(self):
        self.dispatch("PATCH")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def dispatch(self, method):
        self.request_id = uuid.uuid4().hex
        self.started = time.monotonic()
        try:
            if len(self.path) > 4096:
                raise ApiError(414, "Слишком длинный адрес запроса")
            path, query = self.route()
            if path.startswith("/api/"):
                self._body_length = self.validate_body_length(path)
                root = path.split("/", 3)[2]
                if root not in business.ROUTES | {"auth", "webhooks", "billing", "admin", "me", "support", "mobile"}:
                    raise ApiError(404, "Не найдено")
                if root == "webhooks" and path != "/api/webhooks/yookassa":
                    raise ApiError(404, "Не найдено")
                if root == "mobile" and path != "/api/mobile/presentation":
                    raise ApiError(404, "Не найдено")
            if method != "GET" and path != "/api/webhooks/yookassa":
                self.require_origin()
            if method == "GET" and path == "/api/auth/providers":
                from backend.identity import route as identity_route

                identity_route(self, None, method, path, query, ORIGIN)
            elif method == "GET" and path == "/api/mobile/presentation":
                presentation = json.loads((ROOT / "backend" / "mobile_presentation.json").read_text(encoding="utf-8"))
                self.send_json(200, presentation)
            elif path.startswith("/api/"):
                with db() as con:
                    self.api(method, path, query, con)
            elif method == "GET":
                self.static(path)
            else:
                raise ApiError(404, "Не найдено")
        except (ApiError, business.DomainError) as err:
            self.send_json(err.status, {"error": err.message})
        except sqlite3.IntegrityError:
            self.send_json(
                409,
                {"error": "Запись уже существует или используется в другом документе"},
            )
        except Exception as err:
            print(
                json.dumps(
                    {
                        "time": now(),
                        "error": type(err).__name__,
                        "request_id": self.request_id,
                    }
                ),
                flush=True,
            )
            self.send_json(
                500,
                {
                    "error": "Внутренняя ошибка. Попробуйте позже",
                    "request_id": self.request_id,
                },
            )

    def static(self, path):
        if path == "/health":
            with db() as con:
                con.execute("SELECT 1")
            return self.send_json(200, {"ok": True})
        public = {
            "/": ("index.html", "text/html"),
            "/app": ("app.html", "text/html"),
            "/admin": ("admin.html", "text/html"),
            "/privacy": ("privacy.html", "text/html"),
            "/terms": ("terms.html", "text/html"),
            "/contacts": ("contacts.html", "text/html"),
            "/style.css": ("style.css", "text/css"),
            "/app.js": ("app.js", "text/javascript"),
            "/experience.js": ("experience.js", "text/javascript"),
            "/assets/obsidian-folio.png": ("assets/obsidian-folio.png", "image/png"),
            "/assets/black-titanium.png": ("assets/black-titanium.png", "image/png"),
            "/favicon.ico": ("favicon.png", "image/png"),
            "/robots.txt": ("robots.txt", "text/plain"),
            "/sitemap.xml": ("sitemap.xml", "application/xml"),
        }
        for weight in (400, 500, 600, 700, 800):
            font = f"assets/fonts/manrope-{weight}.ttf"
            public["/" + font] = (font, "font/ttf")
        for name, mime in (
            ("black.css", "text/css"),
            ("cabinet.css", "text/css"),
            ("assistant.css", "text/css"),
            ("black.js", "text/javascript"),
            ("assistant-chat.js", "text/javascript"),
            ("landing.js", "text/javascript"),
            ("assets/black/unfold.png", "image/png"),
            ("assets/black/flight.png", "image/png"),
        ):
            public["/" + name] = (name, mime)
        public["/workspace.js"] = ("workspace.js", "text/javascript")
        for name in (
            "reference-hero",
            "reference-sphere",
            "reference-cube",
            "reference-pyramid",
            "reference-ribbon",
        ):
            asset = f"assets/{name}.png"
            public["/" + asset] = (asset, "image/png")
        for name in (
            "arrow-up-right",
            "arrow-right",
            "play",
            "x",
            "check",
            "file-text",
            "link-simple",
            "pause",
            "sun",
            "moon",
        ):
            icon = f"assets/icons/{name}.svg"
            public["/" + icon] = (icon, "image/svg+xml")
        if path not in public:
            raise ApiError(404, "Страница не найдена")
        file, typ = public[path]
        data = (WEB / file).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", typ + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("X-Request-ID", getattr(self, "request_id", ""))
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; form-action 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(data)

    def api(self, method, path, query, con):
        if (
            path == "/api/auth/providers"
            or path.startswith("/api/auth/oauth/")
            or path == "/api/auth/native/exchange"
        ):
            from backend.identity import route

            return route(self, con, method, path, query, ORIGIN)
        if path.removeprefix("/api/").split("/")[0] in business.ROUTES:
            status, payload = business.Service(self, con, ORIGIN).handle(
                method, path, query
            )
            if path == "/api/assistant/stream":
                return payload.write(self)
            if hasattr(payload, "mime"):
                self.send_response(status)
                self.send_header("Content-Type", payload.mime)
                self.send_header("Content-Length", str(len(payload.data)))
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="' + payload.filename + '"',
                )
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(payload.data)
                return
            return self.send_json(status, payload)
        if path == "/api/auth/register" and method == "POST":
            self.throttle("register:" + self.client_address[0], 5, 3600)
            data = self.body()
            email = str(data.get("email", "")).strip().lower()
            password = str(data.get("password", ""))
            name = str(data.get("name", "")).strip()
            if (
                "@" not in email
                or len(email) > 254
                or len(password) < 12
                or len(password) > 128
                or not 1 <= len(name) <= 80
            ):
                raise ApiError(400, "Укажите имя, почту и пароль от 12 символов")
            local_only = ORIGIN.startswith("http://localhost:")
            if (
                not local_only
                and not os.getenv("SMTP_HOST")
                and os.getenv("ALLOW_UNVERIFIED_SIGNUP") != "1"
            ):
                raise ApiError(
                    503, "Регистрация временно недоступна: почта не настроена"
                )
            try:
                user_id = uid()
                con.execute(
                    "INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES(?,?,?,?,?,?)",
                    (
                        user_id,
                        email,
                        hash_password(password),
                        name,
                        now(),
                        now() if local_only and not os.getenv("SMTP_HOST") else None,
                    ),
                )
                event(con, user_id, "signup_completed")
            except sqlite3.IntegrityError:
                raise ApiError(409, "Такая почта уже зарегистрирована")
            if os.getenv("SMTP_HOST"):
                token = create_email_token(con, user_id, "verify", 86400)
                try:
                    mail(
                        email,
                        "Подтвердите почту в Сметре",
                        ORIGIN + "/app?verify=" + token,
                    )
                except Exception:
                    con.execute("DELETE FROM users WHERE id=?", (user_id,))
                    raise ApiError(503, "Не удалось отправить письмо. Попробуйте позже")
            return self.login_response(con, user_id)
        if path == "/api/auth/login" and method == "POST":
            self.throttle("login:" + self.client_address[0], 10, 300)
            data = self.body()
            user = con.execute(
                "SELECT * FROM users WHERE email=?",
                (str(data.get("email", "")).lower().strip(),),
            ).fetchone()
            if not user or not verify_password(
                str(data.get("password", "")), user["password_hash"]
            ):
                raise ApiError(401, "Неверная почта или пароль")
            if user["blocked"]:
                raise ApiError(403, "Аккаунт заблокирован")
            return self.login_response(con, user["id"])
        if path == "/api/auth/verify" and method == "POST":
            data = self.body()
            token = str(data.get("token", ""))
            row = con.execute(
                "SELECT t.* FROM email_tokens t JOIN users u ON u.id=t.user_id WHERE t.token_hash=? AND t.purpose='verify' AND t.consumed_at IS NULL AND t.expires_at>? AND u.deleted_at IS NULL",
                (hashlib.sha256(token.encode()).hexdigest(), now()),
            ).fetchone()
            if not row:
                raise ApiError(400, "Ссылка устарела или уже использована")
            con.execute("BEGIN IMMEDIATE")
            try:
                changed = con.execute(
                    "UPDATE email_tokens SET consumed_at=? WHERE id=? AND consumed_at IS NULL",
                    (now(), row["id"]),
                )
                if changed.rowcount != 1:
                    raise ApiError(409, "Ссылка уже использована")
                con.execute(
                    "UPDATE users SET email_verified_at=? WHERE id=?",
                    (now(), row["user_id"]),
                )
                event(con, row["user_id"], "email_verified")
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            return self.send_json(200, {"ok": True})
        if path == "/api/auth/reset/request" and method == "POST":
            self.throttle("reset:" + self.client_address[0], 5, 3600)
            email = str(self.body().get("email", "")).strip().lower()
            account = con.execute(
                "SELECT id FROM users WHERE email=? AND deleted_at IS NULL", (email,)
            ).fetchone()
            if account and os.getenv("SMTP_HOST"):
                token = create_email_token(con, account["id"], "reset", 1800)
                try:
                    mail(email, "Сброс пароля Сметры", ORIGIN + "/app?reset=" + token)
                except Exception:
                    con.execute(
                        "DELETE FROM email_tokens WHERE token_hash=?",
                        (hashlib.sha256(token.encode()).hexdigest(),),
                    )
                    raise ApiError(503, "Не удалось отправить письмо")
            return self.send_json(200, {"ok": True})
        if path == "/api/auth/reset/confirm" and method == "POST":
            self.throttle("reset-confirm:" + self.client_address[0], 10, 3600)
            data = self.body()
            password = str(data.get("password", ""))
            token = str(data.get("token", ""))
            if not 12 <= len(password) <= 128:
                raise ApiError(400, "Пароль должен содержать от 12 до 128 символов")
            row = con.execute(
                "SELECT t.* FROM email_tokens t JOIN users u ON u.id=t.user_id WHERE t.token_hash=? AND t.purpose='reset' AND t.consumed_at IS NULL AND t.expires_at>? AND u.deleted_at IS NULL",
                (hashlib.sha256(token.encode()).hexdigest(), now()),
            ).fetchone()
            if not row:
                raise ApiError(400, "Ссылка устарела или уже использована")
            con.execute("BEGIN IMMEDIATE")
            try:
                changed = con.execute(
                    "UPDATE email_tokens SET consumed_at=? WHERE id=? AND consumed_at IS NULL",
                    (now(), row["id"]),
                )
                if changed.rowcount != 1:
                    raise ApiError(409, "Ссылка уже использована")
                con.execute(
                    "UPDATE users SET password_hash=?,email_verified_at=coalesce(email_verified_at,?) WHERE id=?",
                    (hash_password(password), now(), row["user_id"]),
                )
                con.execute("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
                audit(con, row["user_id"], "auth.password_reset", row["user_id"])
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            return self.send_json(200, {"ok": True})
        if path == "/api/webhooks/yookassa" and method == "POST":
            if yookassa_mode() == "off":
                raise ApiError(503, "Прием платежей пока не настроен")
            self.throttle("webhook:" + self.client_address[0], 120, 60)
            data = self.body()
            obj = data.get("object")
            if (
                not isinstance(obj, dict)
                or not isinstance(obj.get("id"), str)
                or not 1 <= len(obj["id"]) <= 100
            ):
                raise ApiError(400, "Некорректное уведомление")
            if data.get("event") == "refund.succeeded":
                payment_id = obj.get("payment_id")
                if not isinstance(payment_id, str) or not con.execute(
                    "SELECT 1 FROM payments WHERE provider_id=?", (payment_id,)
                ).fetchone():
                    raise ApiError(404, "Платеж не найден")
                if con.execute(
                    "SELECT 1 FROM refunds WHERE provider_id=?", (obj["id"],)
                ).fetchone():
                    return self.send_json(200, {"ok": True})
                verified = self.provider_call(
                    "/refunds/" + urllib.parse.quote(obj["id"], safe="")
                )
                self.apply_refund(con, verified)
            elif data.get("event") in ("payment.succeeded", "payment.canceled"):
                payment = con.execute(
                    "SELECT * FROM payments WHERE provider_id=?", (obj["id"],)
                ).fetchone()
                if not payment:
                    raise ApiError(404, "Платеж не найден")
                if payment["status"] == data["event"].split(".", 1)[1]:
                    return self.send_json(200, {"ok": True})
                self.apply_payment(con, payment, self.provider_payment(obj["id"]))
            else:
                raise ApiError(400, "Неизвестное событие")
            return self.send_json(200, {"ok": True})
        user = self.auth(con, path.startswith("/api/admin/"))
        if path == "/api/me" and method == "GET":
            return self.send_json(200, {"user": user_view(user, con)})
        if path == "/api/auth/verify/resend" and method == "POST":
            if user["email_verified_at"] is not None:
                return self.send_json(200, {"ok": True})
            self.throttle("verify:" + user["id"], 3, 3600)
            token = create_email_token(con, user["id"], "verify", 86400)
            try:
                mail(
                    user["email"],
                    "Подтвердите почту в Сметре",
                    ORIGIN + "/app?verify=" + token,
                )
            except Exception:
                con.execute(
                    "DELETE FROM email_tokens WHERE token_hash=?",
                    (hashlib.sha256(token.encode()).hexdigest(),),
                )
                raise ApiError(503, "Не удалось отправить письмо")
            return self.send_json(200, {"ok": True})
        if path == "/api/auth/logout" and method == "POST":
            token = (
                self.headers.get("Authorization", "")[7:]
                if self.headers.get("Authorization", "").startswith("Bearer ")
                else ""
            )
            if not token:
                for part in self.headers.get("Cookie", "").split(";"):
                    if part.strip().startswith("session="):
                        token = part.strip()[8:]
            con.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            )
            return self.send_json(200, {"ok": True}, self.cookie("", 0))
        if path == "/api/me" and method == "DELETE":
            # Keep pseudonymous financial records for accounting reconciliation.
            uploads = [
                r[0]
                for r in con.execute(
                    "SELECT f.storage_name FROM files f JOIN workspaces w ON w.id=f.workspace_id WHERE w.owner_id=?",
                    (user["id"],),
                )
            ]
            con.execute("BEGIN IMMEDIATE")
            try:
                con.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
                con.execute("DELETE FROM quotes WHERE user_id=?", (user["id"],))
                con.execute("DELETE FROM workspaces WHERE owner_id=?", (user["id"],))
                con.execute(
                    "DELETE FROM workspace_members WHERE user_id=?", (user["id"],)
                )
                con.execute("DELETE FROM support WHERE user_id=?", (user["id"],))
                con.execute("DELETE FROM email_tokens WHERE user_id=?", (user["id"],))
                con.execute(
                    "UPDATE events SET user_id=NULL WHERE user_id=?", (user["id"],)
                )
                con.execute(
                    "UPDATE users SET email=?,name='Удалённый аккаунт',password_hash=?,blocked=1,role='user',deleted_at=? WHERE id=?",
                    (
                        "deleted-" + user["id"] + "@invalid.local",
                        hash_password(secrets.token_urlsafe(32)),
                        now(),
                        user["id"],
                    ),
                )
                audit(con, None, "account.deleted", user["id"])
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            try:
                from backend.attachments import directory
            except ModuleNotFoundError:
                from attachments import directory
            root = directory()
            for name in uploads:
                file = (root / name).resolve()
                if file.parent == root:
                    file.unlink(missing_ok=True)
            return self.send_json(200, {"ok": True}, self.cookie("", 0))
        if path == "/api/support" and method == "POST":
            self.throttle("support:" + user["id"], 5, 3600)
            message = str(self.body().get("message", "")).strip()
            if not 5 <= len(message) <= 2000:
                raise ApiError(400, "Опишите вопрос (5–2000 символов)")
            con.execute(
                "INSERT INTO support(id,user_id,message,status,created_at) VALUES(?,?,?,?,?)",
                (uid(), user["id"], message, "open", now()),
            )
            return self.send_json(201, {"ok": True})
        if path == "/api/billing" and method == "GET":
            payments = con.execute(
                """SELECT p.id,p.plan,p.amount_kopecks,p.created_at,
                CASE WHEN EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded')
                THEN 'refunded' ELSE p.status END AS status
                FROM payments p WHERE p.user_id=? ORDER BY p.created_at DESC LIMIT 30""",
                (user["id"],),
            ).fetchall()
            return self.send_json(
                200,
                {
                    "payments": [dict(r) for r in payments],
                    "plans": {k: v[0] for k, v in PLANS.items()},
                    "checkout_mode": yookassa_mode(user),
                    "email_verified": user["email_verified_at"] is not None,
                },
            )
        if path == "/api/billing/checkout" and method == "POST":
            if user["email_verified_at"] is None:
                raise ApiError(403, "Подтвердите почту перед оплатой")
            data = self.body()
            plan = data.get("plan")
            key = self.headers.get("Idempotency-Key", "")
            if plan not in PLANS or not 16 <= len(key) <= 100:
                raise ApiError(400, "Неверный тариф или ключ запроса")
            mode = yookassa_mode(user)
            if mode == "off":
                raise ApiError(503, "Оплата пока недоступна")
            previous = con.execute(
                "SELECT * FROM payments WHERE user_id=? AND idempotency_key=?",
                (user["id"], key),
            ).fetchone()
            if previous:
                if previous["plan"] != plan:
                    raise ApiError(409, "Ключ уже использован для другого тарифа")
                return self.send_json(
                    200,
                    {"url": previous["confirmation_url"], "status": previous["status"]},
                )
            amount = PLANS[plan][0]
            request = {
                "amount": {"value": f"{amount / 100:.2f}", "currency": "RUB"},
                "capture": True,
                "confirmation": {
                    "type": "redirect",
                    "return_url": ORIGIN + "/app?payment=return",
                },
                "description": "Доступ Сметра Про на " + ("31 день" if plan == "pro_month" else "366 дней"),
                "metadata": {"user_id": user["id"], "plan": plan},
            }
            result = self.provider_call("/payments", "POST", request, key)
            self.verify_yookassa_shop(result)
            if not result.get("id") or not result.get("confirmation", {}).get(
                "confirmation_url", ""
            ).startswith("https://"):
                raise ApiError(502, "Платежный сервис вернул неполный ответ")
            con.execute(
                "INSERT INTO payments(id,user_id,provider_id,plan,amount_kopecks,status,idempotency_key,confirmation_url,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    uid(),
                    user["id"],
                    result["id"],
                    plan,
                    amount,
                    "pending",
                    key,
                    result["confirmation"]["confirmation_url"],
                    now(),
                ),
            )
            event(con, user["id"], "checkout_started")
            return self.send_json(
                201,
                {
                    "url": result["confirmation"]["confirmation_url"],
                    "status": "pending",
                },
            )
        if path == "/api/billing/sync" and method == "POST":
            self.throttle("sync:" + user["id"], 5, 60)
            rows = con.execute(
                "SELECT * FROM payments WHERE user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 3",
                (user["id"],),
            ).fetchall()
            if rows and yookassa_mode() == "off":
                raise ApiError(503, "Сверка с платёжным сервисом временно недоступна")
            for row in rows:
                self.apply_payment(con, row, self.provider_payment(row["provider_id"]))
            current = con.execute(
                "SELECT * FROM users WHERE id=?", (user["id"],)
            ).fetchone()
            return self.send_json(200, {"user": user_view(current, con)})
        if path == "/api/admin/overview" and method == "GET":
            stats = {
                key: con.execute(sql).fetchone()[0]
                for key, sql in {
                    "users": "SELECT count(*) FROM users WHERE deleted_at IS NULL",
                    "quotes": "SELECT count(*) FROM quotes",
                    "subscriptions": "SELECT count(*) FROM users WHERE entitlement_until > unixepoch() AND deleted_at IS NULL",
                    "revenue_kopecks": "SELECT coalesce(sum(p.amount_kopecks),0) FROM payments p WHERE p.status='succeeded' AND NOT EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded')",
                }.items()
            }
            users = [
                dict(r)
                for r in con.execute(
                    "SELECT id,email,name,role,blocked,plan,entitlement_until,created_at FROM users WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 100"
                )
            ]
            tickets = [
                dict(r)
                for r in con.execute(
                    "SELECT id,user_id,message,status,created_at FROM support ORDER BY created_at DESC LIMIT 100"
                )
            ]
            logs = [
                dict(r)
                for r in con.execute(
                    "SELECT actor_id,action,target,created_at FROM audit ORDER BY created_at DESC LIMIT 100"
                )
            ]
            payment_rows = [
                dict(r)
                for r in con.execute(
                    """SELECT p.id,p.plan,p.amount_kopecks,p.created_at,u.email,
                    CASE WHEN EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded')
                    THEN 'refunded' ELSE p.status END AS status
                    FROM payments p JOIN users u ON u.id=p.user_id
                    ORDER BY p.created_at DESC LIMIT 50"""
                )
            ]
            return self.send_json(
                200, {"stats": stats, "users": users, "tickets": tickets, "audit": logs, "payments": payment_rows}
            )
        if path.startswith("/api/admin/users/") and method == "PATCH":
            target = path.removeprefix("/api/admin/users/")
            data = self.body()
            action = data.get("action")
            if target == user["id"] and action == "block":
                raise ApiError(409, "Нельзя заблокировать себя")
            if not con.execute("SELECT 1 FROM users WHERE id=?", (target,)).fetchone():
                raise ApiError(404, "Пользователь не найден")
            if action in ("block", "unblock"):
                con.execute(
                    "UPDATE users SET blocked=? WHERE id=?",
                    (int(action == "block"), target),
                )
                if action == "block":
                    con.execute("DELETE FROM sessions WHERE user_id=?", (target,))
            elif action == "grant":
                con.execute(
                    "UPDATE users SET plan='pro',entitlement_until=max(coalesce(entitlement_until,0),?)+? WHERE id=?",
                    (now(), 31 * 86400, target),
                )
            elif action == "revoke":
                con.execute(
                    "UPDATE users SET plan='free',entitlement_until=0 WHERE id=?",
                    (target,),
                )
            else:
                raise ApiError(400, "Неизвестное действие")
            audit(con, user["id"], "admin." + action, target)
            return self.send_json(200, {"ok": True})
        raise ApiError(404, "Маршрут не найден")

    def quote_view(self, r):
        return {
            k: r[k]
            for k in (
                "id",
                "title",
                "client",
                "description",
                "amount_kopecks",
                "status",
                "created_at",
                "updated_at",
            )
        } | {"public_url": ORIGIN + "/?quote=" + r["public_token"]}

    def cookie(self, token, age):
        return (
            "session="
            + token
            + "; Path=/; HttpOnly; SameSite=Lax; Max-Age="
            + str(age)
            + ("; Secure" if COOKIE_SECURE else "")
        )

    def login_response(self, con, user_id):
        token = secrets.token_urlsafe(32)
        con.execute(
            "INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)",
            (
                uid(),
                user_id,
                hashlib.sha256(token.encode()).hexdigest(),
                now() + 30 * 86400,
            ),
        )
        row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        payload = {"user": user_view(row, con)}
        # Browsers use the HttpOnly cookie; only native/API clients need a
        # bearer token in JSON. Browser JavaScript cannot override Origin.
        if self.headers.get("Origin") != ORIGIN and self.headers.get("Sec-Fetch-Site") != "same-origin":
            payload["token"] = token
        return self.send_json(200, payload, self.cookie(token, 30 * 86400))

    def provider_call(self, path, method="GET", payload=None, key=None):
        credentials = base64.b64encode(
            (
                os.environ["YOOKASSA_SHOP_ID"] + ":" + os.environ["YOOKASSA_SECRET_KEY"]
            ).encode()
        ).decode()
        headers = {
            "Authorization": "Basic " + credentials,
            "Content-Type": "application/json",
        }
        if key:
            headers["Idempotence-Key"] = key
        request = urllib.request.Request(
            "https://api.yookassa.ru/v3" + path,
            data=json.dumps(payload).encode() if payload else None,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError) as err:
            print(json.dumps({"payment_api_error": str(err)}), flush=True)
            raise ApiError(502, "Платёжный сервис временно недоступен")

    def provider_payment(self, payment_id):
        return self.provider_call(
            "/payments/" + urllib.parse.quote(payment_id, safe="")
        )

    def verify_yookassa_shop(self, payment):
        mode = yookassa_mode()
        if (
            mode == "off"
            or not isinstance(payment, dict)
            or payment.get("test") is not (mode == "test")
            or not isinstance(payment.get("recipient"), dict)
            or str(payment["recipient"].get("account_id"))
            != os.environ["YOOKASSA_SHOP_ID"]
        ):
            raise ApiError(409, "Платёж получен не от выбранного магазина")

    def apply_payment(self, con, local, remote):
        self.verify_yookassa_shop(remote)
        if (
            remote.get("id") != local["provider_id"]
            or remote.get("amount", {}).get("currency") != "RUB"
            or remote.get("amount", {}).get("value")
            != f"{local['amount_kopecks'] / 100:.2f}"
            or remote.get("metadata", {}).get("user_id") != local["user_id"]
            or remote.get("metadata", {}).get("plan") != local["plan"]
        ):
            raise ApiError(409, "Данные платежа не совпали")
        status = remote.get("status")
        if status not in ("pending", "succeeded", "canceled"):
            return
        if status == "succeeded" and remote.get("paid") is not True:
            raise ApiError(409, "Платёж не подтверждён как оплаченный")
        with _LOCK:
            con.execute("BEGIN IMMEDIATE")
            try:
                current = con.execute(
                    "SELECT status FROM payments WHERE id=?", (local["id"],)
                ).fetchone()
                if current["status"] != status and current["status"] == "pending":
                    con.execute(
                        "UPDATE payments SET status=?, activated_at=CASE WHEN ?='succeeded' THEN ? ELSE activated_at END WHERE id=?",
                        (status, status, now(), local["id"]),
                    )
                    if status == "succeeded":
                        con.execute(
                            "UPDATE users SET entitlement_until=max(coalesce(entitlement_until,0),?)+?,plan=? WHERE id=?",
                            (
                                now(),
                                PLANS[local["plan"]][1] * 86400,
                                "pro",
                                local["user_id"],
                            ),
                        )
                    event(con, local["user_id"], "payment_" + status)
                    audit(con, None, "payment." + status, local["id"])
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise

    def apply_refund(self, con, remote):
        refund_id = remote.get("id")
        payment_id = remote.get("payment_id")
        if (
            not isinstance(refund_id, str)
            or not isinstance(payment_id, str)
            or remote.get("status") != "succeeded"
        ):
            raise ApiError(409, "Возврат не подтверждён")
        payment = con.execute(
            "SELECT * FROM payments WHERE provider_id=?", (payment_id,)
        ).fetchone()
        if not payment or payment["status"] != "succeeded":
            raise ApiError(409, "Исходный платёж не найден")
        if (
            remote.get("amount", {}).get("currency") != "RUB"
            or remote.get("amount", {}).get("value")
            != f"{payment['amount_kopecks'] / 100:.2f}"
        ):
            raise ApiError(
                409, "Частичный или несоответствующий возврат требует ручной обработки"
            )
        with _LOCK:
            con.execute("BEGIN IMMEDIATE")
            try:
                existing = con.execute(
                    "SELECT 1 FROM refunds WHERE provider_id=?", (refund_id,)
                ).fetchone()
                if not existing:
                    con.execute(
                        "INSERT INTO refunds(id,payment_id,provider_id,amount_kopecks,status,created_at) VALUES(?,?,?,?,?,?)",
                        (
                            uid(),
                            payment["id"],
                            refund_id,
                            payment["amount_kopecks"],
                            "succeeded",
                            now(),
                        ),
                    )
                    # Rebuild remaining paid time without the refunded grant.
                    grants = con.execute(
                        """SELECT p.plan,p.activated_at FROM payments p
                        WHERE p.user_id=? AND p.status='succeeded' AND p.activated_at IS NOT NULL
                        AND NOT EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded')
                        ORDER BY p.activated_at,p.created_at,p.id""",
                        (payment["user_id"],),
                    ).fetchall()
                    until, plan = 0, "free"
                    for grant in grants:
                        until = (
                            max(until, grant["activated_at"])
                            + PLANS[grant["plan"]][1] * 86400
                        )
                        plan = "pro"
                    con.execute(
                        "UPDATE users SET entitlement_until=?,plan=? WHERE id=?",
                        (until, plan if until > now() else "free", payment["user_id"]),
                    )
                    event(con, payment["user_id"], "payment_refunded")
                    audit(con, None, "payment.refunded", payment["id"])
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise


def main():
    migrate()

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True

        def server_bind(self):
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.allow_reuse_address = False
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    server = Server((os.getenv("HOST", "127.0.0.1"), PORT), Handler)
    print(f"Smetra listening on {PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
