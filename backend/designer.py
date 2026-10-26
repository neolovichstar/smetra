"""Workspace-isolated interior design projects and room-level procurement specifications.

This is a separate designer workflow, not a second copy of the construction
measurement module. All amounts are minor units; AI never computes totals here.
"""
from decimal import Decimal, ROUND_HALF_UP

from backend.business import DomainError, choice, decimal, identity, integer, stamp, string

KINDS = ("finish", "furniture", "lighting", "plumbing", "decor", "equipment", "work", "other")
STATUSES = ("planned", "selected", "approved", "ordered", "delivered", "installed")
MAX_LINE_TOTAL = 10**13


def _revision(service, old, data):
    service.check_revision(old, data)


def _money(quantity, price):
    result = int((Decimal(quantity) * Decimal(price)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if result > MAX_LINE_TOTAL:
        raise DomainError(400, "Сумма позиции превышает допустимый предел")
    return result


def _item_data(service, data, old=None):
    result = {
        "kind": choice(data.get("kind", old["kind"] if old else "furniture"), KINDS, "Тип"),
        "name": string(data.get("name", old["name"] if old else ""), "Название позиции", 200, True),
        "article": string(data.get("article", old["article"] if old else ""), "Артикул", 100),
        "supplier": string(data.get("supplier", old["supplier"] if old else ""), "Поставщик", 200),
        "unit": string(data.get("unit", old["unit"] if old else "шт."), "Единица", 30, True),
        "notes": string(data.get("notes", old["notes"] if old else ""), "Примечания", 2000),
        "status": choice(data.get("status", old["status"] if old else "planned"), STATUSES, "Статус"),
        "unit_price": integer(data.get("unit_price", old["unit_price"] if old else 0), "Цена", 0, 1_000_000_000_00),
    }
    quantity = decimal(data.get("quantity", old["quantity"] if old else "1"), "Количество", "0.0001", "1000000", places=4)
    result["quantity"] = format(quantity, "f")
    _money(result["quantity"], result["unit_price"])
    room_id = data.get("room_id", old["room_id"] if old else None) or None
    if room_id:
        room = service.get("designer_rooms", room_id)
        if room["project_id"] != (old["project_id"] if old else data["_project_id"]):
            raise DomainError(400, "Помещение не относится к дизайн-проекту")
    result["room_id"] = room_id
    return result


def _item_view(row):
    item = dict(row)
    item["total_kopecks"] = _money(item["quantity"], item["unit_price"])
    item["price_missing"] = not bool(item["unit_price"])
    return item


def _project(service, project_id):
    return service.get("designer_projects", project_id)


def _room(service, project_id, room_id):
    room = service.get("designer_rooms", room_id)
    if room["project_id"] != project_id:
        raise DomainError(404, "Помещение не найдено")
    return room


def _item(service, project_id, item_id):
    item = service.get("designer_items", item_id)
    if item["project_id"] != project_id:
        raise DomainError(404, "Позиция не найдена")
    return item


def _detail(service, project):
    rooms = [dict(row) for row in service.con.execute(
        "SELECT * FROM designer_rooms WHERE workspace_id=? AND project_id=? ORDER BY created_at,id LIMIT 101",
        (service.wid, project["id"]),
    )]
    items = [_item_view(row) for row in service.con.execute(
        "SELECT * FROM designer_items WHERE workspace_id=? AND project_id=? ORDER BY created_at,id LIMIT 501",
        (service.wid, project["id"]),
    )]
    total = sum(row["total_kopecks"] for row in items)
    return {
        "project": dict(project),
        "rooms": rooms,
        "items": items,
        "summary": {
            "total_kopecks": total,
            "budget_kopecks": project["budget_kopecks"],
            "remainder_kopecks": project["budget_kopecks"] - total,
            "missing_prices": sum(item["price_missing"] for item in items),
            "positions": len(items),
        },
    }


def route(service, method, parts, query, data):
    con, wid = service.con, service.wid
    if not parts or parts[0] != "projects":
        raise DomainError(404, "Раздел не найден")
    if len(parts) == 1:
        if method == "GET":
            offset = service.page(query)
            rows = [dict(row) for row in con.execute(
                "SELECT * FROM designer_projects WHERE workspace_id=? "
                "ORDER BY updated_at DESC,id LIMIT 50 OFFSET ?",
                (wid, offset),
            )]
            return 200, {"projects": rows, "offset": offset, "limit": 50}
        if method == "POST":
            if con.execute("SELECT count(*) FROM designer_projects WHERE workspace_id=?", (wid,)).fetchone()[0] >= 200:
                raise DomainError(400, "В одном пространстве может быть до 200 дизайн-проектов")
            name = string(data.get("name", ""), "Название проекта", 200, True)
            description = string(data.get("description", ""), "Описание", 3000)
            budget = integer(data.get("budget_kopecks", 0), "Бюджет", 0, MAX_LINE_TOTAL)
            client_id = data.get("client_id") or None
            if client_id:
                service.get("clients", client_id)
            project_id, now = identity(), stamp()
            con.execute(
                "INSERT INTO designer_projects(id,workspace_id,client_id,name,description,budget_kopecks,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (project_id, wid, client_id, name, description, budget, now, now),
            )
            service.emit("designer_project", project_id, "Создан дизайн-проект")
            return 201, {"project": dict(_project(service, project_id))}
    if len(parts) < 2:
        raise DomainError(404, "Маршрут не найден")
    project_id = string(parts[1], "Проект", 100, True)
    project = _project(service, project_id)
    if len(parts) == 2:
        if method == "GET":
            return 200, _detail(service, project)
        if method == "PATCH":
            _revision(service, project, data)
            name = string(data.get("name", project["name"]), "Название проекта", 200, True)
            description = string(data.get("description", project["description"]), "Описание", 3000)
            budget = integer(data.get("budget_kopecks", project["budget_kopecks"]), "Бюджет", 0, MAX_LINE_TOTAL)
            con.execute(
                "UPDATE designer_projects SET name=?,description=?,budget_kopecks=?,revision=revision+1,updated_at=?"
                " WHERE id=? AND workspace_id=?",
                (name, description, budget, stamp(), project_id, wid),
            )
            service.emit("designer_project", project_id, "Дизайн-проект изменён")
            return 200, {"project": dict(_project(service, project_id))}
        if method == "DELETE":
            con.execute("DELETE FROM designer_projects WHERE id=? AND workspace_id=?", (project_id, wid))
            service.emit("designer_project", project_id, "Дизайн-проект удалён")
            return 200, {"deleted": True}

    kind = parts[2] if len(parts) >= 3 else ""
    if kind not in ("rooms", "items"):
        raise DomainError(404, "Маршрут не найден")
    table = "designer_rooms" if kind == "rooms" else "designer_items"
    if len(parts) == 3 and method == "POST":
        count = con.execute(f"SELECT count(*) FROM {table} WHERE workspace_id=? AND project_id=?", (wid, project_id)).fetchone()[0]
        if count >= (50 if kind == "rooms" else 500):
            raise DomainError(400, "Достигнут лимит помещений или позиций проекта")
        now, record_id = stamp(), identity()
        if kind == "rooms":
            values = {
                "name": string(data.get("name", ""), "Название помещения", 120, True),
                "notes": string(data.get("notes", ""), "Примечание", 2000),
            }
        else:
            values = _item_data(service, {**data, "_project_id": project_id})
        keys = ["id", "workspace_id", "project_id", "created_at", "updated_at", *values]
        con.execute(
            f"INSERT INTO {table}({','.join(keys)}) VALUES({','.join('?' for _ in keys)})",
            (record_id, wid, project_id, now, now, *values.values()),
        )
        con.execute(
            "UPDATE designer_projects SET updated_at=? WHERE id=? AND workspace_id=?",
            (now, project_id, wid),
        )
        service.emit("designer_project", project_id, "Добавлено помещение" if kind == "rooms" else "Добавлена позиция комплектации")
        row = service.get(table, record_id)
        return 201, {"room" if kind == "rooms" else "item": dict(row) if kind == "rooms" else _item_view(row)}
    if len(parts) == 4:
        record_id = string(parts[3], "Запись", 100, True)
        row = _room(service, project_id, record_id) if kind == "rooms" else _item(service, project_id, record_id)
        if method == "PATCH":
            _revision(service, row, data)
            if kind == "rooms":
                values = {
                    "name": string(data.get("name", row["name"]), "Название помещения", 120, True),
                    "notes": string(data.get("notes", row["notes"]), "Примечание", 2000),
                }
            else:
                values = _item_data(service, data, row)
            update = ",".join(key + "=?" for key in values)
            con.execute(
                f"UPDATE {table} SET {update},revision=revision+1,updated_at=? WHERE id=? AND workspace_id=? AND project_id=?",
                (*values.values(), stamp(), record_id, wid, project_id),
            )
            con.execute("UPDATE designer_projects SET updated_at=? WHERE id=? AND workspace_id=?", (stamp(), project_id, wid))
            service.emit("designer_project", project_id, "Изменена комплектация")
            return 200, {"room" if kind == "rooms" else "item": dict(service.get(table, record_id)) if kind == "rooms" else _item_view(service.get(table, record_id))}
        if method == "DELETE":
            con.execute(f"DELETE FROM {table} WHERE id=? AND workspace_id=? AND project_id=?", (record_id, wid, project_id))
            con.execute("UPDATE designer_projects SET updated_at=? WHERE id=? AND workspace_id=?", (stamp(), project_id, wid))
            service.emit("designer_project", project_id, "Удалено помещение" if kind == "rooms" else "Удалена позиция комплектации")
            return 200, {"deleted": True}
    raise DomainError(404, "Маршрут не найден")
