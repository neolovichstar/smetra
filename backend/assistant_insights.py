"""Bounded, read-only assistant tools backed by workspace-scoped domain APIs.

Every monetary value returned here is in kopecks, never inferred by the model.
"""

import datetime as dt
import re

from backend.business import DomainError, string


READ_NAMES = frozenset({
    "list_records", "get_record", "overview", "read_file", "read_markdown",
    "list_files", "search_knowledge", "search_file_content",
    "list_construction_objects", "get_construction_object",
    "calculate_construction", "get_file_metadata", "get_document",
    "list_documents", "search_workspace", "find_catalog_prices",
    "catalog_price_history", "audit_quote", "compare_quote_versions",
    "project_finances", "deadline_radar",
})

NEW_READ_NAMES = frozenset({
    "search_workspace", "find_catalog_prices", "catalog_price_history",
    "audit_quote", "compare_quote_versions", "project_finances", "deadline_radar",
})


def _id(args, label="ID"):
    return string(args.get("id", ""), label, 80, True)


def _search(args):
    query = string(args.get("query", ""), "Поиск", 100, True).strip()
    if len(query) < 2:
        raise DomainError(400, "Для поиска нужны хотя бы два символа")
    return query


def _price_fields(row):
    return {key: row.get(key) for key in (
        "id", "name", "article", "category", "unit", "price",
        "cost_price", "updated_at", "revision",
    ) if key in row}


def read(service, name, args):
    """Only accepts registered read operations; never mutates business data."""
    if name not in NEW_READ_NAMES:
        raise DomainError(400, "Неизвестный инструмент чтения")

    if name == "search_workspace":
        query = _search(args)
        result = service.route("GET", "search", [], {"q": [query]}, {})[1]
        return {"query": query, "results": result.get("items", [])[:40]}

    if name == "find_catalog_prices":
        query = _search(args)
        result = service.route("GET", "catalog", [], {"q": [query]}, {})[1]
        return {"query": query, "items": [_price_fields(row) for row in result["items"][:15]],
                "has_more": len(result["items"]) > 15,
                "price_unit": "kopecks", "source": "workspace_catalog"}

    if name == "catalog_price_history":
        record = service.route("GET", "catalog", [_id(args, "Позиция")], {}, {})[1]["item"]
        return {"item": _price_fields(record), "price_unit": "kopecks",
                "history": [{key: row[key] for key in (
                    "price", "cost_price", "item_revision", "created_at",
                ) if key in row} for row in record.get("price_history", [])[:20]]}

    if name == "audit_quote":
        quote = service.quote_view(service.get("quotes", _id(args, "Смета")))
        items = quote.get("items", [])
        problems = []
        for index, item in enumerate(items, 1):
            if not str(item.get("name") or "").strip():
                problems.append({"row": index, "issue": "missing_name"})
            if item.get("unit_price") == 0 and item.get("included", True):
                problems.append({"row": index, "issue": "zero_price"})
            if not str(item.get("unit", "")).strip():
                problems.append({"row": index, "issue": "missing_unit"})
            if item.get("optional") and not item.get("included", True):
                problems.append({"row": index, "issue": "excluded_option"})
        return {
            "id": quote["id"], "title": quote["title"],
            "currency": quote["currency"], "revision": quote["revision"],
            "status": quote["status"], "approval_state": quote["approval_state"],
            "amount_kopecks": quote["amount_kopecks"],
            "internal_cost_kopecks": quote["internal_cost"],
            "profit_kopecks": quote["profit"],
            "item_count": len(items),
            "included_count": sum(bool(item.get("included", True)) for item in items),
            "issues": problems[:40], "more_issues": len(problems) > 40,
            "totals_source": "server_authoritative",
            "note": "Замечания — сигналы для проверки, не автоматические ошибки",
        }

    if name == "compare_quote_versions":
        quote_id = _id(args, "Смета")
        source = str(args.get("from_version", ""))
        target = str(args.get("to_version", "current"))
        valid = lambda v: bool(re.fullmatch(r"[1-9][0-9]{0,8}", v))
        if not valid(source) or (target != "current" and not valid(target)):
            raise DomainError(400, "Укажите существующую версию и версию для сравнения")
        return service.route("GET", "quotes", [quote_id, "compare"],
                             {"from": [source], "to": [target]}, {})[1]

    if name == "project_finances":
        project = service.route("GET", "projects", [_id(args, "Заказ")], {}, {})[1]["item"]
        planned = project["amount_kopecks"]
        paid = project["paid"]
        spent = project["actual_cost"]
        return {
            "id": project["id"], "name": project["name"],
            "currency": project["currency"], "status": project["status"],
            "planned_revenue_kopecks": planned,
            "planned_cost_kopecks": project.get("internal_cost"),
            "paid_kopecks": paid, "expenses_kopecks": spent,
            "unpaid_kopecks": max(0, planned - paid),
            "cash_position_kopecks": paid - spent,
            "payment_count": len(project["payments"]),
            "expense_count": len(project["expenses"]),
            "source": "workspace_project_ledger",
        }

    if name == "deadline_radar":
        days = args.get("days", 30)
        if type(days) is not int or not 1 <= days <= 365:
            raise DomainError(400, "Период должен быть от 1 до 365 дней")
        today = dt.date.today()
        horizon = today + dt.timedelta(days=days)
        # Filter in SQL before limiting, so old overdue tasks cannot hide upcoming ones.
        sql = (
            "SELECT id,name,due_date,status,'project' AS kind FROM projects "
            "WHERE workspace_id=? AND due_date!='' AND due_date<=? "
            "AND status NOT IN ('completed','cancelled') "
            "UNION ALL "
            "SELECT id,name,due_date,status,'task' AS kind FROM tasks "
            "WHERE workspace_id=? AND due_date!='' AND due_date<=? AND status!='done' "
            "ORDER BY due_date LIMIT 60"
        )
        rows = [dict(row) for row in service.con.execute(
            sql, (service.wid, horizon.isoformat(), service.wid, horizon.isoformat()),
        )]
        for row in rows:
            row["overdue"] = row["due_date"] < today.isoformat()
        return {"as_of": today.isoformat(), "through": horizon.isoformat(),
                "deadlines": rows[:40], "has_more": len(rows) > 40}
    raise DomainError(400, "Неизвестный инструмент чтения")
