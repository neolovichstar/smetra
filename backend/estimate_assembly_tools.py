"""Assembly assistant tools use the ordinary API and explicit action confirmation."""
from backend.business import DomainError, string
from backend import estimate_assemblies as assemblies

READ_TOOLS = ("list_estimate_assemblies", "preview_estimate_assembly")
WRITE_TOOLS = ("save_estimate_assembly", "apply_estimate_assembly", "recalculate_estimate_assembly", "set_estimate_scope")


def tools(function):
    values = {"type": "object", "additionalProperties": {"type": ["string", "number"]}}
    scope = {"type": "object", "properties": {key: {"type": "array", "items": {"type": "string"}, "maxItems": 20}
                                               for key in assemblies.SCOPE_LABELS}, "additionalProperties": False}
    return [
        function("list_estimate_assemblies", "Сборки текущей компании с формулами и собственными расценками. Не придумывай нормы расхода и цены.", {}, ()),
        function("preview_estimate_assembly", "Рассчитать сборку по параметрам на сервере без изменения сметы. Результат требует проверки технологии и расхода по производителю.",
                 {"id": {"type": "string"}, "parameters": values}, ("id", "parameters")),
        function("save_estimate_assembly", "Предложить сохранить технологическую сборку. Только после явного подтверждения. Используй нормы и цены пользователя; для неизвестных цен ставь 0: публикация заблокируется до проверки.",
                 {"id": {"type": "string"}, "revision": {"type": "integer"}, "title": {"type": "string"}, "currency": {"type": "string"}, "parameters": values,
                  "labels": {"type": "object", "additionalProperties": {"type": "string"}},
                  "items": {"type": "array", "maxItems": 50, "items": {"type": "object", "properties": {
                      "name": {"type": "string"}, "unit": {"type": "string"}, "kind": {"type": "string", "enum": ["work", "material", "service", "equipment", "other"]},
                      "expression": {"type": "string", "description": "Количество: параметры, числа, + - * / и скобки"},
                      "unit_price": {"type": "integer", "description": "Цена в копейках"}, "cost_price": {"type": "integer"}, "category": {"type": "string"}},
                      "required": ["name", "unit", "expression", "unit_price"]}}, "scope": scope}, ("title", "parameters", "items")),
        function("apply_estimate_assembly", "Предложить добавить сборку в существующую смету; сохранит остальные строки. Только после подтверждения. Параметры и состав показываются в карточке; ничего не отправляется заказчику.",
                 {"quote_id": {"type": "string"}, "id": {"type": "string"}, "parameters": values}, ("quote_id", "id", "parameters")),
        function("recalculate_estimate_assembly", "Предложить пересчёт одной применённой сборки по новым параметрам. Сохраняет ручные строки и цены; опубликованная версия неизменна.",
                 {"quote_id": {"type": "string"}, "instance_id": {"type": "string"}, "parameters": values}, ("quote_id", "instance_id", "parameters")),
        function("set_estimate_scope", "Предложить заменить границы предложения: включено, исключено, обеспечивает заказчик, требует уточнения. Это видимые заказчику условия; не помещай сюда закупочные цены или наценку. Только после подтверждения.",
                 {"quote_id": {"type": "string"}, "scope": scope}, ("quote_id", "scope")),
    ]


def read(service, name, args):
    return service.route("GET" if name == READ_TOOLS[0] else "POST", "assemblies",
                         [] if name == READ_TOOLS[0] else ["preview"], {}, args)[1]


def prepare(service, name, args):
    service.write_access(True)
    if name == "save_estimate_assembly":
        values = assemblies.normalize(args)
        if args.get("id"):
            row, old = assemblies.record(service, args["id"])
            values.update(id=row["id"], revision=old["revision"])
        summary = "Сохранить сборку · " + values["title"]
        rows = [{"field": item["name"], "before": None,
                 "after": f"{item['expression']} {item['unit']}; цена {item['unit_price'] / 100:.2f}"} for item in values["items"]]
    else:
        quote = service.get("quotes", string(args.get("quote_id", ""), "Смета", 80, True))
        if quote["approval_state"] == "approved":
            raise DomainError(409, "Согласованную смету нельзя изменить: создайте копию")
        current = service.quote_view(quote)
        values = {"quote_id": quote["id"], "quote_revision": quote["revision"]}
        if name == "set_estimate_scope":
            values["scope"] = assemblies.scope(args.get("scope"))
            rows = [{"field": label, "before": "\n".join(current.get("scope", {}).get(key, [])),
                     "after": "\n".join(values["scope"][key])} for key, label in assemblies.SCOPE_LABELS.items()]
        else:
            values["parameters"] = assemblies.parameters(args.get("parameters"))
            if name == "apply_estimate_assembly":
                row, definition = assemblies.record(service, args.get("id", ""))
                values.update(id=row["id"], revision=definition["revision"])
                calculated = assemblies.preview(service, {**values, "currency": current["currency"]})
                if len(current["items"]) + len(calculated["items"]) > 200:
                    raise DomainError(400, "В смете может быть до 200 позиций")
            else:
                values["instance_id"] = string(args.get("instance_id", ""), "Сборка", 64, True)
                calculated = assemblies.recalculate({**values, "items": current["items"]})
            rows = [{"field": "Параметры", "before": None, "after": str(values["parameters"])},
                    *[{"field": item["name"], "before": None,
                       "after": f"{item['quantity']} {item['unit']} · {item['subtotal'] / 100:.2f} {current['currency']}"}
                      for item in calculated["items"] if item.get("assembly")]]
        summary = {"set_estimate_scope": "Изменить состав предложения", "apply_estimate_assembly": "Добавить сборку",
                   "recalculate_estimate_assembly": "Пересчитать сборку"}[name] + " · " + quote["title"]
    values["_preview"] = {"kind": "fields", "rows": rows}
    return values, summary


def apply(service, name, args):
    service.write_access(True)
    if name == "save_estimate_assembly":
        return service.route("PATCH" if args.get("id") else "POST", "assemblies", [args["id"]] if args.get("id") else [], {}, args)
    quote = service.get("quotes", args["quote_id"])
    service.check_revision(quote, {"revision": args["quote_revision"]})
    current = service.quote_view(quote)
    data = {"revision": quote["revision"]}
    if name == "set_estimate_scope":
        data["scope"] = args["scope"]
    elif name == "apply_estimate_assembly":
        calculated = assemblies.preview(service, {**args, "currency": current["currency"]})
        data.update(items=current["items"] + calculated["items"], scope=assemblies.merge_scope(current["scope"], calculated["scope"]))
    else:
        data["items"] = assemblies.recalculate({**args, "items": current["items"]})["items"]
    return service.route("PATCH", "quotes", [quote["id"]], {}, data)
