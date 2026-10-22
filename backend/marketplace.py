"""Authenticated, privacy-safe construction lead marketplace endpoints."""
import datetime as dt
import re
import uuid

try:
    from backend import business
except ModuleNotFoundError:
    import business


def _now(handler):
    return __import__("time").time_ns() // 1_000_000_000


def _error(status, message):
    try:
        from backend.app import ApiError
    except ModuleNotFoundError:
        from app import ApiError
    return ApiError(status, message)


def _id():
    return str(uuid.uuid4())


def _lead(row):
    # Contact fields are deliberately excluded from every public lead representation.
    return {
        "id": row["id"],
        "city": row["city"],
        "property_type": row["property_type"],
        "area_sqm": row["area_sqm"],
        "budget_min_kopecks": row["budget_min_kopecks"],
        "budget_max_kopecks": row["budget_max_kopecks"],
        "description": row["description"],
        "desired_start_date": row["desired_start_date"],
        "status": row["status"],
        "published_at": row["published_at"],
        "expires_at": row["expires_at"],
        "created_at": row["created_at"],
    }


def _query(query, name, default=""):
    value = query.get(name, default)
    return value[0] if isinstance(value, list) and value else value


def _contact(row):
    return {
        "name": row["contact_name"],
        "phone": row["phone"],
        "email": row["email"],
        "preferred_contact_method": row["preferred_contact_method"],
    }


def handle(handler, con, user, method, path, query):
    now = _now(handler)
    prefix = "/api/marketplace/"

    if path == prefix + "leads" and method == "GET":
        handler.throttle("marketplace-feed:" + user["id"], 120, 60)
        city = business.string(_query(query, "city"), "Город", 120)
        try:
            limit = max(1, min(50, int(_query(query, "limit", "30"))))
        except (TypeError, ValueError):
            raise _error(400, "Некорректный лимит выдачи")
        select = (
            "SELECT id,city,property_type,area_sqm,budget_min_kopecks,budget_max_kopecks,"
            "description,desired_start_date,status,published_at,expires_at,created_at "
            "FROM marketplace_leads WHERE status='published' AND (expires_at IS NULL OR expires_at>?)"
        )
        if city:
            rows = con.execute(
                select + " AND lower(city)=lower(?) ORDER BY published_at DESC,id DESC LIMIT ?",
                (now, city, limit),
            ).fetchall()
        else:
            rows = con.execute(
                select + " ORDER BY published_at DESC,id DESC LIMIT ?",
                (now, limit),
            ).fetchall()
        balance = con.execute(
            "SELECT lead_token_balance FROM users WHERE id=?", (user["id"],)
        ).fetchone()
        return handler.send_json(200, {
            "items": [_lead(row) for row in rows],
            "lead_token_balance": int(balance["lead_token_balance"] if balance else 0),
            "unlock_price_tokens": 150,
            "topup_plan": "lead_tokens_150",
        })

    if path == prefix + "leads" and method == "POST":
        handler.throttle("marketplace-create:" + user["id"], 5, 3600)
        data = handler.body()
        city = business.string(data.get("city"), "Город", 120, True)
        property_type = data.get("property_type", "apartment")
        if property_type not in ("apartment", "house", "commercial", "other"):
            raise _error(400, "Неизвестный тип объекта")
        description = business.string(data.get("description", ""), "Описание объекта", 5000)
        contact_name = business.string(data.get("contact_name", user["name"]), "Контактное имя", 120, True)
        phone = business.string(data.get("phone", ""), "Телефон", 50)
        email = business.string(data.get("email", ""), "Электронная почта", 254)
        if not phone and not email:
            raise _error(400, "Укажите телефон или электронную почту для связи")
        area = data.get("area_sqm")
        if area is not None:
            if isinstance(area, bool):
                raise _error(400, "Некорректная площадь объекта")
            try:
                area = float(area)
            except (TypeError, ValueError):
                raise _error(400, "Некорректная площадь объекта")
            if not (0 < area <= 100000):
                raise _error(400, "Площадь должна быть от 0 до 100 000 м²")
            area = str(area)

        budget_min = data.get("budget_min_kopecks")
        budget_max = data.get("budget_max_kopecks")
        for label, value in (("Минимальный бюджет", budget_min), ("Максимальный бюджет", budget_max)):
            if value is not None and (type(value) is not int or not 0 <= value <= 100_000_000_000):
                raise _error(400, "Некорректное поле «" + label + "»")
        if budget_min is not None and budget_max is not None and budget_max < budget_min:
            raise _error(400, "Максимальный бюджет не может быть меньше минимального")
        desired_date = data.get("desired_start_date")
        if desired_date:
            if not isinstance(desired_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", desired_date):
                raise _error(400, "Дата начала работ должна быть в формате ГГГГ-ММ-ДД")
            try:
                dt.date.fromisoformat(desired_date)
            except ValueError:
                raise _error(400, "Некорректная дата начала работ")
        quote_id = data.get("source_quote_id") or None
        if quote_id is not None:
            if not isinstance(quote_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", quote_id):
                raise _error(400, "Некорректная ссылка на смету")
            accessible = con.execute(
                "SELECT 1 FROM quotes q LEFT JOIN workspace_members m "
                "ON m.workspace_id=q.workspace_id AND m.user_id=? "
                "WHERE q.id=? AND (q.user_id=? OR m.user_id=?) LIMIT 1",
                (user["id"], quote_id, user["id"], user["id"]),
            ).fetchone()
            if not accessible:
                raise _error(404, "Исходная смета не найдена")

        lead_id = _id()
        stamp = now
        with business.transaction_lock_scope(con, (f"user:{user['id']}",)):
            con.execute("BEGIN IMMEDIATE")
            try:
                # Create as draft first to respect runtime RLS; publish only as its owner.
                con.execute(
                    "INSERT INTO marketplace_leads(id,created_by,source_quote_id,city,property_type,area_sqm,"
                    "budget_min_kopecks,budget_max_kopecks,description,desired_start_date,status,published_at,"
                    "expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,'draft',NULL,?,?,?)",
                    (lead_id, user["id"], quote_id, city, property_type, area, budget_min, budget_max,
                     description, desired_date or None, stamp + 30 * 86400, stamp, stamp),
                )
                preferred = data.get("preferred_contact_method")
                if preferred not in ("phone", "email", "messenger"):
                    preferred = "email" if email and not phone else "phone"
                con.execute(
                    "INSERT INTO marketplace_lead_contacts(lead_id,contact_name,phone,email,preferred_contact_method,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (lead_id, contact_name, phone or None, email or None, preferred, stamp, stamp),
                )
                con.execute(
                    "UPDATE marketplace_leads SET status='published',published_at=?,updated_at=? "
                    "WHERE id=? AND created_by=?",
                    (stamp, stamp, lead_id, user["id"]),
                )
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        row = con.execute(
            "SELECT id,city,property_type,area_sqm,budget_min_kopecks,budget_max_kopecks,description,"
            "desired_start_date,status,published_at,expires_at,created_at FROM marketplace_leads WHERE id=?",
            (lead_id,),
        ).fetchone()
        return handler.send_json(201, {"lead": _lead(row)})

    if path == prefix + "purchases" and method == "GET":
        handler.throttle("marketplace-purchases:" + user["id"], 60, 60)
        rows = con.execute(
            "SELECT l.id,l.city,l.property_type,l.area_sqm,l.budget_min_kopecks,l.budget_max_kopecks,"
            "l.description,l.desired_start_date,l.status,l.published_at,l.expires_at,l.created_at,"
            "p.purchased_at,p.price_kopecks,p.tokens_spent,c.contact_name,c.phone,c.email,c.preferred_contact_method "
            "FROM lead_purchases p JOIN marketplace_leads l ON l.id=p.lead_id "
            "JOIN marketplace_lead_contacts c ON c.lead_id=l.id "
            "WHERE p.buyer_user_id=? ORDER BY p.purchased_at DESC LIMIT 100",
            (user["id"],),
        ).fetchall()
        return handler.send_json(200, {"items": [
            {**_lead(row), "purchased_at": row["purchased_at"], "price_kopecks": row["price_kopecks"],
             "tokens_spent": row["tokens_spent"], "contact": _contact(row)}
            for row in rows
        ]})

    parts = path.strip("/").split("/")
    if len(parts) == 5 and parts[:3] == ["api", "marketplace", "leads"] and parts[4] == "purchase" and method == "POST":
        lead_id = parts[3]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", lead_id):
            raise _error(400, "Некорректный идентификатор заказа")
        idem = handler.headers.get("Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", idem):
            raise _error(400, "Для покупки нужен корректный Idempotency-Key")
        handler.throttle("marketplace-purchase:" + user["id"], 10, 60)
        team = con.execute(
            "SELECT w.id FROM workspaces w JOIN workspace_members m ON m.workspace_id=w.id "
            "WHERE m.user_id=? AND w.plan='pro_team' AND w.subscription_status='active' AND w.entitlement_until>? "
            "ORDER BY CASE WHEN m.role='owner' THEN 0 ELSE 1 END,w.id LIMIT 1",
            (user["id"], now),
        ).fetchone()
        solo_active = user["plan"] == "pro" and int(user["entitlement_until"] or 0) > now
        if not solo_active and not team:
            raise _error(403, "Открытие контактов доступно только владельцам активного PRO Solo или участникам PRO Team")
        workspace_id = team["id"] if team else business.ensure_workspace(con, user)
        stamp = now
        purchase_id = _id()
        with business.transaction_lock_scope(con, (f"user:{user['id']}", f"lead:{lead_id}")):
            con.execute("BEGIN IMMEDIATE")
            try:
                existing = con.execute(
                    "SELECT id,lead_id FROM lead_purchases WHERE buyer_user_id=? AND idempotency_key=?",
                    (user["id"], idem),
                ).fetchone()
                if existing and existing["lead_id"] != lead_id:
                    raise _error(409, "Этот ключ идемпотентности уже использован для другого заказа")
                if not existing:
                    existing = con.execute(
                        "SELECT id FROM lead_purchases WHERE lead_id=? AND buyer_user_id=?",
                        (lead_id, user["id"]),
                    ).fetchone()
                if existing:
                    purchase_id = existing["id"]
                else:
                    lead = con.execute(
                        "SELECT id FROM marketplace_leads WHERE id=? AND status='published' "
                        "AND (expires_at IS NULL OR expires_at>?)",
                        (lead_id, stamp),
                    ).fetchone()
                    if not lead:
                        raise _error(404, "Опубликованный заказ не найден или срок публикации истёк")
                    changed = con.execute(
                        "UPDATE users SET lead_token_balance=lead_token_balance-150,lead_token_balance_updated_at=? "
                        "WHERE id=? AND lead_token_balance>=150 AND deleted_at IS NULL AND blocked=0",
                        (stamp, user["id"]),
                    )
                    if changed.rowcount != 1:
                        raise _error(402, "Недостаточно токенов. Пополните баланс пакетом 150 токенов за 150 ₽.")
                    balance = con.execute(
                        "SELECT lead_token_balance FROM users WHERE id=?", (user["id"],)
                    ).fetchone()["lead_token_balance"]
                    con.execute(
                        "INSERT INTO lead_purchases(id,lead_id,buyer_user_id,buyer_workspace_id,price_kopecks,tokens_spent,idempotency_key,purchased_at) "
                        "VALUES(?,?,?,?,15000,150,?,?)",
                        (purchase_id, lead_id, user["id"], workspace_id, idem, stamp),
                    )
                    con.execute(
                        "INSERT INTO lead_token_ledger(id,user_id,delta_tokens,balance_after,entry_type,source,source_id,idempotency_key,created_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?)",
                        (_id(), user["id"], -150, balance, "purchase", "marketplace_lead", purchase_id,
                         "lead-purchase:" + purchase_id, stamp),
                    )
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        row = con.execute(
            "SELECT l.id,l.city,l.property_type,l.area_sqm,l.budget_min_kopecks,l.budget_max_kopecks,"
            "l.description,l.desired_start_date,l.status,l.published_at,l.expires_at,l.created_at,"
            "p.purchased_at,p.price_kopecks,p.tokens_spent,c.contact_name,c.phone,c.email,c.preferred_contact_method "
            "FROM lead_purchases p JOIN marketplace_leads l ON l.id=p.lead_id "
            "JOIN marketplace_lead_contacts c ON c.lead_id=l.id "
            "WHERE p.id=? AND p.buyer_user_id=?",
            (purchase_id, user["id"]),
        ).fetchone()
        if not row:
            raise _error(404, "Покупка не найдена")
        return handler.send_json(200, {
            "lead": _lead(row), "purchased_at": row["purchased_at"],
            "price_kopecks": row["price_kopecks"], "tokens_spent": row["tokens_spent"],
            "contact": _contact(row),
        })

    if len(parts) == 4 and parts[:3] == ["api", "marketplace", "leads"] and method == "GET":
        lead_id = parts[3]
        row = con.execute(
            "SELECT id,city,property_type,area_sqm,budget_min_kopecks,budget_max_kopecks,description,"
            "desired_start_date,status,published_at,expires_at,created_at FROM marketplace_leads "
            "WHERE id=? AND status='published' AND (expires_at IS NULL OR expires_at>?)",
            (lead_id, now),
        ).fetchone()
        if not row:
            raise _error(404, "Опубликованный заказ не найден")
        return handler.send_json(200, {"lead": _lead(row)})

    raise _error(404, "Не найдено")
