"""Partner domain proof and privacy-preserving conversion analytics.

Untrusted partner domains cannot cause arbitrary server-side HTTP requests:
DNS proof uses a fixed DNS-over-HTTPS resolver; HTML proof connects only to
a pre-validated public IP with TLS hostname verification and no redirects.
"""
import datetime as dt
import html.parser
import http.client
import ipaddress
import json
import re
import secrets
import socket
import ssl
import time
import urllib.parse
import urllib.request

from backend import partner_platform as partner

EVENT_TYPES = frozenset({"widget_impression", "widget_click", "material_order_reported"})
KEY_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{12,100}\Z")
VALID_METHODS = ("dns", "meta")
VERIFICATION_TTL = 90 * 86400  # Domain ownership is not permanent.


def _moment():
    return int(time.time())


def domain_status(con, account):
    row = con.execute(
        "SELECT domain,token,status,method,verified_at,last_checked_at "
        "FROM partner_domain_verifications WHERE partner_id=?", (account["id"],)
    ).fetchone()
    if row:
        value = dict(row)
        if (value["status"] == "verified" and
                (not value["verified_at"] or value["verified_at"] <= _moment() - VERIFICATION_TTL)):
            value["status"] = "expired"
        return value
    return {
        "domain": account["allowed_host"], "status": "not_started",
        "method": None, "verified_at": None, "last_checked_at": None,
    }


def begin_verification(con, account, method="dns"):
    if method not in VALID_METHODS:
        raise partner.PartnerError(400, "Способ проверки: dns или meta")
    existing = domain_status(con, account)
    if existing["status"] == "verified":
        return existing
    token = "smetra-verify-" + secrets.token_hex(24)
    moment = _moment()
    con.execute(
        "INSERT INTO partner_domain_verifications "
        "(partner_id,domain,token,status,method,verified_at,last_checked_at,created_at) "
        "VALUES(?,?,?,'pending',?,NULL,NULL,?) "
        "ON CONFLICT(partner_id) DO UPDATE SET token=excluded.token,"
        "status='pending',method=excluded.method,verified_at=NULL,last_checked_at=NULL",
        (account["id"], account["allowed_host"], token, method, moment),
    )
    return domain_status(con, account)


def _verify_dns(host, token):
    # No user-controlled URL: only a fixed resolver over TLS, bounded payload.
    lookup = "_smetra-verification." + host
    url = "https://cloudflare-dns.com/dns-query?" + urllib.parse.urlencode(
        {"name": lookup, "type": "TXT"}
    )
    request = urllib.request.Request(
        url, headers={"Accept": "application/dns-json", "User-Agent": "SmetraPartnerVerification/1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            if response.status != 200:
                return False
            document = json.loads(response.read(32769))
    except (OSError, ValueError, TimeoutError) as err:
        raise partner.PartnerError(503, "DNS-проверка временно недоступна") from err
    if document.get("Status") != 0 or not isinstance(document.get("Answer", []), list):
        return False
    for row in document.get("Answer", [])[:50]:
        if not isinstance(row, dict):
            continue
        if str(row.get("name", "")).lower().rstrip(".") != lookup:
            continue
        if row.get("type") != 16:
            continue
        record = row.get("data", "")
        if not isinstance(record, str):
            continue
        try:
            record = json.loads(record)  # DoH TXT strings are JSON-quoted.
        except ValueError:
            pass
        if record == token:
            return True
    return False


class _MetaChecker(html.parser.HTMLParser):
    def __init__(self, token):
        super().__init__(convert_charrefs=True)
        self.expected = token
        self.matched = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta":
            return
        attributes = {k.lower(): v for k, v in attrs if k}
        if (attributes.get("name", "").lower() == "smetra-domain-verification"
                and attributes.get("content") == self.expected):
            self.matched = True


def _verify_meta(host, token):
    # Pin the approved public IP for the TCP connection. This prevents DNS
    # rebinding between validation and connection and rejects loopback/private IPs.
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as err:
        raise partner.PartnerError(503, "Домен пока не разрешается в DNS") from err
    allowed = []
    for address in addresses[:16]:
        ip = address[4][0]
        if not ipaddress.ip_address(ip).is_global:
            raise partner.PartnerError(400, "Домен указывает на непубличный адрес")
        if ip not in allowed:
            allowed.append(ip)
    if not allowed:
        return False
    try:
        with socket.create_connection((allowed[0], 443), timeout=4) as sock:
            with ssl.create_default_context().wrap_socket(sock, server_hostname=host) as tls:
                tls.settimeout(4)
                tls.sendall(
                    ("GET / HTTP/1.0\r\nHost: " + host +
                     "\r\nAccept: text/html\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n"
                    ).encode("ascii")
                )
                response = http.client.HTTPResponse(tls)
                response.begin()
                if response.status != 200:
                    return False  # Never follow redirects.
                if not response.getheader("Content-Type", "").lower().startswith("text/html"):
                    return False
                data = response.read(65537)
    except (OSError, ssl.SSLError, http.client.HTTPException) as err:
        raise partner.PartnerError(503, "HTTPS-проверка временно недоступна") from err
    if len(data) > 65536:
        return False
    parser = _MetaChecker(token)
    parser.feed(data.decode("utf-8", "replace"))
    return parser.matched


def verify_domain(con, account):
    row = domain_status(con, account)
    if row["status"] == "not_started":
        raise partner.PartnerError(409, "Сначала создайте проверку домена")
    method = row["method"]
    if method not in VALID_METHODS:
        raise partner.PartnerError(409, "Неизвестный способ проверки")
    valid = (_verify_dns(row["domain"], row["token"]) if method == "dns"
             else _verify_meta(row["domain"], row["token"]))
    moment = _moment()
    con.execute(
        "UPDATE partner_domain_verifications "
        "SET status=?,verified_at=CASE WHEN ?=1 THEN coalesce(verified_at,?) ELSE verified_at END,"
        "last_checked_at=? WHERE partner_id=?",
        ("verified" if valid else "pending", int(valid), moment, moment, account["id"]),
    )
    return domain_status(con, account)


def require_verified(con, account):
    row = con.execute(
        "SELECT 1 FROM partner_domain_verifications WHERE partner_id=? "
        "AND domain=? AND status='verified' AND verified_at>?",
        (account["id"], account["allowed_host"], _moment() - VERIFICATION_TTL),
    ).fetchone()
    if not row:
        raise partner.PartnerError(403, "Сначала подтвердите домен партнёра")


def report_event(con, account, data):
    """Only partner server credentials may submit *unverified* merchant events."""
    require_verified(con, account)
    if not isinstance(data, dict) or set(data) - {"event_key", "event_type", "amount_kopecks"}:
        raise partner.PartnerError(400, "Недопустимые поля события")
    key, kind = data.get("event_key"), data.get("event_type")
    if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key) or kind not in EVENT_TYPES:
        raise partner.PartnerError(400, "Некорректное событие")
    amount = data.get("amount_kopecks", 0)
    if type(amount) is not int or not 0 <= amount <= 100_000_000_000:
        raise partner.PartnerError(400, "Некорректная сумма")
    if (kind == "material_order_reported") != (amount > 0):
        raise partner.PartnerError(400, "Сумма разрешена только для заказа")
    con.execute(
        "INSERT INTO partner_site_events"
        "(id,partner_id,event_key,event_type,amount_kopecks,created_at)"
        "VALUES(?,?,?,?,?,?) ON CONFLICT(partner_id,event_key) DO NOTHING",
        (partner._id(), account["id"], key, kind, amount, _moment()),
    )
    recorded = con.execute(
        "SELECT event_type,amount_kopecks FROM partner_site_events "
        "WHERE partner_id=? AND event_key=?", (account["id"], key)
    ).fetchone()
    if not recorded or recorded["event_type"] != kind or int(recorded["amount_kopecks"]) != amount:
        raise partner.PartnerError(409, "Ключ события уже использован для других данных")
    return {"accepted": True, "trusted": False, "used_for_commissions": False}


def _daily(con, table, partner_id, since, filter_sql=""):
    # All table names and optional clauses are static server constants.
    query = (
        f"SELECT created_at/86400 AS day,count(*) AS count FROM {table} "
        f"WHERE partner_id=? AND created_at>=? {filter_sql} "
        "GROUP BY created_at/86400 ORDER BY day"
    )
    return {int(r["day"]): int(r["count"]) for r in con.execute(query, (partner_id, since)).fetchall()}


def analytics(con, account, days=30):
    if type(days) is not int or days not in (7, 30, 90):
        raise partner.PartnerError(400, "Период: 7, 30 или 90 дней")
    now = _moment()
    start_day = now // 86400 - days + 1
    since = start_day * 86400
    pid = account["id"]
    visits = _daily(con, "partner_clicks", pid, since)
    registrations = _daily(con, "partner_attributions", pid, since)
    paid = _daily(con, "partner_commissions", pid, since)
    materials = _daily(con, "partner_outbound_clicks", pid, since)
    impressions = _daily(con, "partner_site_events", pid, since,
                         "AND event_type='widget_impression'")
    reported_orders = _daily(con, "partner_site_events", pid, since,
                             "AND event_type='material_order_reported'")
    metric = con.execute(
        "SELECT count(*) AS payments,COUNT(DISTINCT user_id) AS paying_accounts,"
        "coalesce(sum(CASE WHEN status='pending' THEN gross_kopecks ELSE 0 END),0) AS gross_kopecks,"
        "coalesce(sum(CASE WHEN status='pending' THEN commission_kopecks ELSE 0 END),0) AS commission_kopecks,"
        "coalesce(sum(CASE WHEN status='reversed' THEN commission_kopecks ELSE 0 END),0) AS reversed_kopecks "
        "FROM partner_commissions WHERE partner_id=? AND created_at>=?",
        (pid, since),
    ).fetchone()
    events = con.execute(
        "SELECT event_type,count(*) AS count,coalesce(sum(amount_kopecks),0) AS amount_kopecks "
        "FROM partner_site_events WHERE partner_id=? AND created_at>=? GROUP BY event_type",
        (pid, since),
    ).fetchall()
    reported = {x["event_type"]: {"count": x["count"], "amount_kopecks": x["amount_kopecks"]}
                for x in events}
    timeline = [{
        "date": dt.datetime.fromtimestamp(day * 86400, dt.timezone.utc).strftime("%Y-%m-%d"),
        "visits": visits.get(day, 0),
        "registrations": registrations.get(day, 0),
        "payments": paid.get(day, 0),
        "materials_clicks": materials.get(day, 0),
        "reported_impressions": impressions.get(day, 0),
        "reported_orders": reported_orders.get(day, 0),
    } for day in range(start_day, start_day + days)]
    return {
        "days": days, "timezone": "UTC", "partner": account["code"],
        "visits": sum(visits.values()),
        "registrations": sum(registrations.values()),
        "verified_subscription_payments": dict(metric),
        "outbound_material_clicks": sum(materials.values()),
        "merchant_reported": reported,
        "timeline": timeline,
        "payouts_enabled": False,
        "note": "Merchant site events and orders are self-reported and are not proof of payment.",
    }
