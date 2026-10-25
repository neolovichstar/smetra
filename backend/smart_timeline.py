"""Deterministic, read-only construction timeline preview.

Durations are derived only from explicit input: the user's production rate or
manual duration, not fabricated drying standards. A dependency's curing delay
uses calendar days; a work stage can use business days (Mon–Fri).
No external AI, quotes, billing changes or server-side writes.
"""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, InvalidOperation, ROUND_CEILING

_CODE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class TimelineError(ValueError):
    pass


def _decimal(value, label: str, minimum: str, maximum: str) -> Decimal:
    if isinstance(value, bool):
        raise TimelineError(f"Проверьте поле «{label}»")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise TimelineError(f"Проверьте поле «{label}»") from None
    if not number.is_finite() or number < Decimal(minimum) or number > Decimal(maximum):
        raise TimelineError(f"Проверьте поле «{label}»")
    return number


def _integer(value, label: str, minimum: int, maximum: int) -> int:
    number = _decimal(value, label, str(minimum), str(maximum))
    if number != number.to_integral_value():
        raise TimelineError(f"«{label}» должно быть целым числом")
    return int(number)


def _date(value: object, label: str) -> dt.date:
    if not isinstance(value, str) or len(value) != 10:
        raise TimelineError(f"Проверьте дату «{label}»")
    try:
        result = dt.date.fromisoformat(value)
    except ValueError:
        raise TimelineError(f"Проверьте дату «{label}»") from None
    if result.isoformat() != value or result.year < 2020 or result.year > 2090:
        raise TimelineError(f"Проверьте дату «{label}»")
    return result


def _advance(start: dt.date, days: int, weekdays: bool) -> dt.date:
    if not weekdays:
        return start + dt.timedelta(days=days)
    current = start
    remaining = days
    while remaining:
        if current.weekday() < 5:
            remaining -= 1
        current += dt.timedelta(days=1)
    return current


def _workday(day: dt.date, weekdays: bool) -> dt.date:
    if weekdays:
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
    return day


def preview(data: dict) -> dict:
    """Compute parallel/sequential dependencies; end_date is inclusive.

    stages: {id, name, quantity, daily_output, duration_days,
             curing_days, delay_days, depends_on: [stage-id, ...]}
    quantity/daily_output may be omitted if duration_days is supplied.
    Curing is a *user-specified* hold after completion, applied to successors.
    """
    if not isinstance(data, dict):
        raise TimelineError("Некорректный план")
    start = _date(data.get("start_date"), "начала")
    weekdays = data.get("workdays_only", True)
    if not isinstance(weekdays, bool):
        raise TimelineError("Некорректный календарь рабочих дней")
    raw = data.get("stages")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 40:
        raise TimelineError("Укажите от 1 до 40 этапов")
    stages = {}
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise TimelineError("Некорректные данные этапа")
        code = item.get("id")
        if not isinstance(code, str) or not _CODE.fullmatch(code) or code in stages:
            raise TimelineError("Идентификаторы этапов должны быть уникальными")
        name = item.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise TimelineError("Укажите название этапа до 120 символов")
        deps = item.get("depends_on", [])
        if not isinstance(deps, list) or len(deps) > 20 or any(not isinstance(d, str) for d in deps) or len(set(deps)) != len(deps):
            raise TimelineError("Некорректные зависимости этапа")
        if "duration_days" in item and item["duration_days"] not in (None, ""):
            duration = _integer(item["duration_days"], "Продолжительность", 1, 730)
            quantity = None
            output = None
        else:
            quantity = _decimal(item.get("quantity"), "Объём", "0.0001", "100000000")
            output = _decimal(item.get("daily_output"), "Выработка за день", "0.0001", "100000000")
            duration = int((quantity / output).to_integral_value(rounding=ROUND_CEILING))
            if not 1 <= duration <= 730:
                raise TimelineError("Продолжительность этапа превышает два года")
        curing = _integer(item.get("curing_days", 0), "Технологическая пауза", 0, 365)
        delay = _integer(item.get("delay_days", 0), "Задержка", 0, 365)
        stages[code] = {
            "id": code, "name": name.strip(), "duration_days": duration,
            "curing_days": curing, "delay_days": delay,
            "depends_on": deps, "quantity": str(quantity) if quantity is not None else None,
            "daily_output": str(output) if output is not None else None,
            "order": index,
        }
    for item in stages.values():
        if item["id"] in item["depends_on"] or any(dep not in stages for dep in item["depends_on"]):
            raise TimelineError("Зависимость указывает на отсутствующий этап")

    done, visiting = {}, set()
    first = _workday(start, weekdays)

    def resolve(code: str) -> dict:
        if code in done:
            return done[code]
        if code in visiting:
            raise TimelineError("Обнаружена циклическая зависимость этапов")
        visiting.add(code)
        item = stages[code]
        predecessors = [resolve(dep) for dep in item["depends_on"]]
        ready = max((p["_ready"] for p in predecessors), default=first)
        begin = _workday(max(first, ready), weekdays)
        exclusive_end = _advance(begin, item["duration_days"] + item["delay_days"], weekdays)
        finish = exclusive_end - dt.timedelta(days=1)
        while weekdays and finish.weekday() >= 5:
            finish -= dt.timedelta(days=1)
        next_ready = exclusive_end + dt.timedelta(days=item["curing_days"])
        if (next_ready - start).days > 3650:
            raise TimelineError("План превышает десять лет")
        result = {
            "id": code, "name": item["name"], "start_date": begin.isoformat(),
            "end_date": finish.isoformat(), "ready_date": next_ready.isoformat(),
            "duration_days": item["duration_days"],
            "curing_days": item["curing_days"],
            "delay_days": item["delay_days"],
            "depends_on": item["depends_on"], "quantity": item["quantity"],
            "daily_output": item["daily_output"], "_ready": next_ready,
            "_finish": finish,
        }
        done[code] = result
        visiting.remove(code)
        return result

    ordered = [resolve(key) for key in stages]
    # Handover must also respect the final curing hold, even if no later task
    # depends on it. Curing uses calendar days, so weekends may be included.
    final = max(max(item["_finish"], item["_ready"] - dt.timedelta(days=1)) for item in ordered)
    return {
        "start_date": first.isoformat(),
        "end_date": final.isoformat(),
        "calendar_days": (final - first).days + 1,
        "workdays_only": weekdays,
        "stages": [{k: v for k, v in step.items() if not k.startswith("_")} for step in ordered],
        "disclaimer": "Ориентировочный план: сроки и технологические перерывы вводит специалист. Не заменяет инструкции производителя и обследование объекта.",
    }
