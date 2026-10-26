"""Private partner acquisition, catalog ingestion and verified-payment commissions.

Partner API keys are distinct from user sessions. This module never authorizes
payment, moves money or calls external vendor URLs.
"""
import hashlib
import ipaddress
import re
import secrets
import time
import urllib.parse
import uuid

COOKIE_NAME = "smetra_partner"
CLICK_TTL = 30 * 86400
HOLD_SECONDS = 30 * 86400
MAX_REFERRAL_AGE = 7 * 86400
MAX_PRODUCTS = 100
SUBSCRIPTION_PREFIXES = ("pro_", "team_")
CODE_RE = re.compile(r"[a-z0-9][a-z0-9_-]{2,39}\Z")
SKU_RE = re.compile(r"[A-Za-z0-9_.:-]{1,80}\Z")


class PartnerError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _now():
    return int(time.time())


def _id():
    return str(uuid.uuid4())


def _sha(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _required_text(value, field, maxlen):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maxlen:
        raise PartnerError(400, "Некорректное поле: " + field)
    return value.strip()


def _host(host):
    host = _required_text(host, "allowed_host", 180).lower().rstrip(".")
    if not re.fullmatch(r"[a-z0-9.-]+", host) or "." not in host or ".." in host:
        raise PartnerError(400, "Некорректный домен партнёра")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise PartnerError(400, "IP вместо домена запрещён")
    if host.endswith((".localhost", ".local", ".internal", ".test", ".invalid", ".example")):
        raise PartnerError(400, "Тестовые или внутренние домены запрещены")
    return host


def _url(value, host):
    value = _required_text(value, "url", 2048)
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        raise PartnerError(400, "Некорректный адрес товара") from None
    if (parsed.scheme != "https" or not parsed.hostname or
            parsed.username is not None or parsed.password is not None or
            port not in (None, 443) or parsed.hostname.lower().rstrip(".") != host or
            any(ord(ch) < 32 for ch in value) or "\\" in value):
        raise PartnerError(400, "Товар должен вести на подтверждённый HTTPS-домен партнёра")
    return value


def create_partner(con, data):
    """Admin-only caller. Return raw API token once; only its hash is stored."""
    if not isinstance(data, dict):
        raise PartnerError(400, "Некорректные параметры")
    code = data.get("code")
    if not isinstance(code, str) or not CODE_RE.fullmatch(code):
        raise PartnerError(400, "Код: 3–40 символов, латиница, цифры, _ или -")
    name = _required_text(data.get("name"), "name", 120)
    allowed_host = _host(data.get("allowed_host"))
    bps = data.get("commission_bps", 2000)
    days = data.get("term_days", 365)
    if type(bps) is not int or not 0 <= bps <= 3000:
        raise PartnerError(400, "Комиссия должна быть от 0 до 30%")
    if type(days) is not int or not 30 <= days <= 730:
        raise PartnerError(400, "Некорректный срок комиссионного периода")
    secret = "smp_live_" + secrets.token_urlsafe(36)
    partner_id = _id()
    from backend.business import transaction
    with transaction(con, lock_scopes=("partner-admin:onboard",)):
        con.execute(
            "INSERT INTO partner_accounts(id,code,name,allowed_host,active,commission_bps,term_days,created_at) "
            "VALUES(?,?,?,?,1,?,?,?)",
            (partner_id, code, name, allowed_host, bps, days, _now()),
        )
        con.execute(
            "INSERT INTO partner_api_tokens(id,partner_id,token_hash,created_at) VALUES(?,?,?,?)",
            (_id(), partner_id, _sha(secret), _now()),
        )
    return {"id": partner_id, "code": code, "name": name,
            "referral_path": "/api/partners/r/" + code, "api_key": secret}


def list_partners(con):
    rows = con.execute(
        "SELECT id,code,name,allowed_host,active,commission_bps,term_days,created_at "
        "FROM partner_accounts ORDER BY created_at DESC LIMIT 200"
    ).fetchall()
    return {"partners": [dict(row) for row in rows]}


def auth_partner(con, header):
    if (not isinstance(header, str) or len(header) > 160 or
            not header.startswith("Partner smp_live_")):
        raise PartnerError(401, "Нужен партнёрский API-ключ")
    token = header[len("Partner "):]
    if not re.fullmatch(r"smp_live_[A-Za-z0-9_-]{35,100}\Z", token):
        raise PartnerError(401, "Неверный партнёрский API-ключ")
    row = con.execute(
        "SELECT p.* FROM partner_api_tokens k JOIN partner_accounts p ON p.id=k.partner_id "
        "WHERE k.token_hash=? AND k.revoked_at IS NULL AND p.active=1",
        (_sha(token),),
    ).fetchone()
    if not row:
        raise PartnerError(401, "Партнёрский ключ отозван или не найден")
    return row


def begin_visit(con, code):
    if not CODE_RE.fullmatch(code):
        raise PartnerError(404, "Партнёр не найден")
    row = con.execute(
        "SELECT id FROM partner_accounts WHERE code=? AND active=1", (code,)
    ).fetchone()
    if not row:
        raise PartnerError(404, "Партнёр не найден")
    raw = secrets.token_urlsafe(32)
    moment = _now()
    con.execute(
        "INSERT INTO partner_clicks(id,partner_id,token_hash,created_at,expires_at) VALUES(?,?,?,?,?)",
        (_id(), row["id"], _sha(raw), moment, moment + CLICK_TTL),
    )
    return raw


def cookie_header(token, secure=True):
    return (f"{COOKIE_NAME}={token}; Path=/api; Max-Age={CLICK_TTL}; "
            "HttpOnly; SameSite=Lax" + ("; Secure" if secure else ""))


def _cookie_value(header):
    if not isinstance(header, str):
        return ""
    for part in header.split(";"):
        key, sep, value = part.strip().partition("=")
        if sep and key == COOKIE_NAME and re.fullmatch(r"[A-Za-z0-9_-]{35,100}\Z", value):
            return value
    return ""


def capture(con, user, cookie):
    """Attribute only a genuinely new account after a tracked visit.

    First-touch is immutable. The client cannot select the partner on a checkout.
    """
    raw = _cookie_value(cookie)
    if not raw or user["blocked"] or user["deleted_at"] is not None:
        return False
    moment = _now()
    click = con.execute(
        "SELECT c.* FROM partner_clicks c JOIN partner_accounts p ON p.id=c.partner_id "
        "WHERE c.token_hash=? AND c.expires_at>? AND p.active=1",
        (_sha(raw), moment),
    ).fetchone()
    if not click:
        return False
    if not click["created_at"] <= user["created_at"] <= click["created_at"] + MAX_REFERRAL_AGE:
        return False
    if con.execute("SELECT 1 FROM partner_attributions WHERE user_id=?", (user["id"],)).fetchone():
        return False
    if con.execute("SELECT 1 FROM payments WHERE user_id=? AND status='succeeded'", (user["id"],)).fetchone():
        return False
    p = con.execute(
        "SELECT commission_bps,term_days FROM partner_accounts WHERE id=?", (click["partner_id"],)
    ).fetchone()
    created = con.execute(
        "INSERT INTO partner_attributions(user_id,partner_id,click_id,rate_bps,term_days,created_at) "
        "VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO NOTHING",
        (user["id"], click["partner_id"], click["id"], p["commission_bps"], p["term_days"], moment),
    )
    return created.rowcount > 0


def record_subscription_payment(con, payment):
    """Call only from verified pending->succeeded payment transaction."""
    terms = con.execute(
        "SELECT is_test FROM billing_intents WHERE payment_id=?", (payment["id"],)
    ).fetchone()
    if (not terms or terms["is_test"] or not payment["plan"].startswith(SUBSCRIPTION_PREFIXES)):
        return False
    attribution = con.execute(
        "SELECT a.*,p.active FROM partner_attributions a "
        "JOIN partner_accounts p ON p.id=a.partner_id WHERE a.user_id=?",
        (payment["user_id"],),
    ).fetchone()
    if not attribution or not attribution["active"]:
        return False
    moment = int(payment["activated_at"] or _now())
    start = attribution["first_paid_at"]
    if start is None:
        con.execute(
            "UPDATE partner_attributions SET first_paid_at=? WHERE user_id=? AND first_paid_at IS NULL",
            (moment, payment["user_id"]),
        )
        start = con.execute(
            "SELECT first_paid_at FROM partner_attributions WHERE user_id=?",
            (payment["user_id"],),
        ).fetchone()["first_paid_at"]
    if not start <= moment < start + attribution["term_days"] * 86400:
        return False
    if con.execute("SELECT 1 FROM refunds WHERE payment_id=? AND status='succeeded'",
                   (payment["id"],)).fetchone():
        return False
    gross = int(payment["amount_kopecks"])
    commission = gross * attribution["rate_bps"] // 10000
    if commission <= 0:
        return False
    con.execute(
        "INSERT INTO partner_commissions(id,partner_id,user_id,payment_id,gross_kopecks,"
        "commission_kopecks,rate_bps,status,created_at,ready_at) "
        "VALUES(?,?,?,?,?,?,?,'pending',?,?) ON CONFLICT(payment_id) DO NOTHING",
        (_id(), attribution["partner_id"], payment["user_id"], payment["id"],
         gross, commission, attribution["rate_bps"], moment, moment + HOLD_SECONDS),
    )
    return True


def reverse_subscription_payment(con, payment_id):
    """A verified full refund invalidates commission, including after hold."""
    return con.execute(
        "UPDATE partner_commissions SET status='reversed' "
        "WHERE payment_id=? AND status='pending'",
        (payment_id,),
    ).rowcount


def summary(con, partner):
    moment = _now()
    result = con.execute(
        "SELECT count(*) AS conversions,"
        "coalesce(sum(CASE WHEN status='pending' THEN commission_kopecks ELSE 0 END),0) AS earned_kopecks,"
        "coalesce(sum(CASE WHEN status='pending' AND ready_at<=? THEN commission_kopecks ELSE 0 END),0) AS cleared_kopecks,"
        "coalesce(sum(CASE WHEN status='reversed' THEN commission_kopecks ELSE 0 END),0) AS reversed_kopecks "
        "FROM partner_commissions WHERE partner_id=?", (moment, partner["id"]),
    ).fetchone()
    clicks = con.execute(
        "SELECT count(*) FROM partner_clicks WHERE partner_id=? AND created_at>=?",
        (partner["id"], moment - 30 * 86400),
    ).fetchone()[0]
    return {"partner": partner["code"], "clicks_30d": clicks, **dict(result),
            "status": "accounting_only", "payouts_enabled": False}


def ingest_products(con, partner, body):
    """Small bounded catalog import; no network fetching or order placement."""
    if not isinstance(body, dict) or not isinstance(body.get("products"), list):
        raise PartnerError(400, "Ожидается массив products")
    items = body["products"]
    if not 1 <= len(items) <= MAX_PRODUCTS:
        raise PartnerError(400, "Пакет каталога: от 1 до 100 товаров")
    seen = set()
    prepared = []
    for item in items:
        if not isinstance(item, dict):
            raise PartnerError(400, "Некорректный товар")
        sku = item.get("sku")
        if not isinstance(sku, str) or not SKU_RE.fullmatch(sku) or sku in seen:
            raise PartnerError(400, "Некорректный или повторяющийся SKU")
        seen.add(sku)
        name = _required_text(item.get("name"), "name", 200)
        price = item.get("price_kopecks")
        if type(price) is not int or not 0 <= price <= 100000000000:
            raise PartnerError(400, "Некорректная цена")
        url = _url(item.get("url"), partner["allowed_host"])
        active = item.get("available", True)
        if type(active) is not bool:
            raise PartnerError(400, "Некорректная доступность")
        prepared.append((sku, name, name.casefold(), price, url, int(active)))
    moment = _now()
    from backend.business import transaction
    with transaction(con, lock_scopes=(f"partner:{partner['id']}",)):
        for sku, name, normalized, price, url, active in prepared:
            con.execute(
                "INSERT INTO partner_products(id,partner_id,sku,name,search_name,price_kopecks,url,available,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(partner_id,sku) DO UPDATE SET "
                "name=excluded.name,search_name=excluded.search_name,"
                "price_kopecks=excluded.price_kopecks,"
                "url=excluded.url,available=excluded.available,updated_at=excluded.updated_at",
                (_id(), partner["id"], sku, name, normalized, price, url, active, moment),
            )
    return {"accepted": len(prepared)}


def offers(con, term):
    from backend.partner_integrations import VERIFICATION_TTL
    term = _required_text(term, "q", 80)
    if len(term) < 2:
        raise PartnerError(400, "Введите минимум 2 символа")
    # Escape SQL LIKE metacharacters; a partner cannot inject SQL by product title.
    pattern = "%" + term.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = con.execute(
        "SELECT p.id,p.name,p.price_kopecks,p.updated_at,a.name AS partner "
        "FROM partner_products p JOIN partner_accounts a ON a.id=p.partner_id "
        "JOIN partner_domain_verifications v ON v.partner_id=a.id AND v.domain=a.allowed_host AND v.status='verified' "
        "WHERE a.active=1 AND p.available=1 AND v.verified_at>? "
        "AND p.search_name LIKE ? ESCAPE '\\' "
        "ORDER BY p.price_kopecks ASC LIMIT 30",
        (_now() - VERIFICATION_TTL, pattern),
    ).fetchall()
    return {"offers": [{**dict(row), "buy_path": "/api/partners/out/" + row["id"]}
                       for row in rows]}


def outbound(con, user, product_id):
    from backend.partner_integrations import VERIFICATION_TTL
    if not re.fullmatch(r"[0-9a-f-]{36}\Z", product_id):
        raise PartnerError(404, "Товар не найден")
    row = con.execute(
        "SELECT p.id,p.partner_id,p.url,a.allowed_host FROM partner_products p "
        "JOIN partner_accounts a ON a.id=p.partner_id "
        "JOIN partner_domain_verifications v ON v.partner_id=a.id AND v.domain=a.allowed_host AND v.status='verified' "
        "WHERE p.id=? AND p.available=1 AND a.active=1 AND v.verified_at>?",
        (product_id, _now() - VERIFICATION_TTL),
    ).fetchone()
    if not row:
        raise PartnerError(404, "Товар не найден")
    url = _url(row["url"], row["allowed_host"])
    con.execute(
        "INSERT INTO partner_outbound_clicks(id,partner_id,product_id,user_id,created_at) "
        "VALUES(?,?,?,?,?)", (_id(), row["partner_id"], row["id"], user["id"], _now()),
    )
    return url


def new_console_session(con, api_key_header):
    """One-hour scoped bearer token, so the browser need not keep the API key."""
    partner = auth_partner(con, api_key_header)
    token = "smp_session_" + secrets.token_urlsafe(36)
    moment = _now()
    con.execute(
        "INSERT INTO partner_console_sessions"
        "(id,partner_id,session_hash,created_at,expires_at) VALUES(?,?,?,?,?)",
        (_id(), partner["id"], _sha(token), moment, moment + 3600),
    )
    return {"session_token": token, "expires_in": 3600}


def auth_console(con, header):
    """Server SDKs may use the long-lived key, browser uses an expiring session."""
    if isinstance(header, str) and header.startswith("Partner smp_live_"):
        return auth_partner(con, header)
    if not isinstance(header, str) or not re.fullmatch(
            r"PartnerSession smp_session_[A-Za-z0-9_-]{35,100}\Z", header):
        raise PartnerError(401, "Войдите в партнёрскую консоль")
    session = con.execute(
        "SELECT p.* FROM partner_console_sessions s "
        "JOIN partner_accounts p ON p.id=s.partner_id "
        "WHERE s.session_hash=? AND s.revoked_at IS NULL "
        "AND s.expires_at>? AND p.active=1",
        (_sha(header[len("PartnerSession "):]), _now()),
    ).fetchone()
    if not session:
        raise PartnerError(401, "Сессия истекла")
    return session


def revoke_console_session(con, header):
    if not isinstance(header, str) or not header.startswith("PartnerSession "):
        return False
    token = header[len("PartnerSession "):]
    if not re.fullmatch(r"smp_session_[A-Za-z0-9_-]{35,100}\Z", token):
        return False
    return con.execute(
        "UPDATE partner_console_sessions SET revoked_at=? "
        "WHERE session_hash=? AND revoked_at IS NULL",
        (_now(), _sha(token)),
    ).rowcount > 0


def rotate_api_key(con, partner_id):
    """Admin-only rotation invalidates all old keys and console sessions atomically."""
    if not isinstance(partner_id, str) or not re.fullmatch(r"[0-9a-f-]{36}\Z", partner_id):
        raise PartnerError(400, "Некорректный идентификатор партнёра")
    from backend.business import transaction
    with transaction(con, lock_scopes=(f"partner:{partner_id}",)):
        existing = con.execute(
            "SELECT id,code FROM partner_accounts WHERE id=? AND active=1",
            (partner_id,),
        ).fetchone()
        if not existing:
            raise PartnerError(404, "Партнёр не найден")
        moment = _now()
        secret = "smp_live_" + secrets.token_urlsafe(36)
        con.execute(
            "UPDATE partner_api_tokens SET revoked_at=? "
            "WHERE partner_id=? AND revoked_at IS NULL", (moment, partner_id)
        )
        con.execute(
            "UPDATE partner_console_sessions SET revoked_at=? "
            "WHERE partner_id=? AND revoked_at IS NULL", (moment, partner_id)
        )
        con.execute(
            "INSERT INTO partner_api_tokens(id,partner_id,token_hash,created_at) "
            "VALUES(?,?,?,?)", (_id(), partner_id, _sha(secret), moment)
        )
    return {"partner": existing["code"], "api_key": secret, "shown_once": True}


def partner_profile(con, account):
    """Read-only non-PII partner profile."""
    domain = con.execute(
        "SELECT status,verified_at FROM partner_domain_verifications WHERE partner_id=? AND domain=?",
        (account["id"], account["allowed_host"]),
    ).fetchone()
    return {"id": account["id"], "code": account["code"], "name": account["name"],
            "domain": account["allowed_host"], "active": bool(account["active"]),
            "domain_status": domain["status"] if domain else "not_started",
            "domain_verified_at": domain["verified_at"] if domain else None,
            "commission_bps": account["commission_bps"], "term_days": account["term_days"],
            "currency": "RUB", "payouts_enabled": False}


def catalog_page(con, account, limit=50, cursor=""):
    """Tenant-isolated, deterministic keyset pagination."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise PartnerError(400, "Размер страницы от 1 до 100")
    if not isinstance(cursor, str) or (cursor and not SKU_RE.fullmatch(cursor)):
        raise PartnerError(400, "Некорректный курсор")
    rows = con.execute(
        "SELECT sku,name,price_kopecks,url,available,updated_at "
        "FROM partner_products WHERE partner_id=? AND sku>? ORDER BY sku LIMIT ?",
        (account["id"], cursor, limit + 1),
    ).fetchall()
    items = rows[:limit]
    return {"items": [dict(row) for row in items],
            "next_cursor": items[-1]["sku"] if len(rows) > limit else None}


def commission_page(con, account, limit=30, cursor=""):
    """Opaque receipt IDs; no customer names, emails or user IDs."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise PartnerError(400, "Размер страницы от 1 до 100")
    stamp, last_id = 2**62, "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz"
    if cursor:
        match = re.fullmatch(r"([0-9]{1,12}):([0-9a-f-]{36})", cursor) if isinstance(cursor, str) else None
        if not match:
            raise PartnerError(400, "Некорректный курсор")
        stamp, last_id = int(match[1]), match[2]
    rows = con.execute(
        "SELECT id,gross_kopecks,commission_kopecks,rate_bps,status,created_at,ready_at "
        "FROM partner_commissions WHERE partner_id=? "
        "AND (created_at<? OR (created_at=? AND id<?)) "
        "ORDER BY created_at DESC,id DESC LIMIT ?",
        (account["id"], stamp, stamp, last_id, limit + 1),
    ).fetchall()
    now = _now()
    page = rows[:limit]
    items = [{
        "receipt_id": row["id"], "gross_kopecks": row["gross_kopecks"],
        "commission_kopecks": row["commission_kopecks"], "rate_bps": row["rate_bps"],
        "status": "reversed" if row["status"] == "reversed" else (
            "held" if now < row["ready_at"] else "cleared_unpaid"),
        "created_at": row["created_at"], "ready_at": row["ready_at"],
    } for row in page]
    return {"items": items,
            "next_cursor": f"{page[-1]['created_at']}:{page[-1]['id']}" if len(rows) > limit else None,
            "payouts_enabled": False}


def set_partner_active(con, partner_id, active):
    """Administrator-only pause. No payments or payouts are executed."""
    if not isinstance(partner_id, str) or not re.fullmatch(r"[0-9a-f-]{36}\Z", partner_id):
        raise PartnerError(400, "Некорректный идентификатор")
    if type(active) is not bool:
        raise PartnerError(400, "Ожидается active: true/false")
    from backend.business import transaction
    with transaction(con, lock_scopes=(f"partner:{partner_id}",)):
        changed = con.execute("UPDATE partner_accounts SET active=? WHERE id=?",
                              (int(active), partner_id)).rowcount
        if not changed:
            raise PartnerError(404, "Партнёр не найден")
        if not active:
            con.execute("UPDATE partner_console_sessions SET revoked_at=? "
                        "WHERE partner_id=? AND revoked_at IS NULL", (_now(), partner_id))
    return {"id": partner_id, "active": active, "payouts_enabled": False}


def reconcile_confirmed_payments(con, limit=100):
    """Admin-only bounded repair pass; only real confirmed paid subscriptions.

    Safe to re-run: unique payment_id and ON CONFLICT guarantee idempotency.
    This never issues a payout, edits subscription rights, or contacts YooKassa.
    """
    if type(limit) is not int or not 1 <= limit <= 100:
        raise PartnerError(400, "Лимит сверки от 1 до 100")
    candidates = con.execute(
        "SELECT p.* FROM payments p "
        "JOIN billing_intents b ON b.payment_id=p.id "
        "JOIN partner_attributions a ON a.user_id=p.user_id "
        "WHERE p.status='succeeded' AND b.is_test=0 "
        "AND (p.plan LIKE 'pro_%' OR p.plan LIKE 'team_%') "
        "AND NOT EXISTS (SELECT 1 FROM partner_commissions c WHERE c.payment_id=p.id) "
        "AND NOT EXISTS (SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded') "
        "ORDER BY p.activated_at ASC,p.id ASC LIMIT ?",
        (limit,),
    ).fetchall()
    created = sum(bool(record_subscription_payment(con, row)) for row in candidates)
    return {"scanned": len(candidates), "created": created, "payouts_enabled": False}
