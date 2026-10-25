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
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path
from email.message import EmailMessage
from backend.plan_catalog import PURCHASES

try:
    from backend import business, mytracker, revenue, token_packs
except ModuleNotFoundError:
    import business
    import mytracker
    import revenue
    import token_packs

try:
    from backend.estimate_safety import LEGAL_CONSENT_VERSION, REGISTRATION_CONSENT_VERSION
except ModuleNotFoundError:
    from estimate_safety import LEGAL_CONSENT_VERSION, REGISTRATION_CONSENT_VERSION

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "data" / "smetra.sqlite3")))
WEB = ROOT / "apps" / "web"
PORT = int(os.getenv("PORT", "8080"))
ORIGIN = os.getenv("PUBLIC_ORIGIN", "https://" + os.environ['VERCEL_URL'] if os.getenv('VERCEL_URL') else f"http://localhost:{PORT}").rstrip("/")
COOKIE_SECURE = ORIGIN.startswith("https://")
# Browser deployments may be reached through the canonical domain and the
# historical Vercel alias. Origin checks must compare exact, trusted origins,
# never a suffix match or an untrusted Host/X-Forwarded-Host header.
BROWSER_ORIGINS = frozenset({
    ORIGIN,
    "https://smetra.online",
    "https://www.smetra.online",
    "https://smetra.vercel.app",
})
_LOCK = threading.RLock()
_SQLITE_WAL_LOCK = threading.Lock()
_SQLITE_WAL_FILES = set()
RATE = {}
REQUIRED_CLOUD_SCHEMA_VERSION = 56
PLANS = {code: (price, days) for code, (_, price, days) in PURCHASES.items()}


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
        con.execute("PRAGMA busy_timeout=10000")
        # WAL is persistent in SQLite's database file. Reissuing the mode-change
        # pragma for every HTTP request needlessly enters SQLite's journal-mode
        # coordination path and can contend with concurrent readers/writers.
        # Track the file identity (not just the path) so a replaced test/database
        # file is configured again without repeating this work on warm requests.
        if str(DB_PATH) != ":memory:":
            stat = DB_PATH.stat()
            wal_key = (str(DB_PATH.resolve()), stat.st_dev, stat.st_ino)
            if wal_key not in _SQLITE_WAL_FILES:
                with _SQLITE_WAL_LOCK:
                    if wal_key not in _SQLITE_WAL_FILES:
                        mode = con.execute("PRAGMA journal_mode=WAL").fetchone()
                        if mode and str(mode[0]).lower() == "wal":
                            _SQLITE_WAL_FILES.add(wal_key)
        with con:
            yield con
    finally:
        con.close()


def migrate():
    if os.getenv("DATABASE_URL"):
        # Cloud schema changes are explicit, versioned Supabase migrations.
        # Keep startup gated on the newest required migration: checking an older
        # version can let code boot against a partially migrated production DB.
        with db() as con:
            version = con.execute(
                "SELECT version FROM schema_migrations WHERE version=?",
                (REQUIRED_CLOUD_SCHEMA_VERSION,),
            ).fetchone()
            if not version:
                raise RuntimeError(
                    "Apply Smetra PostgreSQL migrations through version "
                    f"{REQUIRED_CLOUD_SCHEMA_VERSION} before starting"
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
        con.executescript((ROOT / "backend" / "migrations" / "031_email_login_challenges.sql").read_text(encoding="utf-8"))
        con.executescript((ROOT / "backend" / "migrations" / "032_retention_indexes.sql").read_text(encoding="utf-8"))
        con.executescript((ROOT / "backend" / "migrations" / "033_estimate_share_responses.sql").read_text(encoding="utf-8"))
        from backend.ai_tokens import ensure_schema as ensure_ai_tokens
        ensure_ai_tokens(con)


def now():
    return int(time.time())


def uid():
    return str(uuid.uuid4())


def mail(to, subject, message):
    required = ("SMTP_HOST", "SMTP_FROM", "SMTP_USER", "SMTP_PASSWORD")
    if any(not os.getenv(name) for name in required):
        raise ApiError(503, "Почта сервиса временно недоступна")
    email = EmailMessage()
    from backend.mail_headers import configure
    configure(email, os.environ["SMTP_FROM"])
    email["To"], email["Subject"] = to, subject
    email.set_content(message)
    email["Reply-To"] = "support@smetra.online"
    from backend.mail_templates import action_html
    if message.startswith(("https://", "http://localhost:")):
        # An invitation may append explanatory text after a single trusted
        # first-line URL. Never turn the entire multiline message into href.
        link = message.splitlines()[0].strip()
        parsed = urllib.parse.urlsplit(link)
        if parsed.scheme in ("https", "http") and parsed.hostname in (
            "smetra.online", "www.smetra.online", "smetra.vercel.app", "localhost"
        ) and not parsed.username and not parsed.password:
            email.add_alternative(action_html(subject, link), subtype="html")
    port = int(os.getenv("SMTP_PORT", "587"))
    context = ssl.create_default_context()
    options = {"timeout": 12}
    if port == 465:
        transport = smtplib.SMTP_SSL
        options["context"] = context
    else:
        transport = smtplib.SMTP
    with transport(os.environ["SMTP_HOST"], port, **options) as smtp:
        if port != 465:
            smtp.starttls(context=context)
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
    avatar_id = user["avatar_id"] if "avatar_id" in user.keys() else ""
    avatar_url = ("https://avatars.yandex.net/get-yapic/" + avatar_id + "/islands-200"
                  if avatar_id and re.fullmatch(r"[A-Za-z0-9_/-]{1,150}", avatar_id)
                  else "")
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "avatar_url": avatar_url,
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
            self.send_header("Retry-After", str(getattr(self, "retry_after", 60)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Request-ID", getattr(self, "request_id", ""))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data: blob: https://avatars.yandex.net https://www.google.com/s2/favicons; frame-src blob:; connect-src 'self'; form-action 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'",
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
        maximum = 7_000_000 if path == "/api/files" else 1_400_000 if self.command == "PATCH" and path.startswith("/api/files/") else 2_000_000 if path == "/api/voice/draft" else 3_000_000 if path in ("/api/ai/draft", "/api/assistant/stream", "/api/assistant/chat", "/api/design-projects/draft") else 2_100_000 if path.startswith("/api/construction/objects/") and path.endswith("/import") else 1_500_000 if path == "/api/public/intake" else 65536
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
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        row = con.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.deleted_at IS NULL",
            (token_hash, now()),
        ).fetchone()
        if not row:
            raise ApiError(401, "Сессия истекла")
        if row["blocked"]:
            raise ApiError(403, "Аккаунт заблокирован")
        if admin and row["role"] != "admin":
            raise ApiError(403, "Недостаточно прав")
        self.session_token_hash = token_hash
        return row

    def throttle(self, key, limit=15, window=60):
        try:
            from backend.redis_infra import RedisUnavailable, rate_limit
        except ModuleNotFoundError:
            from redis_infra import RedisUnavailable, rate_limit
        try:
            result = rate_limit(key, limit, window)
        except RedisUnavailable:
            # Cost-bearing AI requests must not bypass their fast guard during an outage.
            if key.startswith(("assistant:", "ai:")):
                raise ApiError(503, "Ассистент временно недоступен") from None
            result = None  # PostgreSQL remains the distributed fallback.
        if result is not None:
            if not result.allowed:
                self.retry_after = max(1, result.retry_after)
                raise ApiError(429, "Слишком много запросов. Попробуйте позже")
            return
        if os.getenv("DATABASE_URL"):
            try:
                from backend.postgres import throttle
            except ModuleNotFoundError:
                from postgres import throttle
            if not throttle(key, limit, window, now()):
                self.retry_after = window
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
                self.retry_after = window
                raise ApiError(429, "Слишком много запросов. Попробуйте позже")
            RATE[key] = (count + 1, start)

    def require_origin(self):
        origin = self.headers.get("Origin")
        fetch_site = self.headers.get("Sec-Fetch-Site")
        if origin and origin not in BROWSER_ORIGINS:
            raise ApiError(403, "Неверный источник запроса")
        # A browser may mark a request from www.smetra.online as same-site
        # rather than same-origin. Accept only an explicitly trusted origin.
        if fetch_site == "cross-site" or (
            fetch_site == "same-site" and origin not in BROWSER_ORIGINS
        ):
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
        self.retry_after = 60
        try:
            if len(self.path) > 4096:
                raise ApiError(414, "Слишком длинный адрес запроса")
            path, query = self.route()
            if path.startswith("/api/"):
                self._body_length = self.validate_body_length(path)
                root = path.split("/", 3)[2]
                if root not in business.ROUTES | {"auth", "webhooks", "billing", "admin", "me", "profile", "support", "mobile", "cron", "shared-inbox"}:
                    raise ApiError(404, "Не найдено")
                if root == "cron":
                    if method != "GET" or path not in ("/api/cron/assistant", "/api/cron/push", "/api/cron/product-monitor", "/api/cron/cloud-sync", "/api/cron/maintenance"):
                        raise ApiError(404, "Не найдено")
                    if path == "/api/cron/assistant":
                        from backend.assistant_jobs import authenticate

                        authenticate(self)
                    elif path == "/api/cron/maintenance":
                        # Reject anonymous and incorrect cron tokens BEFORE
                        # allocating a Supabase connection from the serverless pool.
                        from backend.maintenance import authenticate
                        authenticate(self, ApiError)
                    elif path == "/api/cron/product-monitor":
                        from backend.product_sources import authenticate_cron
                        authenticate_cron(self)
                    elif path == "/api/cron/cloud-sync":
                        from backend.cloud_drives import authenticate_cron
                        authenticate_cron(self)
                    # /api/cron/push verifies its own dedicated server secret.
                if root == "webhooks" and path not in ("/api/webhooks/yookassa", "/api/webhooks/google-drive"):
                    raise ApiError(404, "Не найдено")
                if root == "mobile" and path != "/api/mobile/presentation":
                    raise ApiError(404, "Не найдено")
            if method != "GET" and path not in ("/api/webhooks/yookassa", "/api/webhooks/google-drive"):
                self.require_origin()
            if method == "GET" and path == "/api/auth/providers":
                from backend.identity import route as identity_route

                identity_route(self, None, method, path, query, ORIGIN)
            elif method == "GET" and path == "/api/billing/catalog":
                from backend.plan_catalog import public_catalog

                plans = [
                    {"code": code, "name": item["name"], "month": item["monthly_kopecks"],
                     "year": item["yearly_kopecks"]}
                    for code, item in public_catalog().items()
                ]
                self.send_json(200, {"plans": plans})
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
            payload = {"error": err.message}
            if err.status == 429:
                payload.update(code="rate_limited", retryAfter=getattr(self, "retry_after", 60))
            self.send_json(err.status, payload)
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
            "/disclaimer": ("disclaimer.html", "text/html"),
            "/contacts": ("contacts.html", "text/html"),
            "/change.html": ("change.html", "text/html"),
            "/change.css": ("change.css", "text/css"),
            "/favicon.ico": ("favicon.ico", "image/x-icon"),
            "/favicon.png": ("favicon.png", "image/png"),
            "/robots.txt": ("robots.txt", "text/plain"),
            "/sitemap.xml": ("sitemap.xml", "application/xml"),
            "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
            "/offline.html": ("offline.html", "text/html"),
            "/offline.css": ("offline.css", "text/css"),
            "/assets/fonts/onest-variable.woff2": ("assets/fonts/onest-variable.woff2", "font/woff2"),
            "/vendor/markdown-it-15.0.2.min.js": ("vendor/markdown-it-15.0.2.min.js", "text/javascript"),
        }
        # Every top-level script is public; the build validates them with node --check.
        js_asset = re.fullmatch(r"/([a-z0-9-]{1,40})\.js", path)
        if js_asset and (WEB / f"{js_asset[1]}.js").is_file():
            public[path] = (f"{js_asset[1]}.js", "text/javascript")
        for name in (
            "arrow-up-right",
            "arrow-up",
            "microphone",
            "arrow-right",
            "play",
            "x",
            "check",
            "file-text",
            "link-simple",
            "pause",
            "sun",
            "moon",
            "arrow-clockwise",
            "bell",
            "book-open",
            "briefcase",
            "buildings",
            "calendar",
            "chat-circle",
            "chat-circle",
            "check-square",
            "credit-card",
            "download-simple",
            "files",
            "floppy-disk",
            "folder",
            "funnel",
            "gear",
            "house",
            "lifebuoy",
            "magnifying-glass",
            "paperclip",
            "pencil-simple",
            "plus",
            "push-pin",
            "shield-check",
            "sign-out",
            "sparkle",
            "trash",
            "users",
            "wallet",
        ):
            icon = f"assets/icons/{name}.svg"
            public["/" + icon] = (icon, "image/svg+xml")
        # The shared interface system lives in apps/web/ui as flat CSS/JS files.
        ui_asset = re.fullmatch(r"/ui/([a-z0-9-]{1,40})\.(css|js)", path)
        if ui_asset and (WEB / "ui" / f"{ui_asset[1]}.{ui_asset[2]}").is_file():
            public[path] = (
                f"ui/{ui_asset[1]}.{ui_asset[2]}",
                "text/css" if ui_asset[2] == "css" else "text/javascript",
            )
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
        self.send_header("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
        self.send_header("X-Request-ID", getattr(self, "request_id", ""))
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data: blob: https://avatars.yandex.net https://www.google.com/s2/favicons; frame-src blob:; connect-src 'self'; form-action 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(data)

    def api(self, method, path, query, con):
        if path == "/api/shared-inbox" or path.startswith("/api/shared-inbox/"):
            from backend.estimate_sharing import recipient_route
            return self.send_json(*recipient_route(self,con,method,path))
        from backend.community import handles, route as communication_route
        if handles(path):
            result = communication_route(self, method, path, query, con)
            if result is not None:
                return result
            raise ApiError(404, "Не найдено")
        if path == '/api/billing/pricing' and method == 'GET':
            experiment,variants=revenue.configuration()
            cheapest=min(variants.values(),key=lambda v:v['month'])
            # Public plan list for the landing page. Prices come from the server
            # catalog; PRO Solo follows the active pricing experiment.
            from backend.plan_catalog import public_catalog
            plans=[]
            for code,plan in public_catalog().items():
                month,year=plan['monthly_kopecks'],plan['yearly_kopecks']
                if code=='pro_solo':
                    month,year=cheapest['month'],cheapest['year']
                plans.append({'code':code,'name':plan['name'].split(' / ')[0],'month':month,'year':year,
                              'seats':plan['seats'],'storage_bytes':plan['storage_bytes'],'free_quotes':plan['free_quotes']})
            return self.send_json(200,{'month':cheapest['month'],'year':cheapest['year'],'from_price':len(variants)>1,'experiment':experiment,'plans':plans})
        if path == "/api/cron/assistant" and method == "GET":
            from backend.assistant_jobs import run_one

            return self.send_json(200, run_one(self, con, ORIGIN))
        if path == "/api/cron/push" and method == "GET":
            from backend.push import authenticate_cron, run_batch

            authenticate_cron(self)
            return self.send_json(200, run_batch(con))
        if path == "/api/cron/product-monitor" and method == "GET":
            from backend.product_sources import authenticate_cron, run_monitor_batch

            authenticate_cron(self)
            return self.send_json(200, run_monitor_batch(con))
        if path == "/api/cron/cloud-sync" and method == "GET":
            from backend.cloud_drives import authenticate_cron, run_cloud_batch

            authenticate_cron(self)
            return self.send_json(200, run_cloud_batch(con))
        if path == "/api/cron/maintenance" and method == "GET":
            from backend.maintenance import run as run_maintenance
            return self.send_json(200, run_maintenance(self, con))
        if path == "/api/webhooks/google-drive" and method == "POST":
            from backend.cloud_drives import webhook

            return self.send_json(200, webhook(self, con))
        # The existing Yandex ID callback can also complete the Disk OAuth flow.
        # This lets one registered redirect URI serve login and an explicitly requested
        # read-only Disk grant without confusing the two independent OAuth states.
        if path == "/api/auth/oauth/yandex/callback" and method == "GET":
            state = query.get("state", [""])[0]
            if isinstance(state, str) and state:
                state_hash = hashlib.sha256(state.encode()).hexdigest()
                try:
                    cloud_state = con.execute(
                        "SELECT id FROM cloud_oauth_states WHERE state_hash=? "
                        "AND provider='yandex_disk' AND consumed_at IS NULL AND expires_at>?",
                        (state_hash, now()),
                    ).fetchone()
                except Exception:
                    cloud_state = None
                if cloud_state:
                    path = "/api/premium/cloud/oauth/callback"
        if path == "/api/me/legal-consent" and method in ("GET", "POST"):
            user = self.auth(con)
            if method == "GET":
                row = con.execute(
                    "SELECT document_version,accepted_at,source FROM legal_acceptances "
                    "WHERE user_id=? AND document_version=? LIMIT 1",
                    (user["id"], LEGAL_CONSENT_VERSION),
                ).fetchone()
                return self.send_json(200, {
                    "accepted": bool(row),
                    "version": LEGAL_CONSENT_VERSION,
                    "accepted_at": row["accepted_at"] if row else None,
                })
            data = self.body()
            if data.get("accepted") is not True or data.get("version") != LEGAL_CONSENT_VERSION:
                raise ApiError(400, "Подтвердите согласие с действующей редакцией условий")
            con.execute(
                "INSERT INTO legal_acceptances(id,user_id,document_version,accepted_at,source) "
                "VALUES(?,?,?,?,?) ON CONFLICT(user_id,document_version) DO NOTHING",
                (uid(), user["id"], LEGAL_CONSENT_VERSION, now(), "first_estimate"),
            )
            return self.send_json(200, {
                "accepted": True,
                "version": LEGAL_CONSENT_VERSION,
            })
        starts_ai_operation = method == "POST" and (
            path == "/api/ai/draft"
            or path in (
                "/api/assistant",
                "/api/assistant/chat",
                "/api/assistant/stream",
                "/api/assistant/jobs",
            )
        )
        if starts_ai_operation:
            user = self.auth(con)
            accepted = con.execute(
                "SELECT 1 FROM legal_acceptances WHERE user_id=? AND document_version=? LIMIT 1",
                (user["id"], LEGAL_CONSENT_VERSION),
            ).fetchone()
            if not accepted:
                raise ApiError(428, "Сначала примите условия использования AI-черновиков")
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
            if hasattr(payload, "redirect_url"):
                self.send_response(status)
                self.send_header("Location", payload.redirect_url)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                return
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
        if path in ("/api/auth/email/start", "/api/auth/email/confirm") and method == "POST":
            from backend import email_otp
            from types import SimpleNamespace
            app_context = SimpleNamespace(
                ApiError=ApiError, uid=uid, now=now, hash_password=hash_password,
                REGISTRATION_CONSENT_VERSION=REGISTRATION_CONSENT_VERSION,
                event=event, revenue=revenue,
            )
            handler = email_otp.start if path.endswith("/start") else email_otp.confirm
            return handler(self, con, app_context)
        if path == "/api/auth/register" and method == "POST":
            # When passwordless registration is live, no client may bypass
            # mailbox verification through the legacy password endpoint.
            from backend.email_otp import configured as otp_configured
            if otp_configured() and not ORIGIN.startswith("http://localhost:"):
                raise ApiError(409, "Для регистрации по почте используйте код из письма")
            self.throttle("register:" + self.client_address[0], 5, 3600)
            data = self.body()
            if (
                data.get("legal_acceptance") is not True
                or data.get("legal_version") != REGISTRATION_CONSENT_VERSION
            ):
                raise ApiError(
                    400,
                    "Для регистрации примите Пользовательское соглашение, условия и предупреждение об использовании AI",
                )
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
                con.execute(
                    "INSERT INTO legal_acceptances(id,user_id,document_version,accepted_at,source) "
                    "VALUES(?,?,?,?,?)",
                    (uid(), user_id, REGISTRATION_CONSENT_VERSION, now(), "registration"),
                )
                event(con, user_id, "signup_completed")
                revenue.record(con,user_id,'signup_completed',key='signup:'+user_id)
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
            email = str(data.get("email", "")).lower().strip()
            self.throttle("login-account:" + hashlib.sha256(email[:254].encode()).hexdigest(), 20, 300)
            user = con.execute(
                "SELECT * FROM users WHERE email=?",
                (email,),
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
            with business.transaction_lock_scope(con, (f"user:{row['user_id']}",)):
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
            with business.transaction_lock_scope(con, (f"user:{row['user_id']}",)):
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
            revenue.visit(con, user)
            return self.send_json(200, {"user": user_view(user, con)})
        if path == "/api/admin/revenue" and method == "GET":
            return self.send_json(200, revenue.dashboard(con))
        if path == "/api/billing/events" and method == "POST":
            self.throttle('growth:'+user['id'], 60, 3600)
            data = self.body()
            if data.get('name') not in revenue.CLIENT_EVENTS:
                raise ApiError(400, 'Неизвестное событие')
            offer = revenue.pricing(con, user)
            origin = revenue.source(data.get('source'))
            revenue.record(con, user['id'], data['name'], origin, offer['experiment']+':'+offer['variant'],
                           ':'.join((data['name'],user['id'],origin,str(now()//1800))))
            return self.send_json(200, {'ok': True})
        if path == "/api/billing/referral" and method in ('GET','POST'):
            self.throttle('referral:'+user['id'], 20, 3600)
            data = self.body() if method == 'POST' else {}
            code = data.get('code')
            if code is not None and (not isinstance(code,str) or len(code)>80):
                raise ApiError(400,'Неверный код приглашения')
            return self.send_json(200, revenue.referral(con,user,code))
        if path == "/api/profile":
            from backend.profile_memory import profile_route

            return self.send_json(200, profile_route(con, user, method, self.body() if method == "PATCH" else {}))
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
            workspace_lock_rows = con.execute(
                "SELECT workspace_id AS id FROM workspace_members WHERE user_id=? "
                "UNION SELECT id FROM workspaces WHERE owner_id=?",
                (user["id"], user["id"]),
            ).fetchall()
            lock_scopes = [f"user:{user['id']}"] + [
                f"workspace:{workspace_row['id']}" for workspace_row in workspace_lock_rows
            ]
            with business.transaction_lock_scope(con, lock_scopes):
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
                    con.execute("DELETE FROM user_profiles WHERE user_id=?", (user["id"],))
                    con.execute("DELETE FROM assistant_memory WHERE user_id=?", (user["id"],))
                    con.execute("DELETE FROM pricing_assignments WHERE user_id=?", (user['id'],))
                    con.execute("DELETE FROM referral_rewards WHERE inviter_id=? OR invitee_id=?", (user['id'],user['id']))
                    con.execute("DELETE FROM referral_links WHERE user_id=?", (user['id'],))
                    con.execute("UPDATE growth_events SET user_id=NULL WHERE user_id=?", (user['id'],))
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
            offer=revenue.pricing(con,user)
            payments = con.execute(
                """SELECT p.id,p.plan,p.amount_kopecks,p.created_at,p.confirmation_url,
                CASE WHEN EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded')
                THEN 'refunded' ELSE p.status END AS status
                FROM payments p WHERE p.user_id=? ORDER BY p.created_at DESC LIMIT 30""",
                (user["id"],),
            ).fetchall()
            return self.send_json(
                200,
                {
                    "payments": [dict(r) for r in payments],
                    "plans": {k: v['amount_kopecks'] for k, v in offer['plans'].items()},
                    "pricing": offer,
                    "tokens": token_packs.offer(),
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
            if not isinstance(plan, str) or plan not in PLANS or not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", key):
                raise ApiError(400, "Неверный тариф или ключ запроса")
            expected_amount = data.get('expected_amount_kopecks')
            if 'expected_amount_kopecks' in data and (type(expected_amount) is not int or not 100 <= expected_amount <= 100_000_000):
                raise ApiError(400, "Некорректная сумма выбранного тарифа")
            selected_workspace = data.get("workspace_id")
            if selected_workspace is not None:
                if not isinstance(selected_workspace, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", selected_workspace):
                    raise ApiError(400, "Некорректное рабочее пространство")
                if not con.execute("SELECT id FROM workspaces WHERE id=? AND owner_id=?", (selected_workspace, user["id"])).fetchone():
                    raise ApiError(403, "Тарифом управляет владелец пространства")
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
                if expected_amount is not None and expected_amount != previous['amount_kopecks']:
                    raise ApiError(409, "Стоимость выбранной оплаты изменилась. Обновите тариф.")
                captured = con.execute('SELECT is_test,workspace_id FROM billing_intents WHERE payment_id=?', (previous['id'],)).fetchone()
                if captured and selected_workspace and captured["workspace_id"] != selected_workspace:
                    raise ApiError(409, "Ключ уже использован для другого пространства")
                if captured and captured['is_test'] != int(mode == 'test'):
                    raise ApiError(409, "Режим магазина изменился. Начните новую оплату.")
                refunded = con.execute("SELECT 1 FROM refunds WHERE payment_id=? AND status='succeeded'", (previous['id'],)).fetchone()
                return self.send_json(
                    200,
                    {"url": previous["confirmation_url"], "status": 'refunded' if refunded else previous["status"]},
                )
            try:
                intent = revenue.prepare_intent(con,user,key,plan,data.get('source'),mode=='test',expected_amount, data.get('workspace_id'))
            except ValueError:
                raise ApiError(409,'Условия оплаты изменились. Обновите страницу тарифа.') from None
            amount = intent['amount_kopecks']
            request = {
                "amount": {"value": f"{amount / 100:.2f}", "currency": "RUB"},
                "capture": True,
                "confirmation": {
                    "type": "redirect",
                    "return_url": ORIGIN + "/app?payment=return",
                },
                "description": "Доступ Сметра Про на " + str(intent['duration_days']) + " дней",
                "metadata": {"user_id": user["id"], "plan": plan},
            }
            # YooKassa keys belong to the shop, rather than a browser/account,
            # and must be at most 64 characters. Keep retries deterministic.
            provider_key = hashlib.sha256(("checkout:v1:"+user["id"]+":"+key).encode()).hexdigest()
            try:
                result = self.provider_call("/payments", "POST", request, provider_key)
            except ApiError:
                revenue.record(con,user['id'],'checkout_failed',intent['source'],intent['variant'],'checkout-failed:'+intent['id'])
                raise
            self.verify_yookassa_shop(result)
            if result.get("amount") != request["amount"] or result.get("metadata") != request["metadata"]:
                raise ApiError(502, "Платёжный сервис вернул данные другого запроса")
            if not result.get("id") or not result.get("confirmation", {}).get(
                "confirmation_url", ""
            ).startswith("https://"):
                raise ApiError(502, "Платежный сервис вернул неполный ответ")
            try:
                saved, created = revenue.persist_checkout(con,user,key,plan,intent,result)
            except ValueError:
                raise ApiError(409,"Conflicting checkout") from None
            return self.send_json(201 if created else 200, {"url":saved["confirmation_url"],"status":saved["status"]})
        if path == "/api/billing/tokens/checkout" and method == "POST":
            return self.token_checkout(con, user)
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
            return self.send_json(200, {"user": user_view(current, con),"payments":[dict(r) for r in con.execute('SELECT id,status FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 3',(user['id'],))]})
        if path == "/api/admin/overview" and method == "GET":
            # Keep this query portable: production uses PostgreSQL, while local
            # development and tests use SQLite. Pass the timestamp instead of
            # using unixepoch(), which is not available in PostgreSQL.
            stats = {
                "users": con.execute(
                    "SELECT count(*) FROM users WHERE deleted_at IS NULL"
                ).fetchone()[0],
                "quotes": con.execute("SELECT count(*) FROM quotes").fetchone()[0],
                "subscriptions": con.execute(
                    "SELECT count(*) FROM users WHERE entitlement_until > ? AND deleted_at IS NULL",
                    (now(),),
                ).fetchone()[0],
                "revenue_kopecks": con.execute(
                    "SELECT coalesce(sum(p.amount_kopecks),0) FROM payments p JOIN billing_intents b ON b.payment_id=p.id WHERE b.is_test=0 AND p.status='succeeded' AND NOT EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded')"
                ).fetchone()[0],
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
                    "SELECT s.id,s.user_id,u.email,s.message,s.status,s.created_at FROM support s JOIN users u ON u.id=s.user_id ORDER BY s.created_at DESC LIMIT 100"
                )
            ]
            logs = [
                dict(r)
                for r in con.execute(
                    "SELECT a.actor_id,u.email AS actor_email,a.action,a.target,a.detail,a.created_at "
                    "FROM audit a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.created_at DESC LIMIT 100"
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
        if path == "/api/admin/users" and method == "GET":
            search = query.get("q", [""])[0].strip()
            status = query.get("status", ["all"])[0]
            try:
                offset = int(query.get("offset", ["0"])[0])
            except ValueError:
                raise ApiError(400, "Некорректная страница") from None
            if len(search) > 100 or status not in ("all", "active", "blocked", "pro") or not 0 <= offset <= 100000:
                raise ApiError(400, "Некорректный фильтр")
            conditions = ["deleted_at IS NULL"]
            params = []
            if search:
                conditions.append("(lower(email) LIKE ? OR lower(name) LIKE ?)")
                params.extend(["%" + search.lower() + "%"] * 2)
            if status == "active":
                conditions.append("blocked=0")
            elif status == "blocked":
                conditions.append("blocked=1")
            elif status == "pro":
                conditions.append("entitlement_until>?")
                params.append(now())
            where = " AND ".join(conditions)
            count = con.execute("SELECT count(*) FROM users WHERE " + where, params).fetchone()[0]
            rows = [dict(r) for r in con.execute(
                "SELECT id,email,name,role,blocked,plan,entitlement_until,created_at "
                "FROM users WHERE " + where + " ORDER BY created_at DESC,id DESC LIMIT 25 OFFSET ?",
                (*params, offset),
            )]
            return self.send_json(200, {"users": rows, "total": count, "offset": offset})
        if path.startswith("/api/admin/support/") and method == "PATCH":
            target = path.removeprefix("/api/admin/support/")
            if len(target) > 100:
                raise ApiError(400, "Некорректное обращение")
            status = self.body().get("status")
            if status not in ("open", "closed"):
                raise ApiError(400, "Некорректный статус")
            row = con.execute("SELECT status FROM support WHERE id=?", (target,)).fetchone()
            if not row:
                raise ApiError(404, "Обращение не найдено")
            if row["status"] != status:
                con.execute("UPDATE support SET status=? WHERE id=?", (status, target))
                audit(con, user["id"], "admin.support." + status, target)
            return self.send_json(200, {"ok": True})
        if path.startswith("/api/admin/users/") and method in ("GET", "PATCH"):
            from backend import admin_users
            target = path.removeprefix("/api/admin/users/")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", target):
                raise ApiError(404, "Пользователь не найден")
            if method == "GET":
                return self.send_json(200, admin_users.detail(con, target))
            self.throttle("admin-user-action:" + user["id"], 120, 60)
            return self.send_json(200, admin_users.act(con, user, target, self.body(), audit))
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
        revenue.visit(con,row)
        payload = {"user": user_view(row, con)}
        # Browsers use the HttpOnly cookie; only native/API clients need a
        # bearer token in JSON. Browser JavaScript cannot override Origin.
        if (
            self.headers.get("Origin") not in BROWSER_ORIGINS
            and self.headers.get("Sec-Fetch-Site") != "same-origin"
        ):
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

    def token_checkout(self, con, user):
        """One-time token pack. Mirrors subscription checkout; grants happen in apply_payment."""
        if user["email_verified_at"] is None:
            raise ApiError(403, "Подтвердите почту перед оплатой")
        data = self.body()
        millions = data.get("millions")
        key = self.headers.get("Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", key):
            raise ApiError(400, "Неверный ключ запроса")
        amount = token_packs.price(millions)
        plan = token_packs.code(millions)
        expected = data.get("expected_amount_kopecks")
        if expected is not None and expected != amount:
            raise ApiError(409, "Цена токенов изменилась. Обновите страницу.")
        mode = yookassa_mode(user)
        if mode == "off":
            raise ApiError(503, "Оплата пока недоступна")
        self.throttle("token-checkout:" + user["id"], 10, 600)
        previous = con.execute("SELECT * FROM payments WHERE user_id=? AND idempotency_key=?", (user["id"], key)).fetchone()
        if previous:
            if previous["plan"] != plan or previous["amount_kopecks"] != amount:
                raise ApiError(409, "Ключ уже использован для другой покупки")
            refunded = con.execute("SELECT 1 FROM refunds WHERE payment_id=? AND status='succeeded'", (previous["id"],)).fetchone()
            return self.send_json(200, {"url": previous["confirmation_url"], "status": "refunded" if refunded else previous["status"]})
        workspace_id = business.ensure_workspace(con, user)
        con.execute(
            "INSERT INTO billing_intents(id,user_id,request_key,plan,amount_kopecks,duration_days,variant,source,is_test,created_at,bonus_ai_messages,workspace_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,request_key) DO NOTHING",
            (uid(), user["id"], key, plan, amount, 1, "tokens", revenue.source(data.get("source")), int(mode == "test"), now(), 0, workspace_id),
        )
        intent = con.execute("SELECT * FROM billing_intents WHERE user_id=? AND request_key=?", (user["id"], key)).fetchone()
        if intent["plan"] != plan or intent["amount_kopecks"] != amount:
            raise ApiError(409, "Ключ уже использован для другой покупки")
        request = {
            "amount": {"value": f"{amount / 100:.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": ORIGIN + "/app?payment=return#billing"},
            "description": f"Токены ассистента Сметры: {millions} млн",
            "metadata": {"user_id": user["id"], "plan": plan},
        }
        provider_key = hashlib.sha256(("tokens:v1:" + user["id"] + ":" + key).encode()).hexdigest()
        result = self.provider_call("/payments", "POST", request, provider_key)
        self.verify_yookassa_shop(result)
        if result.get("amount") != request["amount"] or result.get("metadata") != request["metadata"]:
            raise ApiError(502, "Платёжный сервис вернул данные другого запроса")
        if not result.get("id") or not result.get("confirmation", {}).get("confirmation_url", "").startswith("https://"):
            raise ApiError(502, "Платежный сервис вернул неполный ответ")
        try:
            saved, created = revenue.persist_checkout(con, user, key, plan, intent, result)
        except ValueError:
            raise ApiError(409, "Conflicting checkout") from None
        return self.send_json(201 if created else 200, {"url": saved["confirmation_url"], "status": saved["status"]})

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
        newly_succeeded = False
        with _LOCK, business.transaction_lock_scope(
            con, (f"user:{local['user_id']}",)
        ):
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
                    pack = token_packs.millions_of(local["plan"])
                    if status == "succeeded" and pack:
                        # A token pack never changes the subscription; it only fills the wallet.
                        from backend import ai_tokens
                        ai_tokens.credit(con, local["user_id"], pack * token_packs.MILLION, "purchase",
                                         f"{pack} млн", "payment:" + local["id"])
                        terms = con.execute('SELECT * FROM billing_intents WHERE payment_id=?', (local['id'],)).fetchone()
                        if terms and not terms['is_test']:
                            revenue.record(con, local['user_id'], 'payment_success', terms['source'], terms['variant'], 'payment:' + local['id'] + ':succeeded')
                    elif status == "succeeded":
                        terms = con.execute('SELECT * FROM billing_intents WHERE payment_id=?',(local['id'],)).fetchone()
                        prior_user = con.execute('SELECT entitlement_until FROM users WHERE id=?',(local['user_id'],)).fetchone()
                        grant_days = terms['duration_days'] if terms else PLANS[local["plan"]][1]
                        entitlement_until = max(int(prior_user['entitlement_until'] or 0), now()) + grant_days * 86400
                        con.execute(
                            "UPDATE users SET entitlement_until=?,plan=? WHERE id=?",
                            (entitlement_until, "pro", local["user_id"]),
                        )
                        # Gift credits are issued only for a provider-confirmed live payment.
                        # The amount and expiry are fixed in the original payment intent.
                        bonus = int(terms['bonus_ai_messages'] or 0) if terms else 0
                        if terms and not terms['is_test'] and bonus > 0:
                            con.execute(
                                "INSERT INTO assistant_bonus_grants(id,user_id,payment_id,amount,remaining,expires_at,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(payment_id) DO NOTHING",
                                (uid(), local['user_id'], local['id'], bonus, bonus, entitlement_until, now()),
                            )
                        revenue.rebuild_workspace_entitlement(con, local["user_id"], terms["workspace_id"] if terms else None)
                        newly_succeeded = True
                    if status in ('succeeded','canceled') and not pack:
                        revenue.payment_event(con,local,status,status=='succeeded' and prior_user['entitlement_until']>now())
                    event(con, local["user_id"], "payment_" + status)
                    audit(con, None, "payment." + status, local["id"])
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        # Advertising attribution must never participate in the payment DB transaction.
        # This fires only for the first pending -> succeeded transition, so duplicate
        # YooKassa webhooks do not duplicate the conversion.
        if newly_succeeded:
            mytracker.track_custom_event(
                local["user_id"],
                "pro_subscription_started",
                {"source": "yookassa", "plan": local["plan"]},
            )

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
        with _LOCK, business.transaction_lock_scope(
            con, (f"user:{payment['user_id']}",)
        ):
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
                    pack = token_packs.millions_of(payment["plan"])
                if not existing and pack:
                    from backend import ai_tokens
                    # Tokens already spent cannot be taken back; the rest of the pack is.
                    moved = con.execute("SELECT delta FROM ai_token_ledger WHERE user_id=? AND ref=?",
                                        (payment["user_id"], "payment:" + payment["id"])).fetchone()
                    if moved:
                        ai_tokens._wallet_add(con, payment["user_id"], -int(moved["delta"]), "refund_revoke", "", "refund:" + payment["id"])
                    event(con, payment["user_id"], "payment_refunded")
                    audit(con, None, "payment.refunded", payment["id"])
                elif not existing:
                    # Rebuild remaining paid time without the refunded grant.
                    grants = con.execute(
                        """SELECT p.plan,p.activated_at,b.duration_days FROM payments p LEFT JOIN billing_intents b ON b.payment_id=p.id
                        WHERE p.user_id=? AND p.status='succeeded' AND p.activated_at IS NOT NULL
                        AND p.plan NOT LIKE 'tokens_%'
                        AND NOT EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded')
                        ORDER BY p.activated_at,p.created_at,p.id""",
                        (payment["user_id"],),
                    ).fetchall()
                    until, plan = 0, "free"
                    for grant in grants:
                        until = (
                            max(until, grant["activated_at"])
                            + (grant['duration_days'] or PLANS[grant["plan"]][1]) * 86400
                        )
                        plan = "pro"
                    con.execute(
                        "UPDATE users SET entitlement_until=?,plan=? WHERE id=?",
                        (until, plan if until > now() else "free", payment["user_id"]),
                    )
                    refunded_terms = con.execute("SELECT workspace_id FROM billing_intents WHERE payment_id=?", (payment["id"],)).fetchone()
                    revenue.rebuild_workspace_entitlement(con, payment["user_id"], refunded_terms["workspace_id"] if refunded_terms else None)
                    # Any unused gift credits attached to a fully refunded purchase are revoked.
                    con.execute("UPDATE assistant_bonus_grants SET remaining=0 WHERE payment_id=?", (payment['id'],))
                    from backend import ai_tokens
                    ai_tokens.revoke_purchase_bonus(con, payment["user_id"], payment["id"])
                    event(con, payment["user_id"], "payment_refunded")
                    terms=con.execute('SELECT is_test,source,variant FROM billing_intents WHERE payment_id=?',(payment['id'],)).fetchone()
                    if terms and not terms['is_test']:
                        revenue.record(con,payment['user_id'],'subscription_cancelled',terms['source'],terms['variant'],'refund:'+refund_id)
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
