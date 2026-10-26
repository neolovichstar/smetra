"""Per-user private vault + opt-in shared workspace file rules.

Use this module from EVERY file list, direct file lookup, and assistant tool.
The RLS migration provides a second independent gate on PostgreSQL.
"""
import uuid


def private_file(service, row):
    return row["vault_scope"] == "personal"


def can_view_file(service, row):
    return (
        row["workspace_id"] == service.wid
        and (row["vault_scope"] == "workspace"
             or row["owner_user_id"] == service.user["id"])
    )


def require_file(service, row):
    if not can_view_file(service, row):
        from backend.business import DomainError

        raise DomainError(404, "Файл не найден")
    return row


def can_write_file(service, row):
    if private_file(service, row):
        return can_view_file(service, row)
    return service.role in ("owner", "admin", "manager", "member")


def require_file_write(service, row):
    from backend.business import DomainError

    require_file(service, row)
    if not can_write_file(service, row):
        raise DomainError(403, "Недостаточно прав на изменение файла")


def file_access_filter(service, alias=""):
    """Return a parameterized predicate; caller owns the workspace condition."""
    prefix = (alias + ".") if alias else ""
    return (
        "(" + prefix + "vault_scope='workspace' OR " +
        prefix + "owner_user_id=?)",
        (service.user["id"],)
    )


def _storage_con(service):
    # A trusted authenticated connection; runtime RLS intentionally cannot
    # aggregate private files from the user's other workspaces.
    return getattr(service, "global_con", None) or service.con


def _private_stats(service):
    if getattr(service.con, "is_postgres", False):
        # SECURITY DEFINER function resolves the authenticated user from the
        # request session. The scoped RLS connection cannot directly sum
        # personal files from other workspaces of the same account.
        schema = service.con.schema
        row = service.con.execute(
            f"SELECT used_bytes,quota_bytes FROM {schema}.vault_personal_stats()"
        ).fetchone()
        return (int(row["used_bytes"]), int(row["quota_bytes"]))
    return None


def personal_storage_used(service):
    stats = _private_stats(service)
    if stats is not None:
        return stats[0]
    row = _storage_con(service).execute(
        "SELECT coalesce(sum(size),0) FROM files "
        "WHERE owner_user_id=? AND vault_scope='personal'",
        (service.user["id"],),
    ).fetchone()
    return int(row[0]) if row else 0


def shared_storage_used(service):
    row = service.con.execute(
        "SELECT coalesce(sum(size),0) FROM files "
        "WHERE workspace_id=? AND vault_scope='workspace'",
        (service.wid,),
    ).fetchone()
    return int(row[0]) if row else 0


def personal_storage_limit(service):
    """Account-wide quota based on owner-paid workspaces, not team membership.

    Each account has its own 100 MB minimum. Members never inherit a team
    company's subscription for their private files. Server-side quotas are
    also checked by the independent PostgreSQL trigger.
    """
    from backend.plan_catalog import workspace_summary
    from backend.business import stamp

    stats = _private_stats(service)
    if stats is not None:
        return stats[1]
    con = _storage_con(service)
    ids = con.execute(
        "SELECT id FROM workspaces WHERE owner_id=?",
        (service.user["id"],),
    ).fetchall()
    quota = 100_000_000
    for row in ids:
        quota = max(quota, int(workspace_summary(con, row["id"], stamp())["storage_bytes"]))
    if int(service.user["entitlement_until"] or 0) > stamp():
        quota = max(quota, 500_000_000)
    return quota


def personal_workspace_id(user_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "smetra-workspace:" + user_id))
