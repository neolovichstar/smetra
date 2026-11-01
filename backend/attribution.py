"""First-touch marketing attribution.

The browser remembers the first campaign link (UTM tags) or referring site a visitor came
from and hands it over once, right after sign-in. Only new accounts are attributed, so an
old customer clicking an ad later does not count as acquired by it. Nothing here is personal
data beyond the link to the account; the referrer is reduced to its host name.
"""
import re

from backend.business import DomainError as ApiError

FIELDS = ("source", "medium", "campaign", "content", "term")
NEW_ACCOUNT_WINDOW = 14 * 86400
HOST_RE = re.compile(r"(?=.{1,253}\Z)([a-z0-9-]{1,63}\.)+[a-z]{2,63}\Z")
TAG_RE = re.compile(r"[\w .:/+@%-]{1,100}\Z", re.UNICODE)
SEARCH = ("yandex.", "ya.ru", "google.", "bing.com", "duckduckgo.com", "mail.ru", "rambler.ru")
SOCIAL = ("vk.com", "t.me", "telegram.", "ok.ru", "dzen.ru", "youtube.com", "rutube.ru", "pikabu.ru")


def _tag(value):
    text = str(value or "").strip().lower()
    return text if text and TAG_RE.fullmatch(text) else ""


def clean(data):
    """Validated attribution or None when the payload carries nothing usable."""
    if not isinstance(data, dict):
        raise ApiError(400, "Некорректные данные")
    values = {field: _tag(data.get(field)) for field in FIELDS}
    host = str(data.get("referrer") or "").strip().lower().removeprefix("www.")
    values["referrer_host"] = host if HOST_RE.fullmatch(host) and not host.endswith("smetra.online") else ""
    path = str(data.get("landing") or "")
    values["landing_path"] = path if path.startswith("/") and len(path) <= 200 and re.fullmatch(r"/[\w./-]*", path) else ""
    seen = data.get("first_seen_at")
    values["first_seen_at"] = int(seen) if isinstance(seen, (int, float)) and seen > 0 else 0
    if not values["source"] and not values["referrer_host"]:
        return None
    return values


def capture(con, user, data, moment):
    """Store the first touch for an account created recently; later calls change nothing."""
    values = clean(data)
    if values is None or moment - int(user["created_at"]) > NEW_ACCOUNT_WINDOW:
        return False
    first_seen = values["first_seen_at"] or moment
    # A first touch cannot be later than now or long before the account existed.
    first_seen = min(moment, max(first_seen, int(user["created_at"]) - 90 * 86400))
    cursor = con.execute(
        "INSERT INTO user_attribution(user_id,source,medium,campaign,content,term,referrer_host,landing_path,first_seen_at,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO NOTHING",
        (user["id"], values["source"], values["medium"], values["campaign"], values["content"], values["term"],
         values["referrer_host"], values["landing_path"], first_seen, moment),
    )
    return bool(getattr(cursor, "rowcount", 1))


def _matches(host, names):
    return any(("." + host).find("." + name) >= 0 for name in names)


def channel(source, medium, host):
    """A readable channel for the admin table."""
    if source:
        return source + (" / " + medium if medium else "")
    if _matches(host, SEARCH):
        return "поиск: " + host
    if _matches(host, SOCIAL):
        return "соцсети: " + host
    return "сайт: " + host


def summary(con, moment, days=30):
    """Signups, activation and paying accounts by acquisition channel for recent sign-ups."""
    start = moment - days * 86400
    valid = ("p.status='succeeded' AND b.is_test=0 AND NOT EXISTS(SELECT 1 FROM refunds r "
             "WHERE r.payment_id=p.id AND r.status='succeeded')")
    rows = con.execute(
        "SELECT coalesce(a.source,'') AS source, coalesce(a.medium,'') AS medium, coalesce(a.campaign,'') AS campaign, "
        "coalesce(a.referrer_host,'') AS referrer_host, count(*) AS signups, "
        "sum(CASE WHEN EXISTS(SELECT 1 FROM growth_events e WHERE e.user_id=u.id AND e.name='activated') THEN 1 ELSE 0 END) AS activated, "
        f"sum(CASE WHEN EXISTS(SELECT 1 FROM payments p JOIN billing_intents b ON b.payment_id=p.id WHERE p.user_id=u.id AND {valid}) THEN 1 ELSE 0 END) AS paid "
        "FROM users u LEFT JOIN user_attribution a ON a.user_id=u.id "
        "WHERE u.deleted_at IS NULL AND u.created_at>=? "
        "GROUP BY coalesce(a.source,''), coalesce(a.medium,''), coalesce(a.campaign,''), coalesce(a.referrer_host,'') "
        "ORDER BY count(*) DESC LIMIT 100",
        (start,),
    ).fetchall()
    items = []
    for row in rows:
        known = row["source"] or row["referrer_host"]
        items.append({
            "channel": channel(row["source"], row["medium"], row["referrer_host"]) if known else "прямые и без меток",
            "campaign": row["campaign"], "signups": row["signups"],
            "activated": row["activated"] or 0, "paid": row["paid"] or 0,
        })
    return {"days": days, "items": items}
