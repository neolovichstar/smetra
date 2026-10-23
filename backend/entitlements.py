"""Server-authoritative workspace plan and feature entitlements.

Legacy Pro purchases map to PRO Solo. They deliberately do not unlock PRO Plus
material monitoring or cloud integrations.
"""
from __future__ import annotations

from typing import Any

PLAN_TIER = {
    "free": "starter",
    "starter": "starter",
    "pro": "pro_solo",
    "pro_month": "pro_solo",
    "pro_year": "pro_solo",
    "pro_solo": "pro_solo",
    "pro_solo_month": "pro_solo",
    "pro_solo_year": "pro_solo",
    "pro_solo_monthly": "pro_solo",
    "pro_solo_yearly": "pro_solo",
    "pro_plus": "pro_plus",
    "pro_plus_month": "pro_plus",
    "pro_plus_year": "pro_plus",
    "pro_plus_monthly": "pro_plus",
    "pro_plus_yearly": "pro_plus",
    "team": "team",
    "team_month": "team",
    "team_year": "team",
    "team_monthly": "team",
    "team_yearly": "team",
}
TIER_RANK = {"starter": 0, "pro_solo": 1, "pro_plus": 2, "team": 3}
FEATURE_MINIMUM_TIER = {
    "visual_estimates": "pro_plus",
    "product_monitor": "pro_plus",
    "cloud_drives": "pro_plus",
    "team_management": "team",
    "object_chats": "team",
    "clean_export": "pro_solo",
    "finance": "pro_plus",
    "document_branding": "pro_plus",
}
PAID_STATUSES = frozenset(("active", "trialing", "paid"))
PREMIUM_PLUS_PLAN_CODES = tuple(
    code for code, tier in PLAN_TIER.items() if tier in ("pro_plus", "team")
)


def evaluate_workspace_plan(row: Any, feature: str, now: int) -> dict[str, Any]:
    """Return an explicit feature decision without trusting client-side plan state."""
    minimum = FEATURE_MINIMUM_TIER.get(feature)
    if minimum is None:
        raise ValueError("Unknown entitlement feature")
    raw_plan = str(row["plan"] or "free") if row else "free"
    tier = PLAN_TIER.get(raw_plan, "starter")
    expires_at = int(row["entitlement_until"] or 0) if row else 0
    status = str(row["subscription_status"] or "").lower() if row else ""
    entitled = tier == "starter" or (
        expires_at > now and status in PAID_STATUSES
    )
    effective_tier = tier if entitled else "starter"
    allowed = TIER_RANK[effective_tier] >= TIER_RANK[minimum]
    return {
        "allowed": allowed,
        "plan": raw_plan,
        "tier": effective_tier,
        "minimum_tier": minimum,
        "entitled_until": expires_at if entitled else 0,
    }


def workspace_plan_row(con: Any, workspace_id: str, now: int) -> Any:
    row = con.execute(
        "SELECT w.plan,w.subscription_status,w.entitlement_until,w.owner_id,"
        "u.entitlement_until AS legacy_until FROM workspaces w JOIN users u ON u.id=w.owner_id WHERE w.id=?",
        (workspace_id,),
    ).fetchone()
    if not row:
        return None
    value = dict(row)
    # Historical personal Pro grants retain Solo benefits in their original workspace.
    # A new payment bound to another workspace cannot expand personal access.
    if PLAN_TIER.get(str(value["plan"]), "starter") == "starter" and value["legacy_until"] > now:
        import uuid
        personal = str(uuid.uuid5(uuid.NAMESPACE_URL, "smetra-workspace:" + value["owner_id"]))
        bound = con.execute(
            "SELECT 1 FROM billing_intents b JOIN payments p ON p.id=b.payment_id "
            "WHERE b.user_id=? AND b.workspace_id IS NOT NULL AND p.status='succeeded' "
            "AND NOT EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded') LIMIT 1",
            (value["owner_id"],),
        ).fetchone()
        if workspace_id == personal and not bound:
            value.update(plan="pro", subscription_status="active", entitlement_until=value["legacy_until"])
    return value


def workspace_feature_access(con: Any, workspace_id: str, feature: str, now: int) -> dict[str, Any]:
    return evaluate_workspace_plan(workspace_plan_row(con, workspace_id, now), feature, now)
