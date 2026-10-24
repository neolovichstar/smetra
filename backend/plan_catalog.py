"""The four public products; prices and limits are owned by the server."""
from copy import deepcopy

CATALOG = {
    "starter": {"name": "Старт", "monthly_kopecks": 0, "yearly_kopecks": None,
                "seats": 1, "storage_bytes": 0, "free_quotes": 10, "priority": "standard"},
    "pro_solo": {"name": "PRO Solo", "monthly_kopecks": 49000, "yearly_kopecks": 490000,
                 "seats": 1, "storage_bytes": 500_000_000, "free_quotes": None, "priority": "turbo"},
    "pro_plus": {"name": "PRO Плюс / Снабженец", "monthly_kopecks": 69000, "yearly_kopecks": None,
                 "seats": 1, "storage_bytes": 5_000_000_000, "free_quotes": None, "priority": "turbo"},
    "team": {"name": "TEAM / Компания", "monthly_kopecks": 399000, "yearly_kopecks": 3990000,
             "seats": 5, "storage_bytes": 5_000_000_000, "free_quotes": None, "priority": "turbo"},
}
# Existing purchase codes remain valid, preserving receipts and idempotent retries.
PURCHASES = {
    "pro_month": ("pro_solo", 49000, 31),
    "pro_year": ("pro_solo", 490000, 366),
    "pro_plus_month": ("pro_plus", 69000, 31),
    "team_month": ("team", 399000, 31),
    "team_year": ("team", 3990000, 366),
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
