"""Immutable client approvals for additional construction work."""

import json
import secrets
from decimal import Decimal, ROUND_HALF_UP

from backend.business import DomainError, calculate, choice, identity, integer, packed, stamp, string, transaction


def view(row, public=False):
    result = {key: row[key] for key in (
        "id", "object_id", "root_id", "version", "title", "description",
        "amount_kopecks", "deadline_days", "status", "response_name",
        "response_comment", "sent_at", "decided_at", "expires_at", "created_at", "updated_at",
    )}
    result["items"] = json.loads(row["items_json"])
    if not public:
        result["public_token"] = row["public_token"]
    return result


def fields(data, previous=None):
    if previous and "items" not in data:
        items, total = json.loads(previous["items_json"]), previous["amount_kopecks"]
    else:
        computed, total, _ = calculate(data.get("items"))
        items = []
        for item in computed:
            if not item["included"]:
                continue
            quantity = Decimal(item["quantity"])
            effective_price = int((Decimal(item["subtotal"]) / quantity).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            items.append({
                "name": item["name"], "description": item["description"], "unit": item["unit"],
                "quantity": item["quantity"], "unit_price": effective_price,
                "subtotal": item["subtotal"],
            })
    if not items:
        raise DomainError(400, "Добавьте хотя бы одну работу")
    return dict(
        title=string(data.get("title", previous["title"] if previous else ""), "Название допработ", 200, True),
        description=string(data.get("description", previous["description"] if previous else ""), "Описание", 2000),
        items_json=packed(items), amount_kopecks=total,
        deadline_days=integer(data.get("deadline_days", previous["deadline_days"] if previous else 0),
                              "Изменение срока", 0, 365),
        updated_at=stamp(),
    )


def list_changes(service, obj):
    return [view(row) for row in service.con.execute(
        "SELECT * FROM construction_changes WHERE object_id=? AND workspace_id=? "
        "ORDER BY created_at DESC,version DESC,id DESC LIMIT 200",
        (obj["id"], service.wid),
    )]


def route(service, obj, method, rest, data):
    if rest == ["changes"] and method == "POST":
        count = service.con.execute("SELECT count(*) FROM construction_changes WHERE object_id=? AND workspace_id=?",
                                    (obj["id"], service.wid)).fetchone()[0]
        if count >= 200:
            raise DomainError(409, "На объекте может быть не больше 200 версий допработ")
        change_id = identity()
        values = dict(id=change_id, workspace_id=service.wid, object_id=obj["id"],
                      root_id=change_id, version=1, status="draft", public_token=None,
                      response_name="", response_comment="", sent_at=None, decided_at=None,
                      expires_at=None, created_at=stamp(), **fields(data))
        service.insert("construction_changes", values)
        service.emit("construction_change", change_id, "Черновик допработ создан")
        return 201, {"change": view(values)}
    if len(rest) >= 2 and rest[0] == "changes":
        change = service.con.execute(
            "SELECT * FROM construction_changes WHERE id=? AND object_id=? AND workspace_id=?",
            (rest[1], obj["id"], service.wid),
        ).fetchone()
        if not change:
            raise DomainError(404, "Допработы не найдены")
        if len(rest) == 2 and method == "PATCH":
            if change["status"] != "draft":
                raise DomainError(409, "Отправленная версия неизменяема. Создайте новую версию")
            values = fields(data, change)
            service.update("construction_changes", change["id"], values)
            return 200, {"change": view(dict(change, **values))}
        if len(rest) == 2 and method == "DELETE":
            if change["status"] != "draft":
                raise DomainError(409, "Отправленную версию нельзя удалить")
            service.con.execute("DELETE FROM construction_changes WHERE id=? AND workspace_id=?",
                                (change["id"], service.wid))
            return 200, {"ok": True}
        if len(rest) == 3 and rest[2] == "send" and method == "POST":
            if change["status"] != "draft":
                raise DomainError(409, "Эта версия уже отправлена")
            values = dict(status="sent", public_token=secrets.token_urlsafe(32),
                          sent_at=stamp(), expires_at=stamp() + 30 * 86400, updated_at=stamp())
            service.update("construction_changes", change["id"], values)
            service.emit("construction_change", change["id"], "Допработы отправлены клиенту")
            return 200, {"change": view(dict(change, **values))}
        if len(rest) == 3 and rest[2] == "revoke" and method == "POST":
            if change["status"] != "sent":
                raise DomainError(409, "Отозвать можно только ожидающую версию")
            values = dict(status="declined", public_token=None, response_comment="Ссылка отозвана исполнителем",
                          decided_at=stamp(), updated_at=stamp())
            service.update("construction_changes", change["id"], values)
            service.emit("construction_change", change["id"], "Ссылка согласования отозвана")
            return 200, {"change": view(dict(change, **values))}
        if len(rest) == 3 and rest[2] == "revise" and method == "POST":
            if change["status"] not in ("changes_requested", "declined"):
                raise DomainError(409, "Новая версия доступна после ответа клиента")
            latest = service.con.execute(
                "SELECT max(version) FROM construction_changes WHERE root_id=? AND workspace_id=?",
                (change["root_id"], service.wid),
            ).fetchone()[0]
            if change["version"] != latest or latest >= 100:
                raise DomainError(409, "Уже есть более новая версия")
            values = dict(id=identity(), workspace_id=service.wid, object_id=obj["id"],
                          root_id=change["root_id"], version=latest + 1, status="draft", public_token=None,
                          response_name="", response_comment="", sent_at=None, decided_at=None,
                          expires_at=None, created_at=stamp(), **fields(data, change))
            service.insert("construction_changes", values)
            service.emit("construction_change", values["id"], "Новая версия допработ создана")
            return 201, {"change": view(values)}
    raise DomainError(404, "Действие не найдено")


def public(service, method, path, query):
    service.h.throttle("public-change:" + service.h.client_address[0], 90, 60)
    data = service.h.body() if method == "POST" else {}
    token = string(data.get("token", query.get("token", [""])[0]), "Ссылка", 100, True)
    with transaction(service.con):
        row = service.con.execute(
            "SELECT * FROM construction_changes WHERE public_token=? AND status!='draft'", (token,),
        ).fetchone()
        if not row:
            raise DomainError(404, "Допработы не найдены")
        if method == "GET" and path == "/api/public/change":
            return 200, {"change": view(row, public=True)}
        if method == "POST" and path == "/api/public/change/respond":
            if row["status"] != "sent":
                raise DomainError(409, "Решение по этой версии уже принято")
            if row["expires_at"] < stamp():
                raise DomainError(410, "Срок согласования истёк")
            decision = choice(data.get("action"), ("approved", "changes_requested", "declined"), "Решение")
            name = string(data.get("name", ""), "Имя", 120, True)
            comment = string(data.get("comment", ""), "Комментарий", 2000)
            if decision == "changes_requested" and not comment:
                raise DomainError(400, "Опишите необходимые изменения")
            service.con.execute(
                "UPDATE construction_changes SET status=?,response_name=?,response_comment=?,decided_at=?,updated_at=? "
                "WHERE id=? AND status='sent'",
                (decision, name, comment, stamp(), stamp(), row["id"]),
            )
            return 200, {"change": view(dict(row, status=decision, response_name=name,
                                            response_comment=comment, decided_at=stamp()), public=True)}
    raise DomainError(404, "Действие не найдено")
