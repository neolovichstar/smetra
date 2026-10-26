"""Bounded retention for expired authentication artifacts and old rate-limit keys.

No quotes, estimates, billing, audit, jobs or active tokens are deleted.
Only the Vercel CRON_SECRET holder may run this endpoint.
"""
import hmac
import os
import time

# Keep expired login links for a short diagnostic buffer, but never indefinitely.
RETENTION = (
    ("email_login_challenges", "id", "expires_at", 2 * 86400),
    ("email_tokens", "id", "expires_at", 7 * 86400),
    ("oauth_states", "state_hash", "expires_at", 2 * 86400),
    ("oauth_tickets", "ticket_hash", "expires_at", 2 * 86400),
    ("sessions", "id", "expires_at", 7 * 86400),
    # Partner referrals count for 30 days; delete after expiry + 14-day buffer.
    ("partner_clicks", "id", "expires_at", 14 * 86400),
    ("partner_console_sessions", "id", "expires_at", 7 * 86400),
    ("partner_site_events", "id", "created_at", 180 * 86400),
    ("partner_outbound_clicks", "id", "created_at", 180 * 86400),
    # The same table also holds monthly AI quota counters. Do NOT delete
    # current or recent counters; only keys untouched for four months.
    ("rate_limits", "key", "started", 120 * 86400),
)

def authenticate(handler, error_class=None):
    if error_class is None:
        from backend.app import ApiError
        error_class = ApiError
    secret = os.getenv("CRON_SECRET", "")
    auth = handler.headers.get("Authorization", "")
    if len(secret) < 32 or not hmac.compare_digest(auth, "Bearer " + secret):
        raise error_class(401, "Нет доступа")


def cleanup(con, *, now=None, per_table=4000):
    """Run predictable batches using already indexed expiration columns.

    A single invocation deletes at most 6 x 4000 records. Batches use
    subselects to support both PostgreSQL and local SQLite.
    """
    timestamp = int(time.time()) if now is None else int(now)
    limit = max(1, min(int(per_table), 4000))
    counts = {}
    for table, primary_key, column, grace_period in RETENTION:
        # Referenced clicks are audit evidence for first-touch attribution.
        # Deleting them would violate partner_attributions.click_id foreign keys
        # and abort the entire maintenance job.
        extra = (
            " AND NOT EXISTS (SELECT 1 FROM partner_attributions a "
            "WHERE a.click_id=partner_clicks.id)"
            if table == "partner_clicks" else ""
        )
        sql = (
            f"DELETE FROM {table} WHERE {primary_key} IN "
            f"(SELECT {primary_key} FROM {table} "
            f"WHERE {column}<?{extra} ORDER BY {column},{primary_key} LIMIT ?)"
        )
        affected = con.execute(sql, (timestamp - grace_period, limit))
        counts[table] = max(0, affected.rowcount)
    return {"ok": True, "removed": counts, "batch_limit": limit}


def run(handler, con):
    authenticate(handler)
    report = cleanup(con)
    # Backend-only reconciliation of provider-confirmed subscription purchases.
    # It cannot execute a partner payout and is safe on duplicate cron runs.
    from backend.partner_platform import reconcile_confirmed_payments
    report["partner_reconciliation"] = reconcile_confirmed_payments(con, limit=100)
    return report
