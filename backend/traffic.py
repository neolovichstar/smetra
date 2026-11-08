"""Small first-party audience counters; no IP, email, user agent or raw visitor IDs.

Counting starts when this feature is enabled, and reports only aggregate data
to admins. A random browser identifier is irreversibly hashed before storage.
"""
import datetime as dt
import hashlib
import time
import uuid


def ensure_schema(con):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS site_visits(
            id TEXT PRIMARY KEY,
            day INTEGER NOT NULL,
            visitor_hash TEXT NOT NULL,
            page TEXT NOT NULL CHECK(page IN ('landing','app')),
            views INTEGER NOT NULL DEFAULT 1 CHECK(views BETWEEN 1 AND 100),
            created_at INTEGER NOT NULL,
            UNIQUE(day,visitor_hash,page)
        );
        CREATE INDEX IF NOT EXISTS idx_site_visits_created ON site_visits(created_at);
        CREATE INDEX IF NOT EXISTS idx_site_visits_day ON site_visits(day);
    """)


def record(con, visitor_id, page, *, timestamp=None):
    """Count one visitor once per page and day; bound repeated page views."""
    if page not in ("landing", "app"):
        raise ValueError("Unknown tracked page")
    # Only UUID4 generated in the browser; no raw identifier is persisted.
    identifier = uuid.UUID(visitor_id)
    if identifier.version != 4 or str(identifier) != visitor_id:
        raise ValueError("Invalid visitor ID")
    moment = int(time.time()) if timestamp is None else int(timestamp)
    day = moment // 86400
    digest = hashlib.sha256(b"smetra-first-party-traffic-v1:" + identifier.bytes).hexdigest()
    con.execute(
        "INSERT INTO site_visits(id,day,visitor_hash,page,views,created_at) "
        "VALUES(?,?,?,?,1,?) ON CONFLICT(day,visitor_hash,page) DO UPDATE SET "
        "views=CASE WHEN site_visits.views<100 THEN site_visits.views+1 ELSE 100 END",
        (str(uuid.uuid4()), day, digest, page, moment),
    )


def overview(con, *, timestamp=None):
    moment = int(time.time()) if timestamp is None else int(timestamp)
    today = moment // 86400

    def unique(since):
        row = con.execute(
            "SELECT count(DISTINCT visitor_hash) FROM site_visits WHERE day>=? AND day<=?",
            (today-since+1, today),
        ).fetchone()
        return int(row[0])

    rows = con.execute(
        "SELECT day, count(DISTINCT visitor_hash) AS visitors, "
        "coalesce(sum(views),0) AS views FROM site_visits "
        "WHERE day>=? AND day<=? GROUP BY day ORDER BY day",
        (today-29, today),
    ).fetchall()
    by_day = {int(row["day"]): row for row in rows}
    daily = [
        {
            "day": dt.datetime.fromtimestamp(day*86400, dt.timezone.utc).strftime("%Y-%m-%d"),
            "visitors": int(by_day[day]["visitors"]) if day in by_day else 0,
            "views": int(by_day[day]["views"]) if day in by_day else 0,
        }
        for day in range(today-29, today+1)
    ]
    pages = [
        {"page": row["page"], "visitors": int(row["visitors"]), "views": int(row["views"])}
        for row in con.execute(
            "SELECT page,count(DISTINCT visitor_hash) AS visitors,"
            "coalesce(sum(views),0) AS views FROM site_visits "
            "WHERE day>=? AND day<=? GROUP BY page",
            (today-29,today),
        ).fetchall()
    ]
    oldest = con.execute("SELECT min(created_at) FROM site_visits").fetchone()[0]
    return {
        "today": unique(1), "week": unique(7), "month": unique(30),
        "views_30d": sum(day["views"] for day in daily),
        "daily": daily, "pages": pages,
        "collecting_since": int(oldest) if oldest else None,
        "timezone": "UTC",
    }
