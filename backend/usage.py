"""What the account has used against its plan: one read-only summary.

Every limit comes from the same server code that enforces it (the token
allowance, the free quote limit, storage and seats), so the bars in the
interface can never disagree with what the server will actually allow.
"""


def meter(used, limit):
    """Used and left against a limit; unlimited when there is no limit."""
    used = max(0, int(used or 0))
    if limit is None:
        return {"used": used, "limit": None, "remaining": None, "remaining_pct": None}
    limit = max(0, int(limit))
    remaining = max(0, limit - used)
    # Whole percent left, rounded down so «100%» means nothing was used.
    pct = remaining * 100 // limit if limit else 0
    return {"used": used, "limit": limit, "remaining": remaining, "remaining_pct": pct}


def summary(service):
    from backend import ai_tokens
    from backend.attachments import workspace_storage_limit
    from backend.entitlements import workspace_feature_access
    from backend.business import stamp
    from backend.plan_catalog import workspace_summary, starter_quote_limit

    con, wid, now = service.con, service.wid, stamp()
    plan = workspace_summary(con, wid, now)
    tokens = ai_tokens.balance(service)

    from backend.plan_catalog import quota_owner
    owner = quota_owner(service)
    created = con.execute(
        "SELECT count(*) FROM events WHERE user_id=? AND name='quote_created'", (owner["id"],)
    ).fetchone()[0]
    # Same rule as quote creation: a paid workspace or a personal PRO lifts the limit.
    paid = workspace_feature_access(con, wid, "clean_export", now)["allowed"] or (owner["entitlement_until"] or 0) > now
    free_quotes = starter_quote_limit(owner) if plan["tier"] == "starter" else plan.get("free_quotes")

    storage_used = con.execute("SELECT coalesce(sum(size),0) FROM files WHERE workspace_id=?", (wid,)).fetchone()[0]
    seats_used = con.execute("SELECT count(*) FROM workspace_members WHERE workspace_id=?", (wid,)).fetchone()[0]

    def count(table):
        return con.execute(f"SELECT count(*) FROM {table} WHERE workspace_id=?", (wid,)).fetchone()[0]

    return 200, {
        "plan": {"tier": plan["tier"], "name": plan["name"], "until": plan.get("entitled_until") or None},
        "tokens": {
            **meter(tokens["monthly_used"], tokens["monthly_limit"]),
            "wallet": tokens["wallet"],
            "period": tokens["period"],
            "resets_at": tokens["resets_at"],
        },
        "quotes": meter(created, None if paid or free_quotes is None else free_quotes),
        "storage": meter(storage_used, workspace_storage_limit(service)),
        "seats": meter(seats_used, plan.get("seats")),
        "history": history(con, service.user["id"], now),
        "records": {
            "quotes": count("quotes"),
            "clients": count("clients"),
            "projects": count("projects"),
            "files": count("files"),
        },
    }


def history(con, user_id, now):
    """Bounded personal token audit, without prompts or other users' entries."""
    cutoff = now - 30 * 86400
    totals = dict(con.execute(
        "SELECT coalesce(sum(CASE WHEN delta<0 THEN -delta ELSE 0 END),0) AS spent,"
        "coalesce(sum(CASE WHEN delta>0 THEN delta ELSE 0 END),0) AS added,"
        "count(CASE WHEN delta<0 THEN 1 END) AS debits "
        "FROM ai_token_ledger WHERE user_id=? AND created_at>=? AND created_at<=?",
        (user_id, cutoff, now),
    ).fetchone())
    entries = [dict(row) for row in con.execute(
        "SELECT id,bucket,delta,reason,created_at FROM ai_token_ledger "
        "WHERE user_id=? AND created_at<=? ORDER BY created_at DESC,id DESC LIMIT 20", (user_id, now)
    )]
    return {**totals, 'days': 30, 'entries': entries}
