"""Immutable client approvals for additional construction work."""

import datetime as dt
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
        result.update({key: row[key] for key in ("protected_quote_id", "internal_cost", "budget_applied_at") if key in row.keys()})
    return result


def protected_preview(service, change):
    service.write_access(True)
    from backend.estimate_workflow import economics, margin_policy
    from backend.quote_integrity import fingerprint
    items, total, cost = calculate(json.loads(change["calculation_json"]) or json.loads(change["items_json"]))
    if total != change["amount_kopecks"]:
        raise DomainError(409, "Пересохраните старые допработы: округлённые цены позиций требуют проверки")
    return {**economics(items, total, cost, margin_policy(service)), "source_sha256": fingerprint(dict(change))}


def fields(data, previous=None):
    if previous and "items" not in data:
        items, total, internal_cost = json.loads(previous["items_json"]), previous["amount_kopecks"], previous["internal_cost"]
        calculation_json = previous["calculation_json"]
    else:
        computed, total, internal_cost = calculate(data.get("items"))
        calculation_json = packed(computed)
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
        items_json=packed(items), calculation_json=calculation_json, amount_kopecks=total, internal_cost=internal_cost,
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
    if not service.finance_visible() and "items" in data and isinstance(data["items"], list):
        data = {**data, "items": [{**item, "cost_price": 0} if isinstance(item, dict) else item for item in data["items"]]}
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
        if isinstance(data.get("items"), list):
            from collections import defaultdict
            costs = defaultdict(list)
            for item in json.loads(change["calculation_json"]):
                costs[(item["name"], item["unit"])].append(item.get("cost_price", 0))
            restored = []
            for item in data["items"]:
                if not isinstance(item, dict):
                    raise DomainError(400, "Проверьте позиции допработ")
                if service.finance_visible() and "cost_price" in item:
                    restored.append(item)
                    continue
                matches = costs[(string(item.get("name", ""), "Позиция", 200), string(item.get("unit", "шт."), "Единица", 30))]
                if len(set(matches)) > 1:
                    raise DomainError(409, "Для повторяющихся позиций укажите закупочные цены явно с доступом к финансам")
                restored.append({**item, "cost_price": matches[0] if matches else 0})
            data = {**data, "items": restored}
        if len(rest) == 3 and rest[2] == "protect-preview" and method == "GET":
            return 200, protected_preview(service, change)
        if len(rest) == 2 and method == "PATCH":
            if change["status"] != "draft":
                raise DomainError(409, "Отправленная версия неизменяема. Создайте новую версию")
            values = fields(data, change)
            service.update("construction_changes", change["id"], values)
            return 200, {"change": view(dict(change, **values))}
        if len(rest) == 3 and rest[2] == "protect" and method == "POST":
            service.write_access(True)
            if change["protected_quote_id"]:
                quote = service.get("quotes", change["protected_quote_id"])
                return 200, {"quote": service.quote_view(quote), "change": view(change)}
            if change["status"] != "draft":
                raise DomainError(409, "Создайте новую версию допработ перед защищённой публикацией")
            if data.get("review_confirmed") is not True:
                raise DomainError(400, "Подтвердите проверку объёмов, технологии и цен допработ")
            preview = protected_preview(service, change)
            if data.get("source_sha256", preview["source_sha256"]) != preview["source_sha256"]:
                raise DomainError(409, "Допработы изменились после проверки. Обновите предложение")
            if not obj["project_id"]:
                raise DomainError(409, "Сначала свяжите объект с заказом, чтобы учесть согласованные допработы")
            project = service.get("projects", obj["project_id"])
            if project["status"] in ("completed", "cancelled"):
                raise DomainError(409, "Заказ уже закрыт")
            client = service.get("clients", obj["client_id"])["name"] if obj["client_id"] else "Заказчик"
            original = json.loads(change["calculation_json"])
            quote = service.create_quote({"title": change["title"][:120], "client": client, "client_id": obj["client_id"],
                "currency": project["currency"], "items": original or json.loads(change["items_json"]),
                "terms": change["description"] + (f"\nК сроку заказа добавляется дней: {change['deadline_days']}." if change["deadline_days"] else "")})
            if quote["amount_kopecks"] != change["amount_kopecks"]:
                raise DomainError(409, "Старая версия округляла цены позиций. Пересохраните проверенные допработы перед публикацией")
            # Lossless calculation rows keep fractional-price rounding and
            # internal costs consistent with the separately agreed supplement.
            service.update("quotes", quote["id"], {"protection_enabled": 1})
            service.publish(service.get("quotes", quote["id"]), {"revision": quote["revision"], "review_confirmed": True,
                            "low_margin_confirmed": data.get("low_margin_confirmed") is True})
            values = {"protected_quote_id": quote["id"], "public_token": None, "status": "sent", "sent_at": stamp(), "updated_at": stamp()}
            service.update("construction_changes", change["id"], values)
            service.emit("construction_change", change["id"], "Допработы опубликованы для защищённого согласования")
            return 200, {"quote": service.quote_view(service.get("quotes", quote["id"])), "change": view(dict(change, **values))}
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
            if change["protected_quote_id"]:
                from backend.protected_estimates import owner_route
                for link in service.con.execute("SELECT id,revision FROM protected_quote_links WHERE quote_id=? AND workspace_id=? AND status='active'", (change["protected_quote_id"], service.wid)).fetchall():
                    owner_route(service, "DELETE", [link["id"]], {}, {"revision": link["revision"]})
                service.con.execute("UPDATE quotes SET approval_state='rejected',status='declined',updated_at=?,revision=revision+1 WHERE id=? AND workspace_id=? AND approval_state IN ('sent','viewed','changes_requested')",
                                    (stamp(), change["protected_quote_id"], service.wid))
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


def protected_decision(service, quote, action, user, comment):
    """Called inside the protected decision transaction, once per accepted quote."""
    change = service.con.execute("SELECT * FROM construction_changes WHERE protected_quote_id=? AND workspace_id=?",
                                 (quote["id"], quote["workspace_id"])).fetchone()
    if not change:
        return
    latest = service.con.execute("SELECT max(version) FROM construction_changes WHERE root_id=? AND workspace_id=?", (change["root_id"], change["workspace_id"])).fetchone()[0]
    if change["status"] != "sent" or latest != change["version"]:
        raise DomainError(409, "Версия допработ больше не ожидает согласования. Запросите актуальное предложение")
    obj = service.con.execute("SELECT * FROM construction_objects WHERE id=? AND workspace_id=?", (change["object_id"], change["workspace_id"])).fetchone()
    if action == "approved" and not change["budget_applied_at"]:
        project = service.con.execute("SELECT * FROM projects WHERE id=? AND workspace_id=?", (obj["project_id"], change["workspace_id"])).fetchone() if obj else None
        if not project or project["status"] in ("completed", "cancelled"):
            raise DomainError(409, "Заказ закрыт или недоступен. Согласуйте условия с исполнителем")
        amount = integer(project["amount_kopecks"] + change["amount_kopecks"], "Новая сумма заказа")
        cost = integer(project["internal_cost"] + change["internal_cost"], "Себестоимость заказа")
        due = (dt.date.fromisoformat(project["due_date"]) + dt.timedelta(days=change["deadline_days"])).isoformat() if project["due_date"] else ""
        service.con.execute("UPDATE projects SET amount_kopecks=?,internal_cost=?,due_date=?,revision=revision+1,updated_at=? WHERE id=? AND workspace_id=?",
                            (amount, cost, due, stamp(), project["id"], change["workspace_id"]))
        service.con.execute("UPDATE construction_changes SET budget_applied_at=? WHERE id=? AND workspace_id=?", (stamp(), change["id"], change["workspace_id"]))
        service.insert("project_stages", {"id": identity(), "workspace_id": change["workspace_id"], "project_id": project["id"],
            "name": change["title"], "description": "Согласованные допработы, версия " + str(change["version"]),
            "due_date": due, "amount_kopecks": change["amount_kopecks"], "status": "planned", "revision": 1,
            "created_at": stamp(), "updated_at": stamp()})
    service.con.execute("UPDATE construction_changes SET status=?,response_name=?,response_comment=?,decided_at=?,updated_at=? WHERE id=? AND workspace_id=?",
                        ("declined" if action == "rejected" else action, user["name"], comment, stamp(), stamp(), change["id"], change["workspace_id"]))


def public(service, method, path, query):
    service.h.throttle("public-change:" + service.h.client_address[0], 90, 60)
    data = service.h.body() if method == "POST" else {}
    token = string(data.get("token", query.get("token", [""])[0]), "Ссылка", 100, True)
    candidate = service.con.execute(
        "SELECT id,workspace_id FROM construction_changes "
        "WHERE public_token=? AND status!='draft' AND protected_quote_id IS NULL",
        (token,),
    ).fetchone()
    if not candidate:
        raise DomainError(404, "Допработы не найдены")
    lock_scope = (
        f"workspace:{candidate['workspace_id']}"
        if candidate["workspace_id"]
        else f"construction-change:{candidate['id']}"
    )
    with transaction(service.con, lock_scopes=(lock_scope,)):
        row = service.con.execute(
            "SELECT * FROM construction_changes WHERE public_token=? AND status!='draft' AND protected_quote_id IS NULL", (token,),
        ).fetchone()
        if not row:
            raise DomainError(404, "Допработы не найдены")
        if row["workspace_id"] != candidate["workspace_id"]:
            raise DomainError(409, "Допработы изменились. Обновите ссылку")
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
