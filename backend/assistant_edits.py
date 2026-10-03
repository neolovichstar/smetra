"""Server-built quote diffs and revision-checked reversal of AI edits."""

import copy
import json
from decimal import Decimal, ROUND_HALF_UP

from backend.business import DomainError, calculate, choice, decimal, string, stamp, packed, transaction

FIELDS = ("unit_price", "quantity", "coefficient", "markup", "discount", "tax", "unit", "category")


def quote_snapshot(service, record):
    if record["approval_state"] != "draft":
        raise DomainError(409, "Ассистент редактирует только черновики. Создайте копию отправленной сметы")
    return service.quote_view(record)


def prepare_bulk(service, data):
    record = service.get("quotes", string(data.get("id", ""), "Смета", 80, True))
    quote = quote_snapshot(service, record)
    items = quote["items"]
    rows = data.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise DomainError(400, "Выберите от 1 до 50 строк сметы")
    if any(type(row) is not int or not 1 <= row <= len(items) for row in rows):
        raise DomainError(400, "Номера строк начинаются с 1 и должны существовать в смете")
    if len(set(rows)) != len(rows):
        raise DomainError(400, "Номера строк не должны повторяться")
    field = choice(data.get("field"), FIELDS, "Поле")
    operation = choice(data.get("operation", "set"), ("set", "multiply"), "Операция")
    value = data.get("value")
    changed = copy.deepcopy(items)
    if field in ("unit", "category"):
        if operation != "set":
            raise DomainError(400, "Текст можно только заменить")
        value = string(value, "Новое значение", 30 if field == "unit" else 100, field == "unit")
    elif operation == "multiply":
        value = decimal(value, "Множитель", "0.0001", "100")
    elif field == "unit_price":
        value = str(value) if type(value) is int else string(value, "Цена в копейках", 20, True)
        if not value.isascii() or not value.isdigit():
            raise DomainError(400, "Цена должна быть целым числом копеек")
        value = int(value)
    else:
        value = string(value, "Новое значение", 40, True) if isinstance(value, str) else value
    for row in rows:
        item = changed[row - 1]
        next_value = value
        if operation == "multiply":
            next_value = Decimal(str(item[field])) * value
            next_value = (int(next_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                          if field == "unit_price" else str(next_value.normalize()))
        item[field] = next_value
    changed, total, _ = calculate(changed)
    differences = [{"row": row, "name": items[row - 1]["name"], "field": field,
                    "before": items[row - 1][field], "after": changed[row - 1][field],
                    "before_amount": items[row - 1]["subtotal"], "after_amount": changed[row - 1]["subtotal"]}
                   for row in sorted(rows) if items[row - 1][field] != changed[row - 1][field]]
    if not differences:
        raise DomainError(409, "Выбранные строки уже содержат это значение")
    preview = {"kind": "quote_items", "title": quote["title"], "currency": quote["currency"],
               "before_total": quote["amount_kopecks"], "after_total": total, "rows": differences}
    return {"id": record["id"], "revision": record["revision"], "items": changed,
            "_undo_fields": {"items": items}, "_preview": preview}


def before_update(service, entity, record, arguments):
    source = quote_snapshot(service, record) if entity == "quotes" else dict(record)
    if entity == "quotes":
        if "amount" in arguments and source["itemized"]:
            raise DomainError(400, "Итог сметы рассчитывается по строкам. Измените цены или количество позиций")
        if "items" in arguments and not source["itemized"]:
            raise DomainError(409, "Чтобы добавить состав к простой смете, подготовьте новую смету с позициями")
        service.quote_data(arguments, record)
    before = {}
    rows = []
    for field in arguments:
        if field in ("id", "revision"):
            continue
        original = source.get("amount_kopecks") if field == "amount" else source.get(field)
        if original != arguments[field]:
            before[field] = original
            rows.append({"field": field, "before": original, "after": arguments[field]})
    if not before:
        raise DomainError(409, "Запись уже содержит эти значения")
    return before, {"kind": "fields", "currency": source.get("currency", "RUB"), "rows": rows}


def undo(service, action_id):
    service.write_access()
    with transaction(service.con):
        row = service.con.execute(
            "SELECT * FROM assistant_actions WHERE id=? AND workspace_id=? AND user_id=?",
            (action_id, service.wid, service.user["id"]),
        ).fetchone()
        if not row:
            raise DomainError(404, "Действие не найдено")
        result = json.loads(row["result"])
        if row["status"] == "undone":
            return result["undo_result"]
        state = result.get("undo")
        if row["status"] != "applied" or not isinstance(state, dict) or result.get("undo_until", 0) < stamp():
            raise DomainError(409, "Это действие уже нельзя отменить")
        from backend.assistant import TABLE

        current = service.get(TABLE.get(state["entity"], state["entity"]), state["id"])
        if current["revision"] != state["revision"]:
            raise DomainError(409, "Запись изменилась после действия ассистента. Отмена не перезапишет новые изменения")
        if state["entity"] == "quotes":
            quote_snapshot(service, current)
        status, restored = service.route("PATCH", state["entity"], [state["id"]], {},
                                        {**state["fields"], "revision": current["revision"]})
        if status >= 400:
            raise DomainError(status, "Не удалось отменить изменение")
        reverted = {"ok": True, "summary": row["summary"], "result": restored, "undone": True}
        result["undo_result"] = reverted
        result["undoable"] = False
        service.con.execute("UPDATE assistant_actions SET status='undone',result=? WHERE id=?",
                            (packed(result), action_id))
        service.emit("ai", action_id, "Отменено: " + row["summary"])
        return reverted
