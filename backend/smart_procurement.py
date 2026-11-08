"""Deterministic, verifiable procurement comparison over user-entered offers.

Only complete landed-cost quotes qualify as "cheapest"; missing stock, delivery
price, city or deadline data is not guessed. Partner commissions are never read.
This module does not place orders or invent online inventory.
"""
import datetime as dt
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP

from backend.business import DomainError, business_date, decimal, integer, string

MAX_QUOTES_PER_OBJECT = 200
MAX_QUOTES_PER_MATERIAL = 20
STEP = Decimal("0.0001")
MAX_TOTAL = 9_007_199_254_740_991


def _date(value, label):
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise DomainError(400, "Неверная дата: " + label)
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        raise DomainError(400, "Неверная дата: " + label) from None


def _number(value, label, optional=False):
    if value in ("", None):
        return None if optional else Decimal(0)
    return decimal(value, label, "0", "1000000", places=4)


def quote_fields(data, previous=None):
    if not isinstance(data, dict):
        raise DomainError(400, "Укажите условия предложения")
    old = dict(previous) if previous is not None else {}
    get = lambda key, default=None: data.get(key, old.get(key, default))
    price = integer(get("unit_price_kopecks"), "Цена поставщика", 1, 100_000_000_000)
    shipping = get("delivery_kopecks")
    days = get("delivery_days")
    stock = _number(get("stock_quantity"), "Остаток", optional=True)
    minimum = _number(get("min_order_quantity", "0"), "Минимальная партия")
    if stock is not None and minimum > stock:
        raise DomainError(400, "Минимальная партия превышает указанный остаток")
    return dict(
        supplier_name=string(get("supplier_name", ""), "Название поставщика", 200, True),
        material_id=string(get("material_id", ""), "Материал", 100, True),
        unit_price_kopecks=price,
        stock_quantity=str(stock) if stock is not None else None,
        min_order_quantity=str(minimum),
        delivery_kopecks=None if shipping in (None, "") else integer(shipping, "Доставка", 0, 100_000_000_000),
        delivery_days=None if days in (None, "") else integer(days, "Срок доставки", 0, 3650),
        delivery_city=string(get("delivery_city", ""), "Город доставки", 120),
        expires_on=_date(get("expires_on", ""), "срок действия предложения"),
        notes=string(get("notes", ""), "Примечание к предложению", 800),
    )


def _city(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().replace("ё", "е").split())


def _kopecks(qty, unit_price):
    value = int((qty * Decimal(unit_price)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if value > MAX_TOTAL:
        raise DomainError(400, "Сумма предложения слишком велика")
    return value


def _candidate(allocations):
    lines = []
    subtotal, delivery = 0, 0
    lead_time = 0
    requested = Decimal(0)
    for offer, qty in allocations:
        product_cost = _kopecks(qty, offer["unit_price_kopecks"])
        subtotal += product_cost
        delivery += offer["delivery_kopecks"]
        requested += qty
        if offer["delivery_days"] is None:
            lead_time = None
        elif lead_time is not None:
            lead_time = max(lead_time, offer["delivery_days"])
        lines.append(dict(
            quote_id=offer["id"], supplier=offer["supplier_name"], quantity=str(qty),
            unit_price_kopecks=offer["unit_price_kopecks"], material_kopecks=product_cost,
            delivery_kopecks=offer["delivery_kopecks"], delivery_days=offer["delivery_days"],
        ))
    if subtotal + delivery > MAX_TOTAL:
        raise DomainError(400, "Сумма предложения слишком велика")
    return dict(
        kind="single" if len(lines) == 1 else "split", suppliers=lines,
        products_kopecks=subtotal, delivery_kopecks=delivery,
        total_kopecks=subtotal + delivery, purchased_quantity=str(requested),
        delivery_days=lead_time,
    )


def _split_choices(left, right, required):
    lo1 = max(STEP, Decimal(left["min_order_quantity"]))
    lo2 = max(STEP, Decimal(right["min_order_quantity"]))
    hi1, hi2 = Decimal(left["stock_quantity"]), Decimal(right["stock_quantity"])
    if lo1 > hi1 or lo2 > hi2 or hi1 + hi2 < required:
        return []
    # Linear landed cost has its optimum at an interval boundary. Check each
    # inventory/minimum-order boundary (both orderings are considered).
    boundaries = (lo1, hi1, required - hi2, required - lo2)
    results = []
    for q1 in boundaries:
        q1 = max(lo1, min(hi1, q1))
        q2 = max(lo2, required - q1)
        if q2 <= hi2 and q1 > 0 and q2 > 0:
            results.append(_candidate(((left, q1), (right, q2))))
    return results


def compare(required_quantity, quotes, *, needed_by="", site_city="", today=None):
    required = _number(required_quantity, "Потребность")
    deadline = _date(needed_by, "нужная дата")
    when = business_date() if today is None else today
    if deadline and dt.date.fromisoformat(deadline) < when:
        raise DomainError(400, "Дата потребности уже прошла")
    location = _city(string(site_city, "Город объекта", 120))
    if len(quotes) > MAX_QUOTES_PER_MATERIAL:
        raise DomainError(409, "Слишком много предложений для одного материала")
    eligible, rejected = [], []
    for input_quote in quotes:
        q = dict(input_quote)
        reason = None
        if q.get("expires_on") and q["expires_on"] < when.isoformat():
            reason = "Предложение устарело"
        elif q.get("stock_quantity") is None:
            reason = "Остаток на складе не указан"
        elif Decimal(q["stock_quantity"]) <= 0:
            reason = "Товара нет в наличии"
        elif q.get("delivery_kopecks") is None:
            reason = "Стоимость доставки неизвестна"
        elif location and not _city(q.get("delivery_city")):
            reason = "Город доставки не подтверждён"
        elif location and location != _city(q["delivery_city"]):
            reason = "Нет подтверждённой доставки в указанный город"
        elif deadline and q.get("delivery_days") is None:
            reason = "Срок доставки неизвестен"
        elif deadline and q["delivery_days"] > (dt.date.fromisoformat(deadline) - when).days:
            reason = "Не успеет к нужной дате"
        if reason:
            rejected.append({"id": q["id"], "supplier": q["supplier_name"], "reason": reason})
        else:
            eligible.append(q)
    choices = []
    if required > 0:
        for q in eligible:
            quantity = max(required, Decimal(q["min_order_quantity"]))
            if quantity <= Decimal(q["stock_quantity"]):
                choices.append(_candidate(((q, quantity),)))
        # Splits are exact for up to two supplier offers. We do not claim a
        # globally optimal mix of three+ sellers or bundle deliveries across SKUs.
        for i, a in enumerate(eligible):
            for b in eligible[i + 1:]:
                choices.extend(_split_choices(a, b, required))
                choices.extend(_split_choices(b, a, required))
    # Stable, commission-free ranking: full price then fewer deliveries and ETA.
    choices.sort(key=lambda p: (p["total_kopecks"], len(p["suppliers"]),
                                p["delivery_days"] if p["delivery_days"] is not None else 9999,
                                tuple(x["quote_id"] for x in p["suppliers"])))
    unique, seen = [], set()
    for item in choices:
        key = tuple(sorted((x["quote_id"], x["quantity"]) for x in item["suppliers"]))
        if key not in seen:
            seen.add(key)
            unique.append(item)
        if len(unique) >= 5:
            break
    best = unique[0] if unique else None
    alternative = next((x for x in unique[1:] if x["total_kopecks"] > best["total_kopecks"]), None) if best else None
    return {
        "best": best, "alternatives": unique[1:],
        "compared": len(quotes), "complete": len(eligible),
        "excluded": rejected, "uncovered_quantity": str(required) if not best else "0",
        "saving_vs_next_kopecks": alternative["total_kopecks"] - best["total_kopecks"] if alternative else None,
        "scope_note": "Доставка учтена отдельно для каждого предложения и материала; общая доставка нескольких SKU и скидки за корзину не рассчитаны. Цены и остатки вводит пользователь, автоматической проверки у магазина нет.",
    }
