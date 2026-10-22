"""Canonical subscription catalogue. Public prices are fixed server-side.

Legacy products remain reconcilable for historical payments but are not purchasable.
Amounts are integer kopecks; clients must always treat the server as price authority.
"""
PUBLIC_PLANS = {
    "pro_month": {
        "amount_kopecks": 49000, "duration_days": 31, "product_code": "pro_solo_month",
        "title": "PRO Solo", "period": "month", "tier": "solo",
        "features": [
            "Без рекламы", "Неограниченное число смет", "Приоритетная очередь ИИ",
            "PDF и XLSX без водяного знака", "500 МБ облачного хранилища",
        ],
    },
    "pro_year": {
        "amount_kopecks": 490000, "duration_days": 366, "product_code": "pro_solo_year",
        "title": "PRO Solo", "period": "year", "tier": "solo",
        "features": [
            "Без рекламы", "Неограниченное число смет", "Приоритетная очередь ИИ",
            "PDF и XLSX без водяного знака", "500 МБ облачного хранилища",
        ],
    },
    "pro_plus_month": {
        "amount_kopecks": 69000, "duration_days": 31, "product_code": "pro_plus_month",
        "title": "PRO Плюс / Снабженец", "period": "month", "tier": "plus",
        "features": [
            "Всё из PRO Solo", "Авансы, расходы и этапы выполнения строк",
            "Конструктор фирменных бланков", "Облачное хранилище до 5 ГБ",
        ],
    },
    "pro_team_month": {
        "amount_kopecks": 399000, "duration_days": 31, "product_code": "pro_team_month",
        "title": "TEAM / Компания", "period": "month", "tier": "team", "seat_limit": 5,
        "features": [
            "Всё из PRO Плюс", "Владелец и до четырёх сотрудников",
            "Единое рабочее пространство и база клиентов", "Синхронизация между устройствами",
        ],
    },
    "pro_team_year": {
        "amount_kopecks": 3990000, "duration_days": 366, "product_code": "pro_team_year",
        "title": "TEAM / Компания", "period": "year", "tier": "team", "seat_limit": 5,
        "features": [
            "Всё из PRO Плюс", "Владелец и до четырёх сотрудников",
            "Единое рабочее пространство и база клиентов", "Синхронизация между устройствами",
        ],
    },
}
PUBLIC_PLAN_CODES = frozenset(PUBLIC_PLANS)
CHECKOUT_PLAN_CODES = PUBLIC_PLAN_CODES

# Historical codes are retained only to reconcile refunds and already-created payments.
LEGACY_BILLING_PLANS = {
    "smart_supplier_month": (20000, 31),
    "lead_tokens_150": (15000, 31),
}
BILLING_PLANS = {
    code: (plan["amount_kopecks"], plan["duration_days"])
    for code, plan in PUBLIC_PLANS.items()
}
BILLING_PLANS.update(LEGACY_BILLING_PLANS)
