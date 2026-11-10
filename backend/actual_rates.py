"""Explicitly approved cost rates from a company's completed jobs, never model prices."""
import json
from decimal import Decimal, ROUND_HALF_UP

from backend.business import DomainError, integer, packed, stamp, string
from backend.quote_integrity import fingerprint


def completed(service, object_id):
    obj = service.get("construction_objects", object_id)
    project = service.get("projects", obj["project_id"]) if obj["project_id"] else None
    if not project or project["status"] != "completed":
        raise DomainError(409, "Расценки по факту доступны после завершения связанного заказа")
    currency = service.con.execute("SELECT currency FROM workspaces WHERE id=?", (service.wid,)).fetchone()["currency"]
    if project["currency"] != currency:
        raise DomainError(409, "Валюта заказа отличается от валюты каталога. Нужна отдельная проверка пересчёта")
    return obj, project


def candidate(service, quantity, facts=None, purchases=None):
    if facts is None:
        facts = [dict(row) for row in service.con.execute("SELECT quantity,note,created_at FROM construction_facts WHERE quantity_id=? AND workspace_id=? ORDER BY id", (quantity["id"], service.wid))]
    if purchases is None:
        purchases = [dict(row) for row in service.con.execute("SELECT quantity,unit_price_kopecks,purchased_on FROM construction_purchases WHERE material_id=? AND workspace_id=? AND status='received' ORDER BY id", (quantity["id"], service.wid))]
    stored = json.loads(quantity["actual_cost_data"])
    source = {"quantity_id": quantity["id"], "unit": quantity["unit"], "facts": facts, "purchases": purchases, "actual_cost_data": stored}
    amount, count, basis = 0, Decimal(0), ""
    if quantity["kind"] == "material" and purchases:
        count = sum((Decimal(row["quantity"]) for row in purchases), Decimal(0))
        amount = sum(int((Decimal(row["quantity"]) * row["unit_price_kopecks"]).quantize(Decimal(1), rounding=ROUND_HALF_UP)) for row in purchases)
        basis = "Средневзвешенная цена полученных закупок"
    elif quantity["kind"] == "work" and stored:
        count = sum((Decimal(row["quantity"]) for row in facts), Decimal(0))
        amount = stored["actual_cost_kopecks"]
        basis = "Фактическая себестоимость, распределённая подрядчиком: " + stored["note"]
    rate = int((Decimal(amount) / count).quantize(Decimal(1), rounding=ROUND_HALF_UP)) if count > 0 and amount > 0 else None
    return {"quantity_id": quantity["id"], "name": quantity["title"], "kind": quantity["kind"], "unit": quantity["unit"],
            "catalog_id": quantity["catalog_id"], "actual_quantity": str(count), "actual_cost_kopecks": amount,
            "cost_price": rate, "basis": basis, "source_sha256": fingerprint(source), "actual_cost_data": stored,
            "note": "Это себестоимость по вашим фактам, а не рыночная цена и не новая цена продажи."}


def route(service, method, parts, data):
    if len(parts) != 2:
        raise DomainError(404, "Действие не найдено")
    action, record_id = parts
    if action == "rates" and method == "GET":
        obj, project = completed(service, record_id)
        rows = service.con.execute("SELECT * FROM construction_quantities WHERE object_id=? AND workspace_id=? AND kind IN ('work','material') ORDER BY created_at,id LIMIT 200", (obj["id"], service.wid)).fetchall()
        facts, purchases = {row["id"]: [] for row in rows}, {row["id"]: [] for row in rows}
        for row in service.con.execute("SELECT quantity_id,quantity,note,created_at FROM construction_facts WHERE object_id=? AND workspace_id=? ORDER BY id", (obj["id"], service.wid)):
            item = dict(row)
            key = item.pop("quantity_id")
            if key in facts:
                facts[key].append(item)
        for row in service.con.execute("SELECT material_id,quantity,unit_price_kopecks,purchased_on FROM construction_purchases WHERE object_id=? AND workspace_id=? AND status='received' ORDER BY id", (obj["id"], service.wid)):
            item = dict(row)
            key = item.pop("material_id")
            if key in purchases:
                purchases[key].append(item)
        return 200, {"object_id": obj["id"], "currency": project["currency"], "items": [candidate(service, row, facts[row["id"]], purchases[row["id"]]) for row in rows]}
    if action not in ("actual-cost", "learn-rate") or method != "POST":
        raise DomainError(405, "Метод не поддерживается")
    quantity = service.get("construction_quantities", record_id)
    obj, _ = completed(service, quantity["object_id"])
    proposed = candidate(service, quantity)
    if data.get("source_sha256") != proposed["source_sha256"]:
        raise DomainError(409, "Фактические данные изменились. Обновите расчёт")
    if action == "actual-cost":
        if quantity["kind"] != "work":
            raise DomainError(400, "Стоимость материалов берётся из полученных закупок")
        if not service.con.execute("SELECT 1 FROM construction_facts WHERE quantity_id=? AND workspace_id=?", (quantity["id"], service.wid)).fetchone():
            raise DomainError(409, "Сначала запишите фактически выполненный объём работы")
        values = {"actual_cost_kopecks": integer(data.get("actual_cost_kopecks"), "Распределённая себестоимость", 1),
                  "note": string(data.get("note", ""), "Основание распределения", 1000, True), "updated_at": stamp(), "updated_by": service.user["id"]}
        service.update("construction_quantities", quantity["id"], {"actual_cost_data": packed(values)})
        service.emit("construction_object", obj["id"], "Основание фактической расценки сохранено")
        return 200, {"candidate": candidate(service, service.get("construction_quantities", record_id))}
    if data.get("confirmation") is not True or proposed["cost_price"] is None:
        raise DomainError(400, "Проверьте факты и подтвердите перенос себестоимости в каталог")
    catalog_id = data.get("catalog_id")
    if not catalog_id and quantity["catalog_id"] and data.get("create") is True:
        previous = service.get("catalog_items", quantity["catalog_id"])
        origin = json.loads(previous["actual_rate_source"] or "{}")
        if origin.get("source_sha256") == proposed["source_sha256"] and previous["cost_price"] == proposed["cost_price"]:
            return 200, {"item": dict(previous), "actual_rate_source": origin, "replayed": True}
        raise DomainError(409, "Для этой позиции уже есть расценка. Выберите её для обновления")
    if catalog_id:
        catalog = service.get("catalog_items", string(catalog_id, "Расценка", 80, True))
        service.check_revision(catalog, data)
        if catalog["unit"] != quantity["unit"] or catalog["item_type"] != quantity["kind"]:
            raise DomainError(409, "Единица и тип выбранной расценки должны совпадать с фактическими данными")
        code, result = service.route("PATCH", "catalog", [catalog["id"]], {}, {"revision": catalog["revision"], "cost_price": proposed["cost_price"]})
    else:
        if data.get("create") is not True:
            raise DomainError(400, "Выберите расценку каталога или подтвердите создание новой")
        code, result = service.route("POST", "catalog", [], {}, {"name": quantity["title"], "unit": quantity["unit"],
            "item_type": quantity["kind"], "price": 0, "cost_price": proposed["cost_price"], "category": "По факту завершённых заказов"})
        catalog_id = result["item"]["id"]
        service.update("construction_quantities", quantity["id"], {"catalog_id": catalog_id})
    source = {"object_id": obj["id"], "quantity_id": quantity["id"], "source_sha256": proposed["source_sha256"], "basis": proposed["basis"],
              "actual_quantity": proposed["actual_quantity"], "actual_cost_kopecks": proposed["actual_cost_kopecks"], "unit": proposed["unit"],
              "cost_price": proposed["cost_price"], "approved_at": stamp(), "approved_by": service.user["id"]}
    service.update("catalog_items", catalog_id, {"actual_rate_source": packed(source)})
    service.emit("catalog", catalog_id, "Фактическая себестоимость подтверждена", "Цена продажи не изменена")
    return code, {**result, "actual_rate_source": source}
