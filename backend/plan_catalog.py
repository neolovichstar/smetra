"""The four public products; prices and limits are owned by the server."""
from copy import deepcopy

# Signups before this rollout retain the previously advertised 10 drafts.
# The limit is lifetime, NOT monthly, and editing an existing quote is free.
STARTER_LEGACY_CUTOFF = 1793190480  # 2026-10-28 12:28:00 UTC
STARTER_NEW_QUOTES = 3
STARTER_LEGACY_QUOTES = 10


def starter_quote_limit(owner):
    """Server-side, immutable-at-signup free quote allowance for the owner."""
    return (STARTER_LEGACY_QUOTES if int(owner["created_at"] or 0) < STARTER_LEGACY_CUTOFF
            else STARTER_NEW_QUOTES)


CATALOG = {
    "starter": {"name": "Старт", "monthly_kopecks": 0, "yearly_kopecks": None,
                "seats": 1, "storage_bytes": 0, "free_quotes": STARTER_NEW_QUOTES, "priority": "standard"},
    "pro_solo": {"name": "PRO Solo", "monthly_kopecks": 79000, "yearly_kopecks": 790000,
                 "seats": 1, "storage_bytes": 500_000_000, "free_quotes": None, "priority": "turbo"},
    "pro_plus": {"name": "PRO Плюс / Снабженец", "monthly_kopecks": 149000, "yearly_kopecks": 1490000,
                 "seats": 1, "storage_bytes": 5_000_000_000, "free_quotes": None, "priority": "turbo"},
    "team": {"name": "TEAM / Компания", "monthly_kopecks": 699000, "yearly_kopecks": 6990000,
             "seats": 5, "storage_bytes": 5_000_000_000, "free_quotes": None, "priority": "turbo"},
}
# Existing purchase codes remain valid, preserving receipts and idempotent retries.
PURCHASES = {
    "pro_month": ("pro_solo", 79000, 31),
    "pro_year": ("pro_solo", 790000, 366),
    "pro_plus_month": ("pro_plus", 149000, 31),
    "pro_plus_year": ("pro_plus", 1490000, 366),
    "team_month": ("team", 699000, 31),
    "team_year": ("team", 6990000, 366),
}


def public_catalog():
    return deepcopy(CATALOG)


def workspace_summary(con, workspace_id, now):
    from backend.entitlements import evaluate_workspace_plan, workspace_plan_row
    row = workspace_plan_row(con, workspace_id, now)
    decision = evaluate_workspace_plan(row, "clean_export", now)
    tier = decision["tier"]
    return {**decision, **deepcopy(CATALOG[tier]),
            "features": {name: evaluate_workspace_plan(row, name, now)["allowed"]
                         for name in ("clean_export", "finance", "document_branding",
                                      "team_management", "object_chats", "cloud_drives",
                                      "visual_estimates", "product_monitor")}}
