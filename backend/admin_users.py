"""Administrator view and controls for one account.

Every change is a deliberate admin action: validated here, written in the
caller's transaction and recorded in the audit log with the admin's reason.
Payments are read-only: refunds and provider state stay with the billing flow.
"""
from backend import ai_tokens
from backend.business import DomainError, stamp
from backend.entitlements import PLAN_TIER

ADMIN_PLANS = {"free": "Старт", "pro_solo": "PRO Solo", "pro_plus": "PRO Plus", "team": "Team"}
MAX_PLAN_DAYS = 3660


class _Viewer:
    """Minimal service-like object so token balances use the same rules as chat."""
    def __init__(self, con, user, workspace_id):
        self.con, self.user, self.wid = con, user, workspace_id


def _personal_workspace(con, user):
    from backend.business import ensure_workspace
    return ensure_workspace(con, user)


def detail(con, user_id):
    user = con.execute("SELECT * FROM users WHERE id=? AND deleted_at IS NULL", (user_id,)).fetchone()
    if not user:
        raise DomainError(404, "Пользователь не найден")
    personal = _personal_workspace(con, user)
    workspaces = [dict(row) for row in con.execute(
        "SELECT id,name,plan,subscription_status,entitlement_until,created_at,"
        "(SELECT count(*) FROM workspace_members m WHERE m.workspace_id=w.id) AS members "
        "FROM workspaces w WHERE owner_id=? ORDER BY created_at LIMIT 20", (user_id,)
    )]
    for workspace in workspaces:
        workspace["tier"] = PLAN_TIER.get(str(workspace["plan"] or "free"), "starter")
        workspace["personal"] = workspace["id"] == personal
    tokens = ai_tokens.balance(_Viewer(con, user, personal))
    tokens.pop("key", None)
    ledger = [dict(row) for row in con.execute(
        "SELECT l.id,l.bucket,l.delta,l.reason,l.note,l.created_at,u.email AS actor_email "
        "FROM ai_token_ledger l LEFT JOIN users u ON u.id=l.actor_id WHERE l.user_id=? "
        "ORDER BY l.created_at DESC,l.id DESC LIMIT 50", (user_id,)
    )]
    payments = [dict(row) for row in con.execute(
        "SELECT p.id,p.plan,p.amount_kopecks,p.status,p.created_at,p.activated_at,"
        "EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded') AS refunded "
        "FROM payments p WHERE p.user_id=? ORDER BY p.created_at DESC LIMIT 30", (user_id,)
    )]
    audit_rows = [dict(row) for row in con.execute(
        "SELECT a.action,a.detail,a.created_at,u.email AS actor_email FROM audit a "
        "LEFT JOIN users u ON u.id=a.actor_id WHERE a.target=? ORDER BY a.created_at DESC LIMIT 40", (user_id,)
    )]
    counts = {
        "sessions": con.execute("SELECT count(*) FROM sessions WHERE user_id=? AND expires_at>?", (user_id, stamp())).fetchone()[0],
        "quotes": con.execute(
            "SELECT count(*) FROM quotes q JOIN workspaces w ON w.id=q.workspace_id WHERE w.owner_id=?", (user_id,)
        ).fetchone()[0],
        "support": con.execute(
            "SELECT count(*) FROM chat_conversations WHERE kind='support' AND created_by=?", (user_id,)
        ).fetchone()[0],
    }
    return {
        "user": {
            "id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"],
            "blocked": bool(user["blocked"]), "plan": user["plan"],
            "entitlement_until": int(user["entitlement_until"] or 0), "created_at": user["created_at"],
            "email_verified": bool(user["email_verified"]) if "email_verified" in user.keys() else None,
        },
        "workspaces": workspaces,
        "tokens": tokens,
        "ledger": ledger,
        "payments": payments,
        "audit": audit_rows,
        "counts": counts,
        "plans": ADMIN_PLANS,
    }


def _reason(data):
    reason = data.get("reason", "")
    if not isinstance(reason, str) or len(reason.strip()) > 200:
        raise DomainError(400, "Причина — до 200 символов")
    return reason.strip()


def act(con, admin, user_id, data, audit):
    """Apply one admin action. Returns a short machine-readable result."""
    action = data.get("action")
    reason = _reason(data)
    user = con.execute("SELECT * FROM users WHERE id=? AND deleted_at IS NULL", (user_id,)).fetchone()
    if not user:
        raise DomainError(404, "Пользователь не найден")
    if action in ("block", "unblock"):
        if user_id == admin["id"] and action == "block":
            raise DomainError(409, "Нельзя заблокировать себя")
        con.execute("UPDATE users SET blocked=? WHERE id=?", (int(action == "block"), user_id))
        if action == "block":
            con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        audit(con, admin["id"], "admin." + action, user_id, reason)
        return {"ok": True}
    if action == "sessions_revoke":
        removed = con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,)).rowcount
        audit(con, admin["id"], "admin.sessions_revoke", user_id, reason)
        return {"ok": True, "revoked": removed}
    if action == "role":
        role = data.get("role")
        if role not in ("user", "admin"):
            raise DomainError(400, "Роль: user или admin")
        if user_id == admin["id"] and role != "admin":
            raise DomainError(409, "Нельзя снять права администратора с себя")
        con.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        audit(con, admin["id"], "admin.role." + role, user_id, reason)
        return {"ok": True}
    if action == "tokens":
        delta = data.get("delta")
        balance = ai_tokens.adjust(con, user_id, delta, admin["id"], reason)
        audit(con, admin["id"], "admin.tokens", user_id, f"{delta:+d}" + (" · " + reason if reason else ""))
        return {"ok": True, "wallet": balance}
    if action == "set_plan":
        plan = data.get("plan")
        if plan not in ADMIN_PLANS:
            raise DomainError(400, "Неизвестный тариф")
        workspace_id = str(data.get("workspace_id") or "") or _personal_workspace(con, user)
        workspace = con.execute("SELECT id FROM workspaces WHERE id=? AND owner_id=?", (workspace_id, user_id)).fetchone()
        if not workspace:
            raise DomainError(404, "Пространство не принадлежит пользователю")
        if plan == "free":
            until, status = 0, ""
        else:
            days = data.get("days")
            if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= MAX_PLAN_DAYS:
                raise DomainError(400, "Срок — от 1 до 3660 дней")
            until, status = stamp() + days * 86400, "active"
        con.execute(
            "UPDATE workspaces SET plan=?,subscription_status=?,entitlement_until=? WHERE id=?",
            (plan, status, until, workspace_id),
        )
        if workspace_id == _personal_workspace(con, user):
            # The personal workspace mirrors the account-level fields older screens read.
            con.execute(
                "UPDATE users SET plan=?,entitlement_until=? WHERE id=?",
                ("free" if plan == "free" else "pro", until, user_id),
            )
        audit(con, admin["id"], "admin.set_plan." + plan, user_id, (f"{workspace_id} · до {until}" if until else workspace_id) + (" · " + reason if reason else ""))
        return {"ok": True, "entitlement_until": until}
    # Request-era shortcuts kept for older admin screens.
    if action == "grant":
        # Computed here: scalar max(a,b) exists in SQLite but not in PostgreSQL.
        until = max(int(user["entitlement_until"] or 0), stamp()) + 31 * 86400
        con.execute("UPDATE users SET plan='pro',entitlement_until=? WHERE id=?", (until, user_id))
        audit(con, admin["id"], "admin.grant", user_id, reason)
        return {"ok": True}
    if action == "revoke":
        con.execute("UPDATE users SET plan='free',entitlement_until=0 WHERE id=?", (user_id,))
        audit(con, admin["id"], "admin.revoke", user_id, reason)
        return {"ok": True}
    raise DomainError(400, "Неизвестное действие")
