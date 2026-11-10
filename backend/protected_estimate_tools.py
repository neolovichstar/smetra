"""Assistant proposals reuse protected-link API policy and explicit confirmation."""
from datetime import datetime

from backend.business import BUSINESS_TIMEZONE, DomainError, string
from backend.protected_estimates import DEFAULT_SETTINGS, _lifetime, _owner_link, _published, email, owner_view, settings

READ_TOOLS = ("list_protected_estimates", "get_protected_estimate_access")
WRITE_TOOLS = ("create_protected_estimate", "update_protected_estimate", "revoke_protected_estimate", "send_protected_estimate")


def tools(function):
    policy = {"type": "object", "properties": {key: {"type": "boolean"} for key in DEFAULT_SETTINGS}, "additionalProperties": False}
    common = {
        "recipient_name": {"type": "string", "maxLength": 120},
        "recipient_email": {"type": "string", "maxLength": 254},
        "settings": policy, "expires_at": {"type": "integer"},
        "max_views": {"type": ["integer", "null"], "minimum": 1, "maximum": 10000},
        "code_mode": {"type": "string", "enum": ["keep", "generate", "remove"]},
    }
    return [
        function("list_protected_estimates", "Посмотреть защищённые ссылки сметы: получатели, права, сроки, открытия и решения. Открытие не доказывает прочтение. Токены и коды не возвращаются.",
                 {"quote_id": {"type": "string"}}, ("quote_id",)),
        function("get_protected_estimate_access", "История изменений доступа и серверные события открытий конкретной ссылки. Личность зрителя неизвестна до подтверждённого ответа; не утверждай, кто прочитал документ.",
                 {"id": {"type": "string"}}, ("id",)),
        function("create_protected_estimate", "Предложить защищённую ссылку на опубликованную смету. Только после нажатия «Применить». По умолчанию только разделы и итог, без материалов, PDF, Excel и копирования. Закупочные данные и наценка не раскрываются. Создание не отправляет письмо. Для одного итога: sections_only=false, show_details=false.",
                 {"quote_id": {"type": "string"}, **common}, ("quote_id",)),
        function("update_protected_estimate", "Предложить изменение прав, получателя, срока, лимита или кода защищённой ссылки. Применяется только после подтверждения, с проверкой текущей версии настроек. Код генерируется сервером и показывается владельцу один раз.",
                 {"id": {"type": "string"}, **common}, ("id",)),
        function("revoke_protected_estimate", "Предложить немедленно отозвать одну защищённую ссылку. Применяется только после явного подтверждения пользователя.",
                 {"id": {"type": "string"}}, ("id",)),
        function("send_protected_estimate", "Подготовить отправку защищённой ссылки по сохранённой почте получателя. Реальное внешнее письмо отправляется ТОЛЬКО после явного нажатия пользователем «Применить» на карточке с адресатом. Старая ссылка заменяется новой. Не утверждай, что письмо отправлено, до результата подтверждения.",
                 {"id": {"type": "string"}}, ("id",)),
    ]


def read(service, name, args):
    if name == "list_protected_estimates":
        quote_id = string(args.get("quote_id", ""), "Смета", 80, True)
        return service.route("GET", "protected-links", [], {"quote_id": [quote_id]}, {})[1]
    return service.route("GET", "protected-links", [string(args.get("id", ""), "Ссылка", 80, True)], {}, {})[1]


def _preview(name, before, values, code_mode):
    """The existing confirmation card renders plain, reviewable field changes."""
    old = before or {}
    after = {**old, **values}
    old_policy = old.get("settings", {})
    policy = {**DEFAULT_SETTINGS, **old_policy, **values.get("settings", {})}
    rows = []

    def add(label, previous, proposed):
        rows.append({"field": label, "before": previous, "after": proposed})

    def date(value):
        return datetime.fromtimestamp(value, BUSINESS_TIMEZONE).strftime("%d.%m.%Y %H:%M МСК") if value else None

    def composition(value):
        return "Разделы и итог" if value.get("sections_only") else "Подробные позиции" if value.get("show_details") else "Только итог"

    if name == "send_protected_estimate":
        add("Действие", None, "Отправить письмо; прежний адрес перестанет работать")
    elif name == "revoke_protected_estimate":
        add("Действие", "Доступ открыт", "Отозвать доступ и закрыть текущие просмотры")
    add("Получатель", old.get("recipient_name"), after.get("recipient_name") or "Не указан")
    add("Почта получателя", old.get("recipient_email"), after.get("recipient_email") or "Не указана — согласование отключено")
    add("Срок доступа", date(old.get("expires_at")), date(after.get("expires_at")))
    add("Лимит открытий", str(old["max_views"]) if old.get("max_views") is not None else None,
        str(after["max_views"]) if after.get("max_views") is not None else "Без ограничения")
    add("Состав предложения", composition(old_policy) if before else None, composition(policy))
    labels = {"allow_pdf": "Скачивание PDF", "allow_excel": "Экспорт Excel", "allow_copy": "Копирование текста",
              "show_quantities": "Количество и единицы", "show_prices": "Цены позиций", "show_materials": "Материалы",
              "watermark": "Персональный водяной знак"}
    for key, label in labels.items():
        add(label, ("Разрешено" if old_policy.get(key) else "Выключено") if before else None,
            "Разрешено" if policy[key] else "Выключено")
    add("Код доступа", ("Установлен" if old.get("has_access_code") else "Нет") if before else None,
        "Сгенерировать новый" if code_mode == "generate" else "Нет" if code_mode == "remove" else "Установлен" if old.get("has_access_code") else "Нет")
    add("Закупочные цены и внутренняя наценка", "Скрыты всегда" if before else None, "Скрыты всегда")
    return {"kind": "fields", "rows": rows}


def prepare(service, name, args):
    service.write_access(True)
    if name == "create_protected_estimate":
        quote, _ = _published(service, args.get("quote_id", ""))
        values = {key: value for key, value in args.items() if key in ("quote_id", "recipient_name", "recipient_email", "settings", "expires_at", "max_views")}
        values["quote_revision"] = quote["revision"]
        values["settings"] = settings(values.get("settings", {}))
        values["expires_at"], values["max_views"] = _lifetime(values)
        summary = "Создать защищённую ссылку · " + quote["title"][:80]
        before = None
    else:
        row = _owner_link(service, args.get("id", ""))
        if row["status"] == "revoked":
            raise DomainError(409, "Ссылка уже отозвана")
        values = {"id": row["id"], "revision": row["revision"]}
        before = owner_view(row)
        if name == "update_protected_estimate":
            values.update({key: value for key, value in args.items() if key in ("recipient_name", "recipient_email", "settings", "expires_at", "max_views")})
            if "settings" in values:
                values["settings"] = settings(values["settings"], before["settings"])
            _lifetime(values, before)
            summary = "Изменить защищённый доступ · " + (row["recipient_name"] or row["recipient_email"] or row["id"][:8])
        elif name == "revoke_protected_estimate":
            summary = "Закрыть защищённый доступ · " + (row["recipient_name"] or row["recipient_email"] or row["id"][:8])
        else:
            if not row["recipient_email"]:
                raise DomainError(400, "Укажите получателя перед отправкой")
            summary = "Отправить защищённую ссылку → " + row["recipient_email"]
    mode = args.get("code_mode", "keep")
    if mode not in ("keep", "generate", "remove"):
        raise DomainError(400, "Проверьте настройку кода доступа")
    if mode == "generate":
        values["generate_access_code"] = True
    elif mode == "remove":
        values["access_code"] = ""
    if "recipient_name" in values:
        values["recipient_name"] = string(values["recipient_name"], "Получатель", 120)
    if "recipient_email" in values:
        values["recipient_email"] = email(values["recipient_email"])
    values["_preview"] = _preview(name, before, values, mode)
    return values, summary


def apply(service, name, args):
    args = dict(args)
    link_id = args.pop("id", None)
    if name == "create_protected_estimate":
        parts, method = [], "POST"
    elif name == "update_protected_estimate":
        parts, method = [link_id], "PATCH"
    elif name == "revoke_protected_estimate":
        parts, method = [link_id], "DELETE"
    else:
        parts, method = [link_id, "send"], "POST"
        # Only this confirmation path supplies the external-delivery approval.
        args["confirm_delivery"] = True
    return service.route(method, "protected-links", parts, {}, args)


def persisted_result(result):
    """Do not turn action history into a store of raw capabilities or codes."""
    return {**result, "result": {key: value for key, value in result["result"].items() if key not in ("url", "access_code")}}
