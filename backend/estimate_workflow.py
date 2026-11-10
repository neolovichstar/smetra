"""Private, deterministic profitability and estimate workflow operations."""
import json
from decimal import Decimal

from backend.business import DomainError, calculate, decimal, integer, packed, stamp, string
from backend.quote_integrity import fingerprint


def project_money(service, project):
    from backend.order_finance import summarize
    totals = service.con.execute(
        "SELECT (SELECT coalesce(sum(amount_kopecks),0) FROM project_payments WHERE project_id=? AND workspace_id=?) AS paid,"
        "(SELECT coalesce(sum(amount_kopecks),0) FROM expenses WHERE project_id=? AND workspace_id=?) AS actual_cost",
        (project["id"], service.wid, project["id"], service.wid),
    ).fetchone()
    return summarize(project["amount_kopecks"], project["internal_cost"], totals["paid"], totals["actual_cost"], json.loads(project["cost_forecast"]))


def forecast(service, method, project_id, data):
    project = service.get("projects", project_id)
    if method == "PATCH":
        service.check_revision(project, data)
        if project["status"] in ("completed", "cancelled"):
            raise DomainError(409, "Заказ закрыт. Фактический результат берётся из записанных расходов")
        remaining = integer(data.get("remaining_cost"), "Расходы до завершения", 0)
        committed = integer(data.get("committed_cost", 0), "Обязательства в остатке", 0)
        if committed > remaining:
            raise DomainError(400, "Обязательства входят в оставшиеся расходы и не могут превышать их")
        values = {"remaining_cost": remaining, "committed_cost": committed,
                  "note": string(data.get("note", ""), "Основание прогноза", 2000), "updated_at": stamp(), "updated_by": service.user["id"]}
        values["actual_cost_at_update"] = project_money(service, project)["actual_cost"]
        values.update(revenue_at_update=project["amount_kopecks"], planned_cost_at_update=project["internal_cost"])
        service.update("projects", project_id, {"cost_forecast": packed(values), "revision": project["revision"] + 1, "updated_at": stamp()})
        service.emit("project", project_id, "Прогноз расходов обновлён")
        project = service.get("projects", project_id)
    elif method != "GET":
        raise DomainError(405, "Метод не поддерживается")
    return 200, {"project_id": project_id, "revision": project["revision"], "currency": project["currency"],
                 "cost_forecast": json.loads(project["cost_forecast"]), "finance": project_money(service, project)}


def margin_policy(service):
    settings = json.loads(service.con.execute("SELECT settings FROM workspaces WHERE id=?", (service.wid,)).fetchone()["settings"])
    return decimal(settings.get("minimum_margin_pct", "0"), "Минимальная маржа", "0", "100")


def economics(items, amount, internal_cost, floor):
    known = bool(items) and all(row.get("cost_price", 0) > 0 for row in items if row.get("included", True))
    profit = amount - internal_cost if known else None
    margin = str((Decimal(profit) * 100 / amount).quantize(Decimal("0.01"))) if known and amount else None
    return {"amount_kopecks": amount, "internal_cost": internal_cost, "profit": profit, "margin_pct": margin,
            "minimum_margin_pct": str(floor), "cost_complete": known,
            "below_minimum": bool(known and Decimal(profit) * 100 < Decimal(amount) * floor)}


def publication_guard(service, quote, data):
    alternative_guard(service.con, quote, service.wid)
    policy = margin_policy(service)
    result = economics(quote["items"], quote["amount_kopecks"], quote["internal_cost"], policy)
    if result["below_minimum"]:
        if service.role not in ("owner", "admin", "manager") or data.get("low_margin_confirmed") is not True:
            raise DomainError(409, "Маржа ниже установленного минимума. Руководитель должен отдельно подтвердить публикацию")
        service.emit("quote", quote["id"], "Публикация с маржой ниже установленного минимума подтверждена", str(result["margin_pct"]) + "%")


def alternative_guard(con, quote, workspace_id=None):
    root = quote.get("alternative_root_id") if isinstance(quote, dict) else quote["alternative_root_id"]
    if root and con.execute("SELECT 1 FROM quotes WHERE alternative_root_id=? AND workspace_id=? AND approval_state='approved' AND id<>?",
                            (root, workspace_id or quote["workspace_id"], quote["id"])).fetchone():
        raise DomainError(409, "По этому предложению уже выбран другой вариант")


def alternative_decision(service, quote, action):
    if not quote["alternative_root_id"] or action != "approved":
        return
    alternative_guard(service.con, quote)
    service.con.execute("UPDATE quotes SET approval_state='rejected',status='declined',updated_at=?,revision=revision+1 WHERE alternative_root_id=? AND workspace_id=? AND id<>? AND approval_state<>'approved'",
                        (stamp(), quote["alternative_root_id"], quote["workspace_id"], quote["id"]))
    service.con.execute("UPDATE protected_quote_links SET proposal_state='rejected',updated_at=? WHERE workspace_id=? AND quote_id IN (SELECT id FROM quotes WHERE alternative_root_id=? AND workspace_id=? AND id<>?)",
                        (stamp(), quote["workspace_id"], quote["alternative_root_id"], quote["workspace_id"], quote["id"]))


def alternatives(service, method, quote_id, data, apply=False):
    quote = service.get("quotes", quote_id)
    root = quote["alternative_root_id"] or quote["id"]
    if method == "GET":
        return 200, {"quotes": [service.quote_view(row) for row in service.con.execute(
            "SELECT * FROM quotes WHERE workspace_id=? AND (alternative_root_id=? OR id=?) ORDER BY created_at,id", (service.wid, root, root))]}
    if method != "POST":
        raise DomainError(405, "Метод не поддерживается")
    service.check_revision(quote, data)
    if quote["approval_state"] != "draft" or quote["alternative_root_id"]:
        raise DomainError(409, "Создайте варианты из отдельного черновика до публикации")
    supplied = data.get("variants")
    if not isinstance(supplied, list) or not 1 <= len(supplied) <= 2:
        raise DomainError(400, "Добавьте один или два варианта к исходной смете")
    original = service.quote_view(quote)
    root_label = string(data.get("root_label", "Исходный вариант"), "Название варианта", 80, True)
    seen, labels, variants = set(), {root_label.casefold()}, []
    for variant in [{"label": root_label, "items": original["items"]}, *supplied]:
        if not isinstance(variant, dict):
            raise DomainError(400, "Проверьте варианты предложения")
        label = string(variant.get("label", ""), "Название варианта", 80, True)
        items, total, cost = calculate(variant.get("items"))
        # Only client-facing composition and prices distinguish an offer.
        signature = fingerprint({"items": [{key: item[key] for key in ("name", "quantity", "unit", "unit_price", "discount", "tax", "coefficient", "markup")} for item in items if item["included"]]})
        if signature in seen:
            raise DomainError(409, "Варианты совпадают. Измените состав или цену перед созданием")
        seen.add(signature)
        if variants:
            if label.casefold() in labels:
                raise DomainError(400, "Названия вариантов должны отличаться")
            labels.add(label.casefold())
        variants.append({"label": label, "items": items, "amount_kopecks": total, "internal_cost": cost})
    if not apply:
        return 200, {"variants": variants, "quote_id": quote_id, "revision": quote["revision"], "currency": quote["currency"]}
    if data.get("confirmation") is not True:
        raise DomainError(400, "Подтвердите создание вариантов после проверки состава и цен")
    results = []
    for variant in variants[1:]:
        created = service.create_quote({**original, "title": (quote["title"][:90] + " · " + variant["label"])[:120], "items": variant["items"]}, trusted_ai_generated=bool(quote["ai_generated"] or getattr(service, "assistant_workflow_creation", False)))
        service.update("quotes", created["id"], {"alternative_root_id": root, "alternative_label": variant["label"], "protection_enabled": 1})
        results.append(service.quote_view(service.get("quotes", created["id"])))
    service.update("quotes", quote_id, {"alternative_root_id": root, "alternative_label": root_label, "protection_enabled": 1,
                                        "revision": quote["revision"] + 1, "updated_at": stamp()})
    service.emit("quote", quote_id, "Варианты предложения созданы", "Согласование одного варианта закрывает остальные")
    return 201, {"quotes": [service.quote_view(service.get("quotes", quote_id)), *results]}


def discount(service, quote_id, data, apply=False):
    quote = service.get("quotes", quote_id)
    service.check_revision(quote, data)
    if quote["approval_state"] == "approved":
        raise DomainError(409, "Согласованная смета защищена. Создайте копию")
    current = service.quote_view(quote)
    if not current["items"]:
        raise DomainError(409, "Для скидки нужны позиции сметы")
    percent = decimal(data.get("percent"), "Дополнительная скидка", "0.01", "99.99")
    floor = margin_policy(service)
    rows = [{**item, "discount": str(100 - (100 - Decimal(item["discount"])) * (100 - percent) / 100)} for item in current["items"]]
    items, total, cost = calculate(rows, allow_zero_total=True)
    before = economics(current["items"], current["amount_kopecks"], current["internal_cost"], floor)
    after = economics(items, total, cost, floor)
    if apply:
        if data.get("confirmation") is not True:
            raise DomainError(400, "Подтвердите скидку после проверки влияния на прибыль")
        if after["below_minimum"] and data.get("low_margin_confirmed") is not True:
            raise DomainError(409, "Скидка снизит маржу ниже минимума. Подтвердите это отдельно")
        result = service.route("PATCH", "quotes", [quote_id], {}, {"revision": quote["revision"], "items": items})
        service.emit("quote", quote_id, "Скидка подтверждена", str(percent) + "%")
        return result
    return 200, {"quote_id": quote_id, "revision": quote["revision"], "currency": quote["currency"], "percent": str(percent),
                 "before": before, "after": after, "profit_reduction": before["profit"] - after["profit"] if before["profit"] is not None else None,
                 "note": "Себестоимость не уменьшается при скидке. При неполных закупочных ценах прибыль неизвестна."}


def route(service, method, parts, data):
    service.write_access(True)
    if parts and parts[0] in ("rates", "actual-cost", "learn-rate"):
        from backend.actual_rates import route as rates_route
        return rates_route(service, method, parts, data)
    if len(parts) == 2 and parts[0] == "forecast":
        return forecast(service, method, parts[1], data)
    if parts == ["margin-policy"]:
        if method == "PATCH":
            value = decimal(data.get("minimum_margin_pct"), "Минимальная маржа", "0", "100")
            settings = json.loads(service.con.execute("SELECT settings FROM workspaces WHERE id=?", (service.wid,)).fetchone()["settings"])
            settings["minimum_margin_pct"] = str(value)
            service.con.execute("UPDATE workspaces SET settings=? WHERE id=?", (packed(settings), service.wid))
            service.emit("workspace", service.wid, "Минимальная маржа изменена", str(value) + "%")
        elif method != "GET":
            raise DomainError(405, "Метод не поддерживается")
        return 200, {"minimum_margin_pct": str(margin_policy(service))}
    if method == "GET" and len(parts) == 2 and parts[0] == "economics":
        quote = service.quote_view(service.get("quotes", parts[1]))
        return 200, {"quote_id": quote["id"], "revision": quote["revision"], "currency": quote["currency"],
                     **economics(quote["items"], quote["amount_kopecks"], quote["internal_cost"], margin_policy(service))}
    if method == "POST" and len(parts) in (2, 3) and parts[0] == "discount" and (len(parts) == 2 or parts[2] == "apply"):
        return discount(service, parts[1], data, apply=len(parts) == 3)
    if len(parts) in (2, 3) and parts[0] == "alternatives" and (len(parts) == 2 or parts[2] == "apply"):
        return alternatives(service, method, parts[1], data, apply=len(parts) == 3)
    raise DomainError(404, "Действие не найдено")
