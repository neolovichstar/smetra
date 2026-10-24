"""Read-only supplier price impact preview for a workspace estimate.

Amounts are integer minor units. Never alters quote prices, revisions or
published versions, and deliberately does not perform inferred FX conversions.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

MAX_SOURCE_AGE = 30 * 86400


def _positive_decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() and Decimal("0") < number <= Decimal("1000000") else None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if 0 <= n <= 10**12 else None


def _estimate_subtotal(item: dict, override_price: int) -> int | None:
    """Use the same per-line price modifiers and HALF_UP rules as business.calculate."""
    try:
        quantity = _positive_decimal(item.get("quantity"))
        coefficient = _positive_decimal(item.get("coefficient", "1"))
        markup = Decimal(str(item.get("markup", "0")))
        discount = Decimal(str(item.get("discount", "0")))
        tax = Decimal(str(item.get("tax", "0")))
        if (
            quantity is None or coefficient is None
            or any(not n.is_finite() for n in (markup, discount, tax))
            or not (0 <= markup <= 10000 and 0 <= discount <= 100 and 0 <= tax <= 100)
        ):
            return None
        base = (
            quantity * override_price * coefficient
            * (1 + markup / 100) * (1 - discount / 100)
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        added_tax = (base * tax / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        total = int(base + added_tax)
        return total if 0 <= total <= 10**15 else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def calculate_price_impact(
    quote: dict, sources: list[dict], now: int, *, max_age: int = MAX_SOURCE_AGE
) -> dict:
    """Compare the locked quote price to a recent compatible supplier observation.

    Requires one unambiguous active source for each line. Missing prices,
    different currencies/units, stale checks and unsupported rows are never
    counted as financial changes. Original quote is never mutated.
    """
    if not isinstance(quote, dict) or not isinstance(sources, list):
        raise ValueError("Invalid impact source")
    currency = str(quote.get("currency") or "").upper()
    items = quote.get("items", [])
    if not isinstance(items, list):
        items = []
    linked: dict[str, list[dict]] = {}
    for source in sources[:300]:
        if isinstance(source, dict):
            linked.setdefault(str(source.get("quote_item_id") or ""), []).append(source)
    results = []
    delta_total = 0
    counted = 0
    for item in items[:200]:
        if not isinstance(item, dict):
            continue
        line_id = str(item.get("line_id") or "")
        if not line_id:
            continue
        providers = [
            source for source in linked.get(line_id, [])
            if source.get("monitored") == 1 and source.get("source_status") == "active"
        ]
        if not providers:
            continue
        result = {
            "line_id": line_id,
            "name": str(item.get("name") or "")[:200],
            "unit": str(item.get("unit") or "")[:30],
            "quantity": str(item.get("quantity") or ""),
            "status": "unavailable",
            "reason": "",
        }
        results.append(result)
        if item.get("included") is False:
            result.update(status="skipped", reason="Позиция исключена из расчёта")
            continue
        if len(providers) != 1:
            result.update(status="ambiguous", reason="Для позиции несколько поставщиков: выберите основной источник")
            continue
        source = providers[0]
        # Price of a package cannot be substituted for price per m².
        if str(source.get("currency") or "").upper() != currency:
            result.update(status="currency_mismatch", reason="Валюта поставщика отличается от валюты сметы")
            continue
        unit = str(item.get("unit") or "").strip().lower()
        src_unit = str(source.get("unit") or "").strip().lower()
        if not src_unit or src_unit != unit:
            result.update(status="unit_mismatch", reason="Единицы измерения различаются или не указаны")
            continue
        checked = _nonnegative_int(source.get("last_checked_at"))
        if checked is None or checked > now + 600 or now - checked > max_age:
            result.update(status="stale", reason="Цена давно не проверялась")
            continue
        observed = _nonnegative_int(source.get("price_kopecks"))
        original = _nonnegative_int(item.get("unit_price"))
        stored_subtotal = _nonnegative_int(item.get("subtotal"))
        if observed is None or original is None or stored_subtotal is None:
            result.update(status="invalid_price", reason="Не хватает достоверной цены")
            continue
        if str(source.get("availability") or "") == "out_of_stock":
            result.update(status="out_of_stock", reason="Товара нет в наличии")
            continue
        new_subtotal = _estimate_subtotal(item, observed)
        if new_subtotal is None:
            result.update(status="invalid_price", reason="Не удалось безопасно пересчитать позицию")
            continue
        difference = new_subtotal - stored_subtotal
        delta_total += difference
        counted += 1
        pct = (Decimal(observed - original) * 100 / Decimal(original)).quantize(
            Decimal(".01"), rounding=ROUND_HALF_UP
        ) if original else None
        result.update(
            status="comparable", reason="",
            quote_unit_price_kopecks=original,
            supplier_unit_price_kopecks=observed,
            checked_at=checked,
            currency=currency,
            quote_subtotal_kopecks=stored_subtotal,
            indicative_subtotal_kopecks=new_subtotal,
            delta_kopecks=difference,
            delta_percent=str(pct) if pct is not None else None,
            source_id=str(source.get("id") or ""),
            source_url=str(source.get("url") or "")[:2048],
        )
    original_total = _nonnegative_int(quote.get("amount_kopecks"))
    total = original_total + delta_total if original_total is not None else None
    if total is not None and (total < 0 or total > 10**15):
        total = None
    return {
        "quote_id": str(quote.get("id") or ""),
        "revision": quote.get("revision"),
        "currency": currency,
        "original_total_kopecks": original_total,
        "indicative_total_kopecks": total,
        "comparable_delta_kopecks": delta_total,
        "comparable_lines": counted,
        "linked_lines": len(results),
        "lines": results,
        "observation_only": True,
        "financial_price_changed": False,
        "notice": "Справочное сравнение текущих наблюдений поставщиков с ценами сметы. Оно не меняет смету и не является автоматическим пересогласованием или прогнозом инфляции.",
    }
