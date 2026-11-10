"""Version-bound estimate capabilities. Public responses are built from allow-lists.

Account authentication remains the application's existing session authentication.
A view capability only authorizes a redacted document; it cannot accept an offer.
No raw link/view tokens, codes, IP addresses or user agents are persisted here.
"""
import hashlib
import json
import re
import secrets
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from backend.business import (
    BUSINESS_TIMEZONE, DomainError, calculate, choice, identity, integer, packed,
    stamp, string, transaction,
)
from backend.quote_integrity import InvalidSnapshot, fingerprint, verify_totals

DEFAULT_SETTINGS = {
    "allow_pdf": False, "allow_excel": False, "allow_copy": False,
    "show_details": False, "show_quantities": False, "show_prices": False,
    "sections_only": True, "show_materials": False, "watermark": True,
}
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}\Z")
DECISION_NOTICE = (
    "Ответ фиксирует ваше решение по предложению. Он не является электронной "
    "подписью и сам по себе не означает заключение договора."
)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def settings(value, previous=None):
    if not isinstance(value, dict) or not set(value) <= DEFAULT_SETTINGS.keys():
        raise DomainError(400, "Проверьте настройки защищённого доступа")
    result = {**DEFAULT_SETTINGS, **(previous or {})}
    for key, enabled in value.items():
        if type(enabled) is not bool:
            raise DomainError(400, "Настройки доступа должны быть переключателями")
        result[key] = enabled
    return result


def email(value):
    value = string(value, "Почта получателя", 254).lower()
    if value and not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
        raise DomainError(400, "Укажите корректную почту получателя")
    return value


def _code_hash(value):
    from backend.app import hash_password
    value = string(value, "Код доступа", 64)
    if value and len(value) < 6:
        raise DomainError(400, "Код доступа должен содержать не менее 6 символов")
    return hash_password(value) if value else ""


def _generated_code(data):
    flag = data.get("generate_access_code", False)
    if type(flag) is not bool or flag and data.get("access_code"):
        raise DomainError(400, "Выберите один способ задания кода доступа")
    return secrets.token_urlsafe(9) if flag else None


def _snapshot(con, row):
    version = con.execute(
        "SELECT snapshot,created_at FROM quote_versions WHERE quote_id=? AND version=?",
        (row["quote_id"], row["quote_version"]),
    ).fetchone()
    if not version:
        raise DomainError(404, "Предложение недоступно")
    snapshot = json.loads(version["snapshot"])
    try:
        if verify_totals(snapshot, calculate) != row["snapshot_sha256"]:
            raise InvalidSnapshot("Published version changed")
    except (InvalidSnapshot, DomainError, ValueError, TypeError):
        raise DomainError(409, "Опубликованная версия требует проверки исполнителем") from None
    return snapshot, version["created_at"]


def _event(con, row, kind, detail=None, actor=None):
    con.execute(
        "INSERT INTO protected_quote_events(id,workspace_id,link_id,kind,actor_id,detail,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (identity(), row["workspace_id"], row["id"], kind, actor, packed(detail or {}), stamp()),
    )


def _state(row):
    if row["status"] == "revoked":
        return "revoked"
    if row["expires_at"] <= stamp():
        return "expired"
    if row["max_views"] is not None and row["view_count"] >= row["max_views"]:
        return "exhausted"
    return "active"


def owner_view(row):
    keys = (
        "id", "quote_id", "quote_version", "recipient_name", "recipient_email",
        "expires_at", "max_views", "view_count", "first_viewed_at", "last_viewed_at",
        "status", "proposal_state", "revision", "created_at", "updated_at", "revoked_at",
    )
    return {**{key: row[key] for key in keys}, "settings": json.loads(row["settings"]),
            "has_access_code": bool(row["access_code_hash"]), "access_status": _state(row)}


def _owner_link(service, link_id):
    service.write_access(True)
    return service.get("protected_quote_links", string(link_id, "Ссылка", 80, True))


def _published(service, quote_id):
    quote = service.get("quotes", string(quote_id, "Смета", 80, True))
    if not quote["published_version"] or quote["approval_state"] == "draft":
        raise DomainError(409, "Сначала опубликуйте проверенную версию сметы")
    version = service.con.execute(
        "SELECT snapshot FROM quote_versions WHERE quote_id=? AND version=?",
        (quote["id"], quote["published_version"]),
    ).fetchone()
    if not version:
        raise DomainError(409, "Опубликованная версия не найдена")
    snapshot = json.loads(version["snapshot"])
    try:
        verify_totals(snapshot, calculate)
    except (InvalidSnapshot, DomainError):
        raise DomainError(409, "Пересохраните и опубликуйте проверенную смету") from None
    return quote, snapshot


def _lifetime(data, old=None):
    moment = stamp()
    expires = integer(data.get("expires_at", old["expires_at"] if old else moment + 7 * 86400),
                      "Срок доступа", 1, 4102444800)
    if "expires_at" in data or old is None:
        if not moment < expires <= moment + 366 * 86400:
            raise DomainError(400, "Срок доступа — от текущего момента до одного года")
    maximum = data.get("max_views", old["max_views"] if old else 20)
    if maximum is not None:
        integer(maximum, "Лимит открытий", 1, 10000)
    return expires, maximum


def owner_route(service, method, parts, query, data):
    service.write_access(True)
    if not parts and method == "GET":
        quote_id = string(query.get("quote_id", [""])[0], "Смета", 80, True)
        service.get("quotes", quote_id)
        rows = service.con.execute(
            "SELECT * FROM protected_quote_links WHERE workspace_id=? AND quote_id=? "
            "ORDER BY created_at DESC,id DESC LIMIT 100", (service.wid, quote_id),
        )
        return 200, {"links": [owner_view(row) for row in rows]}
    if not parts and method == "POST":
        allowed = {"quote_id", "quote_revision", "recipient_name", "recipient_email", "settings",
                   "expires_at", "max_views", "access_code", "generate_access_code"}
        if not set(data) <= allowed:
            raise DomainError(400, "Неизвестные параметры защищённой ссылки")
        request_key = service.h.headers.get("Idempotency-Key", "")
        key_hash = digest(string(request_key, "Ключ операции", 100, True)) if request_key else ""
        # A fast hash of a payload containing a low-entropy code would weaken
        # its scrypt protection. Compare that field with its salted hash instead.
        request_data = {key: value for key, value in data.items() if key != "access_code"}
        request_data["has_supplied_code"] = "access_code" in data
        request_data["supplied_code_enabled"] = bool(data.get("access_code"))
        request_hash = digest(json.dumps(request_data, ensure_ascii=False, sort_keys=True, allow_nan=False)) if key_hash else ""
        if key_hash:
            previous = service.con.execute(
                "SELECT * FROM protected_quote_links WHERE workspace_id=? AND created_by=? AND request_key_hash=?",
                (service.wid, service.user["id"], key_hash),
            ).fetchone()
            if previous:
                if previous["request_hash"] != request_hash:
                    raise DomainError(409, "Ключ уже использован для другой защищённой ссылки")
                if data.get("access_code"):
                    from backend.app import verify_password
                    code = string(data["access_code"], "Код доступа", 64)
                    if not verify_password(code, previous["access_code_hash"]):
                        raise DomainError(409, "Ключ уже использован с другим кодом доступа")
                return 200, {"link": owner_view(previous), "replayed": True}
        quote, snapshot = _published(service, data.get("quote_id", ""))
        if "quote_revision" in data:
            service.check_revision(quote, {"revision": data["quote_revision"]})
        count = service.con.execute(
            "SELECT count(*) FROM protected_quote_links WHERE workspace_id=? AND quote_id=?",
            (service.wid, quote["id"]),
        ).fetchone()[0]
        if count >= 100:
            raise DomainError(409, "Для одной сметы доступно до 100 защищённых ссылок")
        expires, maximum = _lifetime(data)
        token = secrets.token_urlsafe(32)
        generated_code = _generated_code(data)
        contractor = service.con.execute("SELECT name FROM workspaces WHERE id=?", (service.wid,)).fetchone()[0]
        row = dict(
            id=identity(), workspace_id=service.wid, quote_id=quote["id"],
            quote_version=quote["published_version"], snapshot_sha256=fingerprint(snapshot),
            token_hash=digest(token), request_key_hash=key_hash, request_hash=request_hash,
            recipient_name=string(data.get("recipient_name", ""), "Получатель", 120),
            recipient_email=email(data.get("recipient_email", "")), contractor_name=contractor,
            settings=packed(settings(data.get("settings", {}))), access_code_hash=_code_hash(generated_code or data.get("access_code", "")),
            access_epoch=1, expires_at=expires, max_views=maximum, view_count=0,
            first_viewed_at=None, last_viewed_at=None, status="active",
            proposal_state=quote["approval_state"] if quote["approval_state"] in ("approved", "rejected", "changes_requested") else "sent", revision=1,
            created_by=service.user["id"], created_at=stamp(), updated_at=stamp(), revoked_at=None,
        )
        service.insert("protected_quote_links", row)
        # A legacy bearer URL must not be an alternative route around protection.
        service.update("quotes", quote["id"], {"protection_enabled": 1})
        _event(service.con, row, "created", owner_view(row), service.user["id"])
        return 201, {"link": owner_view(row), "url": service.origin + "/protected-estimate#" + token,
                     **({"access_code": generated_code} if generated_code else {})}
    if len(parts) == 1:
        row = _owner_link(service, parts[0])
        if method == "GET":
            events = service.con.execute(
                "SELECT kind,detail,created_at FROM protected_quote_events "
                "WHERE workspace_id=? AND link_id=? ORDER BY created_at DESC,id DESC LIMIT 100",
                (service.wid, row["id"]),
            )
            decision = service.con.execute(
                "SELECT action,comment,quote_version,created_at FROM protected_quote_decisions "
                "WHERE workspace_id=? AND link_id=?", (service.wid, row["id"]),
            ).fetchone()
            return 200, {"link": owner_view(row), "events": [
                {**dict(event), "detail": json.loads(event["detail"])} for event in events
            ], "decision": dict(decision) if decision else None}
        if method in ("PATCH", "DELETE"):
            service.check_revision(row, data)
            if row["status"] == "revoked":
                if method == "DELETE":
                    return 200, {"link": owner_view(row)}
                raise DomainError(409, "Отозванная ссылка не восстанавливается. Создайте новую")
            if method == "DELETE":
                values = {"status": "revoked", "revoked_at": stamp(), "access_epoch": row["access_epoch"] + 1}
                event = "revoked"
            else:
                if not set(data) <= {"revision", "settings", "recipient_name", "recipient_email", "expires_at", "max_views", "access_code", "generate_access_code"}:
                    raise DomainError(400, "Неизвестные параметры доступа")
                expires, maximum = _lifetime(data, row)
                values = {"settings": packed(settings(data.get("settings", {}), json.loads(row["settings"]))),
                          "expires_at": expires, "max_views": maximum}
                for key in ("recipient_name", "recipient_email"):
                    if key in data:
                        values[key] = email(data[key]) if key == "recipient_email" else string(data[key], "Получатель", 120)
                generated_code = _generated_code(data)
                if "access_code" in data or generated_code:
                    values.update(access_code_hash=_code_hash(generated_code or data["access_code"]), access_epoch=row["access_epoch"] + 1)
                # Changing the addressee invalidates every prior viewing capability.
                if any(key in values and values[key] != row[key] for key in ("recipient_name", "recipient_email")):
                    values["access_epoch"] = row["access_epoch"] + 1
                event = "permissions_changed"
            values.update(revision=row["revision"] + 1, updated_at=stamp())
            service.update("protected_quote_links", row["id"], values)
            updated = _owner_link(service, row["id"])
            _event(service.con, row, event, {"before": owner_view(row), "after": owner_view(updated)}, service.user["id"])
            return 200, {"link": owner_view(updated), **({"access_code": generated_code} if method == "PATCH" and generated_code else {})}
    if len(parts) == 2 and parts[1] == "send" and method == "POST":
        row = _owner_link(service, parts[0])
        service.check_revision(row, data)
        if set(data) != {"revision", "confirm_delivery"} or data.get("confirm_delivery") is not True:
            raise DomainError(400, "Подтвердите отправку защищённой ссылки указанному получателю")
        _active(row)
        if row["max_views"] is not None and row["view_count"] >= row["max_views"]:
            raise DomainError(409, "Перед отправкой увеличьте исчерпанный лимит открытий")
        if not row["recipient_email"] or not service.user["email_verified_at"]:
            raise DomainError(403, "Укажите получателя и подтвердите свою почту перед отправкой")
        service.h.throttle("protected-send-user:" + service.user["id"], 5, 3600)
        service.h.throttle("protected-send-recipient:" + digest(row["recipient_email"]), 3, 86400)
        token = secrets.token_urlsafe(32)
        url = service.origin + "/protected-estimate#" + token
        # Keep delivery and token rotation in the existing serialized transaction.
        # An SMTP failure rolls back rotation; a commit failure leaves a dead link,
        # never an unprotected document. The raw capability is never an outbox row.
        from backend.app import mail
        mail(row["recipient_email"], "Защищённое предложение в Сметре", url + "\n\n"
             "Исполнитель предоставил вам защищённую версию сметы. Для ответа войдите с этой почтой."
             + (" Код доступа исполнитель передаёт отдельно." if row["access_code_hash"] else ""))
        service.update("protected_quote_links", row["id"], {
            "token_hash": digest(token), "access_epoch": row["access_epoch"] + 1,
            "revision": row["revision"] + 1, "updated_at": stamp(),
        })
        _event(service.con, row, "sent", actor=service.user["id"])
        return 200, {"link": owner_view(_owner_link(service, row["id"])), "sent": True, "url": url}
    if len(parts) == 2 and parts[1] == "reissue" and method == "POST":
        row = _owner_link(service, parts[0])
        service.check_revision(row, data)
        if row["status"] != "active":
            raise DomainError(409, "Создайте новую ссылку вместо отозванной")
        token = secrets.token_urlsafe(32)
        service.update("protected_quote_links", row["id"], {
            "token_hash": digest(token), "access_epoch": row["access_epoch"] + 1,
            "revision": row["revision"] + 1, "updated_at": stamp(),
        })
        _event(service.con, row, "reissued", actor=service.user["id"])
        return 200, {"link": owner_view(_owner_link(service, row["id"])),
                     "url": service.origin + "/protected-estimate#" + token}
    raise DomainError(404, "Действие с защищённой ссылкой не найдено")


def _material(item):
    category = str(item.get("category", "")).casefold()
    return (item.get("kind") == "material" or item.get("visual_role") in ("material", "product")
            or bool(item.get("product_source_id")) or bool(re.search(r"материал|material|комплектующ|расходник", category)))


def document_view(snapshot, row, view, published_at):
    """Build a new document; never redact a copy of the original snapshot."""
    policy = json.loads(row["settings"])
    output = {key: snapshot.get(key, "") for key in ("title", "currency", "amount_kopecks", "terms", "due_date")}
    from backend.estimate_assemblies import scope
    output["scope"] = scope(snapshot.get("scope", {}))
    output["alternative_label"] = string(snapshot.get("alternative_label", ""), "Вариант", 80)
    current_version = row["current_quote_version"] if "current_quote_version" in row.keys() else row["quote_version"]
    current_state = row["current_quote_state"] if "current_quote_state" in row.keys() else row["proposal_state"]
    current_offer = current_version == row["quote_version"] and current_state != "draft"
    state = current_state if current_offer and current_state in ("approved", "rejected", "changes_requested") else row["proposal_state"]
    output.update(contractor=row["contractor_name"], recipient=row["recipient_name"],
                  number="СМ-" + row["quote_id"].replace("-", "")[:8].upper(),
                  version=row["quote_version"], created_at=published_at,
                  status=state, snapshot_sha256=row["snapshot_sha256"],
                  permissions_revision=row["revision"], permissions=policy,
                  expires_at=row["expires_at"], view_id=view["id"], decision_notice=DECISION_NOTICE,
                  identity_required=True, decisions_available=bool(row["recipient_email"]) and current_offer)
    if not current_offer:
        output["version_notice"] = "Вы просматриваете сохранённую версию. Исполнитель изменил предложение; запросите актуальную ссылку для согласования."
    # Original descriptions may contain hidden positions in free-form text.
    # Contractor terms are the explicit client-facing notes for this document.
    rows = [item for item in snapshot.get("items", [])
            if item.get("included", True) and (policy["show_materials"] or not _material(item))]
    if policy["sections_only"]:
        sections = {}
        for item in rows:
            category = item.get("category") or "Работы"
            section = {"work": "Работы", "service": "Услуги", "material": "Материалы", "equipment": "Оборудование"}.get(category, category)
            sections[section] = sections.get(section, 0) + item["subtotal"]
        output["sections"] = [{"name": name, "amount_kopecks": amount} for name, amount in sections.items()]
    elif policy["show_details"]:
        output["items"] = []
        for item in rows:
            visible = {key: item.get(key, "") for key in ("name", "category")}
            if policy["show_quantities"]:
                visible.update(quantity=item["quantity"], unit=item["unit"])
            if policy["show_prices"]:
                visible["subtotal"] = item["subtotal"]
                if policy["show_quantities"]:
                    # A base price plus a total would reveal the private markup.
                    visible["unit_price"] = int((Decimal(item["subtotal"]) / Decimal(item["quantity"])).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            output["items"].append(visible)
    if snapshot.get("ai_generated"):
        from backend.estimate_safety import AI_ESTIMATE_DISCLAIMER
        output["notice"] = AI_ESTIMATE_DISCLAIMER
    if policy["watermark"]:
        moment = datetime.fromtimestamp(view["created_at"], BUSINESS_TIMEZONE).strftime("%d.%m.%Y %H:%M МСК")
        output["watermark"] = f"{row['recipient_name'] or 'Получатель'} · {moment} · {view['id'][:8]}"
    return output


def _active(row):
    if row["status"] != "active" or row["expires_at"] <= stamp():
        raise DomainError(410, "Доступ закрыт или срок ссылки истёк. Обратитесь к исполнителю")


def _view(con, row, value):
    if not isinstance(value, str) or not TOKEN_RE.fullmatch(value):
        raise DomainError(401, "Откройте защищённую ссылку заново")
    view = con.execute(
        "SELECT * FROM protected_quote_views WHERE token_hash=? AND link_id=? AND workspace_id=?",
        (digest(value), row["id"], row["workspace_id"]),
    ).fetchone()
    if (not view or view["expires_at"] <= stamp() or view["access_epoch"] != row["access_epoch"]
            or row["max_views"] is not None and view["ordinal"] > row["max_views"]):
        raise DomainError(401, "Настройки доступа изменились. Откройте ссылку заново")
    return view


def public_route(service, method, parts):
    if method != "POST" or parts not in (["open"], ["view"], ["pdf"], ["xlsx"], ["respond"]):
        raise DomainError(405, "Для защищённого просмотра используйте POST")
    h, con = service.h, service.con
    h.throttle("protected-public:" + h.client_address[0], 120, 60)
    data = h.body()
    token = data.get("token")
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        raise DomainError(404, "Предложение не найдено")
    token_hash = digest(token)
    candidate = con.execute(
        "SELECT l.id,l.workspace_id FROM protected_quote_links l JOIN quotes q ON q.id=l.quote_id "
        "JOIN users u ON u.id=q.user_id WHERE l.token_hash=? AND u.blocked=0 AND u.deleted_at IS NULL",
        (token_hash,),
    ).fetchone()
    if not candidate:
        raise DomainError(404, "Предложение не найдено")
    h.throttle("protected-link:" + candidate["id"] + ":" + h.client_address[0], 60, 60)
    if parts == ["open"]:
        h.throttle("protected-code:" + candidate["id"] + ":" + h.client_address[0], 10, 600)
        h.throttle("protected-open-global:" + candidate["id"], 100, 600)
    with transaction(con, lock_scopes=(f"workspace:{candidate['workspace_id']}",)):
        row = con.execute(
            "SELECT l.*,q.published_version AS current_quote_version,q.approval_state AS current_quote_state "
            "FROM protected_quote_links l JOIN quotes q ON q.id=l.quote_id "
            "JOIN users u ON u.id=q.user_id WHERE l.token_hash=? AND u.blocked=0 AND u.deleted_at IS NULL",
            (token_hash,),
        ).fetchone()
        if not row:
            raise DomainError(404, "Предложение не найдено")
        _active(row)
        snapshot, published_at = _snapshot(con, row)
        if parts == ["open"]:
            # Refreshing an existing capability does not consume another opening.
            if data.get("view_token"):
                view = _view(con, row, data["view_token"])
                return 200, {"document": document_view(snapshot, row, view, published_at)}
            if row["access_code_hash"]:
                from backend.app import verify_password
                code = data.get("access_code", "")
                if not isinstance(code, str) or len(code) > 64 or not verify_password(code, row["access_code_hash"]):
                    raise DomainError(401, "Введите правильный код доступа от исполнителя")
            if row["max_views"] is not None and row["view_count"] >= row["max_views"]:
                raise DomainError(410, "Лимит открытий исчерпан. Запросите доступ у исполнителя")
            view_token = secrets.token_urlsafe(32)
            view = dict(id=identity(), workspace_id=row["workspace_id"], link_id=row["id"],
                        token_hash=digest(view_token), access_epoch=row["access_epoch"], ordinal=row["view_count"] + 1,
                        created_at=stamp(), expires_at=min(row["expires_at"], stamp() + 8 * 3600))
            keys = tuple(view)
            con.execute(f"INSERT INTO protected_quote_views({','.join(keys)}) VALUES({','.join('?' for _ in keys)})", tuple(view.values()))
            state = "viewed" if row["proposal_state"] == "sent" else row["proposal_state"]
            con.execute(
                "UPDATE protected_quote_links SET view_count=view_count+1,first_viewed_at=coalesce(first_viewed_at,?),"
                "last_viewed_at=?,proposal_state=? WHERE id=?",
                (stamp(), stamp(), state, row["id"]),
            )
            con.execute(
                "UPDATE quotes SET approval_state='viewed' WHERE id=? AND published_version=? AND approval_state='sent'",
                (row["quote_id"], row["quote_version"]),
            )
            _event(con, row, "opened", {"view_id": view["id"]})
            output = document_view(snapshot, dict(row, proposal_state=state), view, published_at)
            return 200, {"document": output, "view_token": view_token}
        view = _view(con, row, data.get("view_token"))
        output = document_view(snapshot, row, view, published_at)
        if parts == ["view"]:
            return 200, {"document": output}
        if parts in (["pdf"], ["xlsx"]):
            permission = "allow_pdf" if parts == ["pdf"] else "allow_excel"
            if not output["permissions"][permission]:
                raise DomainError(403, "Исполнитель запретил этот экспорт")
            h.throttle("protected-export:" + row["id"] + ":" + h.client_address[0], 12, 600)
            from backend.protected_estimate_exports import export
            result = export(output, parts[0])
            _event(con, row, "exported", {"format": parts[0], "view_id": view["id"]})
            return 200, result
        return _respond(service, row, view, data)


def _respond(service, row, view, data):
    user = service.h.auth(service.con)
    if not user["email_verified_at"] or not row["recipient_email"] or user["email"].lower() != row["recipient_email"]:
        raise DomainError(403, "Решение доступно только получателю с подтверждённой почтой")
    if data.get("confirmation") is not True:
        raise DomainError(400, "Подтвердите своё решение по этой версии предложения")
    action = choice(data.get("action"), ("approved", "changes_requested", "rejected"), "Решение")
    comment = string(data.get("comment", ""), "Комментарий", 3000, action == "changes_requested")
    if data.get("snapshot_sha256") != row["snapshot_sha256"]:
        raise DomainError(409, "Версия предложения изменилась. Обновите страницу")
    previous = service.con.execute("SELECT * FROM protected_quote_decisions WHERE link_id=?", (row["id"],)).fetchone()
    if previous:
        if previous["user_id"] == user["id"] and previous["action"] == action and previous["comment"] == comment:
            return 200, {"ok": True, "status": action, "created_at": previous["created_at"], "replayed": True}
        raise DomainError(409, "Решение уже записано. Новые условия согласуйте с исполнителем")
    if type(data.get("permissions_revision")) is not int or data["permissions_revision"] != row["revision"]:
        raise DomainError(409, "Права доступа изменились. Обновите предложение перед ответом")
    quote = service.con.execute("SELECT * FROM quotes WHERE id=? AND workspace_id=?", (row["quote_id"], row["workspace_id"])).fetchone()
    updated = service.con.execute(
        "UPDATE quotes SET approval_state=?,status=?,approved_at=?,approved_by=?,updated_at=?,revision=revision+1 "
        "WHERE id=? AND workspace_id=? AND published_version=? AND approval_state IN ('sent','viewed','changes_requested')",
        (action, {"approved": "accepted", "rejected": "declined", "changes_requested": "sent"}[action],
         stamp() if action == "approved" else None, user["name"] if action == "approved" else "", stamp(),
         row["quote_id"], row["workspace_id"], row["quote_version"]),
    )
    if updated.rowcount != 1:
        raise DomainError(409, "Исполнитель изменил предложение или решение уже принято. Запросите актуальную версию")
    from backend.estimate_workflow import alternative_decision
    alternative_decision(service, quote, action)
    from backend.construction_changes import protected_decision
    protected_decision(service, quote, action, user, comment)
    service.con.execute(
        "INSERT INTO protected_quote_decisions(link_id,workspace_id,view_id,user_id,action,comment,quote_version,snapshot_sha256,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (row["id"], row["workspace_id"], view["id"], user["id"], action, comment, row["quote_version"], row["snapshot_sha256"], stamp()),
    )
    service.con.execute("UPDATE protected_quote_links SET proposal_state=?,updated_at=? WHERE quote_id=? AND quote_version=? AND workspace_id=?",
                        (action, stamp(), row["quote_id"], row["quote_version"], row["workspace_id"]))
    _event(service.con, row, "decision", {"action": action, "comment": comment, "view_id": view["id"]}, user["id"])
    service.wid = row["workspace_id"]
    service.user = user
    labels = {"approved": "Смета принята", "rejected": "Смета отклонена", "changes_requested": "Запрошены изменения"}
    service.emit("quote", row["quote_id"], labels[action], comment, notify=True)
    return 200, {"ok": True, "status": action, "created_at": stamp()}
