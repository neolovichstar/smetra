"""Workspace-owned technological assemblies, using the existing quote calculator.

Applied rows keep their own formula and parameter snapshot. Editing a saved
assembly never changes an estimate, especially an already published version.
"""
import json
import re

from backend.business import DomainError, calculate, choice, identity, integer, packed, stamp, string
from backend.construction_math import decimal_value, evaluate

SCOPE_LABELS = {
    "included": "Включено в стоимость",
    "excluded": "Не включено в стоимость",
    "customer": "Обеспечивает заказчик",
    "clarifications": "Требует уточнения",
}


def scope(value):
    if not isinstance(value, dict) or set(value) - SCOPE_LABELS.keys():
        raise DomainError(400, "Проверьте границы предложения")
    result = {}
    for key in SCOPE_LABELS:
        entries = value.get(key, [])
        if not isinstance(entries, list) or len(entries) > 20:
            raise DomainError(400, "В каждом разделе условий может быть до 20 пунктов")
        result[key] = [string(entry, SCOPE_LABELS[key], 500, True) for entry in entries]
    if len(packed(result)) > 12000:
        raise DomainError(400, "Сократите условия предложения")
    return result


def scope_text(value):
    return "\n\n".join(label + ":\n" + "\n".join("• " + text for text in entries)
                        for key, label in SCOPE_LABELS.items() if (entries := value.get(key)))


def parameters(value):
    if not isinstance(value, dict) or not 1 <= len(value) <= 12:
        raise DomainError(400, "Укажите от 1 до 12 параметров сборки")
    result = {}
    for key, number in value.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,29}", key):
            raise DomainError(400, "Имена параметров: латинские буквы, цифры и подчёркивание")
        result[key] = str(decimal_value(number, key, maximum=1000000))
    return result


def source(value, quantity):
    """Validate private row provenance, never trust a browser-computed quantity."""
    if not isinstance(value, dict):
        raise DomainError(400, "Проверьте источник количества")
    result = {key: string(value.get(key, ""), key, limit, True)
              for key, limit in (("instance_id", 64), ("title", 120), ("expression", 160))}
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", result["instance_id"]):
        raise DomainError(400, "Проверьте идентификатор сборки")
    result["template_id"] = string(value.get("template_id", ""), "Сборка", 80)
    result["template_revision"] = integer(value.get("template_revision", 1), "Версия сборки", 1, 1000000)
    result["parameters"] = parameters(value.get("parameters"))
    derived = evaluate(result["expression"], result["parameters"])
    if derived != quantity:
        raise DomainError(409, "Количество связано со сборкой. Пересчитайте параметры или отключите связь")
    return result


def normalize(data):
    if not isinstance(data, dict):
        raise DomainError(400, "Проверьте сборку")
    title = string(data.get("title", ""), "Название сборки", 120, True)
    defaults = parameters(data.get("parameters"))
    labels = data.get("labels", {})
    if not isinstance(labels, dict) or set(labels) - defaults.keys():
        raise DomainError(400, "Проверьте названия параметров")
    labels = {key: string(labels.get(key, key), "Параметр", 80, True) for key in defaults}
    supplied = data.get("items")
    if not isinstance(supplied, list) or not 1 <= len(supplied) <= 50:
        raise DomainError(400, "В сборке может быть от 1 до 50 позиций")
    items = []
    for item in supplied:
        if not isinstance(item, dict):
            raise DomainError(400, "Проверьте позиции сборки")
        expression = string(item.get("expression", ""), "Формула количества", 160, True)
        # Strip prior instance IDs; a reusable assembly creates a new instance.
        row = {key: value for key, value in item.items() if key not in ("assembly", "line_id")}
        row["quantity"] = str(evaluate(expression, defaults))
        calculated = calculate([row], allow_zero_total=True)[0][0]
        calculated.pop("line_id")
        calculated["expression"] = expression
        items.append(calculated)
    currency = choice(data.get("currency", "RUB"), ("RUB", "USD", "EUR", "KZT", "BYN", "GBP"), "Валюта сборки")
    return {"title": title, "currency": currency, "parameters": defaults, "labels": labels, "items": items,
            "scope": scope(data.get("scope", {}))}


def record(service, template_id):
    row = service.get("estimate_templates", string(template_id, "Сборка", 80, True))
    if row["template_kind"] != "assembly":
        raise DomainError(404, "Сборка не найдена")
    return row, json.loads(row["snapshot"])


def preview(service, data):
    row, definition = record(service, data.get("id", ""))
    if data.get("currency", definition["currency"]) != definition["currency"]:
        raise DomainError(409, "Валюта сборки отличается от валюты сметы. Укажите расценки в валюте сметы")
    if "revision" in data and (type(data["revision"]) is not int or data["revision"] != definition["revision"]):
        raise DomainError(409, "Сборка изменилась. Обновите расчёт")
    values = parameters(data.get("parameters", definition["parameters"]))
    if set(values) != set(definition["parameters"]):
        raise DomainError(400, "Заполните все параметры сборки")
    instance = identity()
    rows = []
    for item in definition["items"]:
        expression = item["expression"]
        rows.append({**item, "line_id": identity(), "quantity": str(evaluate(expression, values)),
                     "assembly": {"instance_id": instance, "title": row["name"], "template_id": row["id"],
                                  "template_revision": definition["revision"], "expression": expression,
                                  "parameters": values}})
    items, total, cost = calculate(rows, allow_zero_total=True)
    return {"items": items, "currency": definition["currency"], "amount_kopecks": total, "internal_cost": cost, "scope": definition["scope"],
            "note": "Расчёт по вашим исходным данным. Проверьте технологию, расход по производителю и цены."}


def recalculate(data):
    supplied = data.get("items")
    if not isinstance(supplied, list) or not 1 <= len(supplied) <= 200:
        raise DomainError(400, "Проверьте позиции сметы")
    instance = string(data.get("instance_id", ""), "Сборка", 64, True)
    values = parameters(data.get("parameters"))
    rows, matched = [], False
    for item in supplied:
        if not isinstance(item, dict):
            raise DomainError(400, "Проверьте позиции сметы")
        metadata = item.get("assembly")
        if isinstance(metadata, dict) and metadata.get("instance_id") == instance:
            matched = True
            old = source(metadata, decimal_value(item.get("quantity"), "Количество"))
            if set(values) != set(old["parameters"]):
                raise DomainError(400, "Заполните все параметры сборки")
            metadata = {**old, "parameters": values}
            item = {**item, "quantity": str(evaluate(old["expression"], values)), "assembly": metadata}
        rows.append(item)
    if not matched:
        raise DomainError(404, "В смете нет этой сборки")
    items, total, cost = calculate(rows, allow_zero_total=True)
    return {"items": items, "amount_kopecks": total, "internal_cost": cost}


def merge_scope(before, extra):
    return {key: list(dict.fromkeys([*before.get(key, []), *extra.get(key, [])])) for key in SCOPE_LABELS}


def route(service, method, parts, data):
    # A definition includes private rates. Match protected-link management rights.
    service.write_access(True)
    if method == "POST" and parts in (["preview"], ["recalculate"]):
        service.h.throttle("assembly-calculate:" + service.user["id"], 90, 60)
        return 200, preview(service, data) if parts == ["preview"] else recalculate(data)
    if not parts and method == "GET":
        return 200, {"items": [{"id": row["id"], **json.loads(row["snapshot"])} for row in service.con.execute(
            "SELECT id,snapshot FROM estimate_templates WHERE workspace_id=? AND template_kind='assembly' "
            "ORDER BY created_at DESC,id LIMIT 100", (service.wid,))]}
    if len(parts) == 1 and method == "GET":
        row, definition = record(service, parts[0])
        return 200, {"assembly": {"id": row["id"], **definition}}
    if (not parts and method == "POST") or (len(parts) == 1 and method == "PATCH"):
        definition = normalize(data)
        template_id, revision = identity(), 1
        if parts:
            row, old = record(service, parts[0])
            if type(data.get("revision")) is not int or data["revision"] != old["revision"]:
                raise DomainError(409, "Сборка изменилась. Обновите страницу")
            template_id, revision = row["id"], old["revision"] + 1
        definition["revision"] = revision
        if parts:
            service.update("estimate_templates", template_id, {"name": definition["title"], "snapshot": packed(definition)})
        else:
            service.insert("estimate_templates", {"id": template_id, "workspace_id": service.wid,
                "name": definition["title"], "snapshot": packed(definition), "created_at": stamp(), "template_kind": "assembly"})
        service.emit("assembly", template_id, "Технологическая сборка сохранена")
        return 200 if parts else 201, {"assembly": {"id": template_id, **definition}}
    if len(parts) == 1 and method == "DELETE":
        row, _ = record(service, parts[0])
        service.con.execute("DELETE FROM estimate_templates WHERE id=? AND workspace_id=?", (row["id"], service.wid))
        service.emit("assembly", row["id"], "Сборка удалена; расчёты в сметах сохранены")
        return 200, {"ok": True}
    raise DomainError(405, "Метод не поддерживается")
