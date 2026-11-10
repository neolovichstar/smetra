"""Confirmed assistant operations for the estimate's commercial workflow."""
from decimal import Decimal

from backend.business import DomainError, decimal, integer, string
from backend.estimate_workflow import margin_policy

READ_TOOLS = ("get_order_forecast", "preview_estimate_discount", "get_estimate_economics", "get_actual_rates", "list_estimate_alternatives")
WRITE_TOOLS = ("update_order_forecast", "apply_estimate_discount", "set_minimum_margin", "create_estimate_alternatives", "record_work_actual_cost", "apply_actual_rate")


def tools(function):
    identifier = {"type": "string"}
    costs = {"remaining_cost": {"type": "integer", "description": "Все оставшиеся расходы в копейках, включая обязательства"},
             "committed_cost": {"type": "integer", "description": "Уже обещанные будущие затраты ВНУТРИ остатка, не прибавлять повторно"},
             "note": {"type": "string"}}
    return [
        function("get_order_forecast", "Текущие расходы, остаток затрат и прибыль заказа. Если forecast_stale=true, расходы изменились: уточни остаток у пользователя. Бюджетный ориентир не выдавай за прогноз завершения.", {"id": identifier}, ("id",)),
        function("get_estimate_economics", "Себестоимость, прибыль, маржа и минимальная маржа сметы. Если cost_complete=false, прибыль неизвестна.", {"id": identifier}, ("id",)),
        function("preview_estimate_discount", "Серверный расчёт влияния дополнительной скидки на прибыль. Не меняет смету. При неполной себестоимости не обещай прибыль.", {"id": identifier, "percent": {"type": "string"}}, ("id", "percent")),
        function("update_order_forecast", "Предложить остаток расходов на завершение по данным подрядчика. Обязательства уже входят в остаток. Только после подтверждения пользователя; не придумывай прогноз.", {"id": identifier, **costs}, ("id", "remaining_cost")),
        function("apply_estimate_discount", "Предложить дополнительную скидку с показом прибыли до и после. При низкой марже карточка отдельно предупреждает руководителя. Применяется только после подтверждения.", {"id": identifier, "percent": {"type": "string"}}, ("id", "percent")),
        function("set_minimum_margin", "Предложить минимальную маржу компании для контроля скидок и публикации. Не меняет тарифы. Только после явного подтверждения.", {"minimum_margin_pct": {"type": "string"}}, ("minimum_margin_pct",)),
        function("list_estimate_alternatives", "Прочитать все варианты одной сметы текущей компании. Заказчик может принять один вариант.", {"id": identifier}, ("id",)),
        function("create_estimate_alternatives", "Предложить один или два альтернативных состава к черновику до публикации. Не придумывай нормы, цены и исключения. Создание учитывается действующим лимитом смет. Только после подтверждения; отправка отдельно.",
                 {"id": identifier, "root_label": {"type": "string"}, "variants": {"type": "array", "minItems": 1, "maxItems": 2,
                  "items": {"type": "object", "properties": {"label": {"type": "string"}, "rows": {"type": "array", "minItems": 1, "maxItems": 200, "uniqueItems": True, "items": {"type": "integer", "minimum": 1, "maximum": 200}},
                      "discount_percent": {"type": "string", "description": "Дополнительная скидка на выбранные позиции, по данным пользователя"}}, "required": ["label", "rows"]}}}, ("id", "variants")),
        function("get_actual_rates", "Фактические себестоимости завершённого объекта: полученные закупки и явно распределённые затраты работ. Не рыночные цены, не цена продажи. В каталог не переносятся автоматически.", {"id": identifier}, ("id",)),
        function("record_work_actual_cost", "Предложить фактическую себестоимость конкретной работы завершённого заказа и основание распределения по данным пользователя. Это аналитика, не новое списание расходов. Только после подтверждения.",
                 {"id": identifier, "actual_cost_kopecks": {"type": "integer"}, "note": {"type": "string"}}, ("id", "actual_cost_kopecks", "note")),
        function("apply_actual_rate", "Предложить перенос проверенной фактической себестоимости в каталог. Цена продажи не меняется. Для новой расценки create=true; для существующей укажи catalog_id. Только после подтверждения.",
                 {"id": identifier, "catalog_id": identifier, "create": {"type": "boolean"}}, ("id",)),
    ]


def read(service, name, args):
    record_id = string(args.get("id", ""), "Запись", 80, True)
    if name == "preview_estimate_discount":
        quote = service.get("quotes", record_id)
        return service.route("POST", "estimate-workflow", ["discount", record_id], {}, {**args, "revision": quote["revision"]})[1]
    if name in ("get_actual_rates", "list_estimate_alternatives"):
        return service.route("GET", "estimate-workflow", ["rates" if name == "get_actual_rates" else "alternatives", record_id], {}, {})[1]
    return service.route("GET", "estimate-workflow", ["forecast" if name == "get_order_forecast" else "economics", record_id], {}, {})[1]


def prepare(service, name, args):
    service.write_access(True)
    if name == "create_estimate_alternatives":
        quote = service.get("quotes", string(args.get("id", ""), "Смета", 80, True))
        current = service.quote_view(quote)
        supplied = args.get("variants")
        if not isinstance(supplied, list) or not 1 <= len(supplied) <= 2:
            raise DomainError(400, "Выберите один или два варианта")
        variants = []
        for variant in supplied:
            if not isinstance(variant, dict):
                raise DomainError(400, "Проверьте вариант")
            indexes = variant.get("rows")
            if not isinstance(indexes, list) or not indexes or len(indexes) > 200 or any(type(index) is not int or not 1 <= index <= len(current["items"]) for index in indexes) or len(set(indexes)) != len(indexes):
                raise DomainError(400, "Укажите номера существующих позиций без повторений")
            discount = decimal(variant.get("discount_percent", "0"), "Скидка варианта", "0", "99.99")
            rows = [{**current["items"][index - 1], "included": True,
                     "discount": str(100 - (100 - Decimal(current["items"][index - 1]["discount"])) * (100 - discount) / 100)} for index in indexes]
            variants.append({"label": variant.get("label", ""), "items": rows})
        values = {"id": quote["id"], "revision": quote["revision"], "root_label": args.get("root_label", "Исходный вариант"), "variants": variants}
        result = service.route("POST", "estimate-workflow", ["alternatives", quote["id"]], {}, values)[1]
        values.update(variants=result["variants"][1:], confirmation=True)
        rows = [{"field": variant["label"], "before": None, "after": str(variant["amount_kopecks"]) + " коп.; " + str(len(variant["items"])) + " позиций"} for variant in result["variants"]]
        rows.append({"field": "Условия", "before": None, "after": "Создаются обычные сметы в пределах действующего тарифа. Принятие одного варианта закрывает остальные. Отправка отдельно."})
        summary = "Создать варианты предложения · " + quote["title"][:80]
    elif name in ("record_work_actual_cost", "apply_actual_rate"):
        from backend.actual_rates import candidate, completed
        quantity = service.get("construction_quantities", string(args.get("id", ""), "Работа или материал", 80, True))
        completed(service, quantity["object_id"])
        current = candidate(service, quantity)
        values = {"id": quantity["id"], "source_sha256": current["source_sha256"]}
        if name == "record_work_actual_cost":
            values.update(actual_cost_kopecks=integer(args.get("actual_cost_kopecks"), "Фактическая себестоимость", 1),
                          note=string(args.get("note", ""), "Основание распределения", 1000, True))
            rows = [{"field": "Фактическая себестоимость, коп.", "before": current["actual_cost_kopecks"], "after": values["actual_cost_kopecks"]},
                    {"field": "Основание распределения", "before": None, "after": values["note"]}]
            summary = "Указать фактическую себестоимость · " + quantity["title"][:80]
        else:
            if current["cost_price"] is None:
                raise DomainError(409, "Недостаточно фактических данных для расценки")
            catalog = service.get("catalog_items", string(args["catalog_id"], "Расценка", 80, True)) if args.get("catalog_id") else None
            values.update(confirmation=True, catalog_id=catalog["id"] if catalog else None, create=args.get("create") is True,
                          revision=catalog["revision"] if catalog else None)
            rows = [{"field": "Себестоимость единицы, коп.", "before": catalog["cost_price"] if catalog else None, "after": current["cost_price"]},
                    {"field": "Основание", "before": None, "after": current["basis"]},
                    {"field": "Цена продажи", "before": None, "after": "Не изменится. Новая расценка создаётся без цены продажи."}]
            summary = "Подтвердить себестоимость в каталоге · " + quantity["title"][:80]
    elif name == "set_minimum_margin":
        values = {"minimum_margin_pct": str(decimal(args.get("minimum_margin_pct"), "Минимальная маржа", "0", "100")),
                  "previous_minimum_margin_pct": str(margin_policy(service))}
        rows = [{"field": "Минимальная маржа, %", "before": values["previous_minimum_margin_pct"], "after": values["minimum_margin_pct"]}]
        summary = "Изменить минимальную маржу компании"
    elif name == "update_order_forecast":
        project = service.get("projects", string(args.get("id", ""), "Заказ", 80, True))
        remaining = integer(args.get("remaining_cost"), "Остаток расходов", 0)
        committed = integer(args.get("committed_cost", 0), "Обязательства", 0)
        if committed > remaining:
            raise DomainError(400, "Обязательства входят в остаток расходов")
        values = {"id": project["id"], "revision": project["revision"], "remaining_cost": remaining, "committed_cost": committed,
                  "note": string(args.get("note", ""), "Основание", 2000)}
        rows = [{"field": "Все оставшиеся расходы, коп.", "before": None, "after": remaining},
                {"field": "Из них обязательства, коп.", "before": None, "after": committed},
                {"field": "Основание", "before": None, "after": values["note"]}]
        summary = "Обновить прогноз расходов · " + project["name"][:80]
    else:
        result = read(service, "preview_estimate_discount", args)
        values = {"id": result["quote_id"], "revision": result["revision"], "percent": result["percent"], "confirmation": True,
                  "low_margin_confirmed": result["after"]["below_minimum"]}
        rows = [{"field": "Скидка, %", "before": None, "after": result["percent"]},
                {"field": "Прибыль, коп.", "before": result["before"]["profit"], "after": result["after"]["profit"]},
                {"field": "Маржа, %", "before": result["before"]["margin_pct"], "after": result["after"]["margin_pct"]}]
        if result["after"]["below_minimum"]:
            rows.append({"field": "Подтверждение руководителя", "before": None, "after": "Скидка снижает маржу ниже минимума компании. Нажимая «Применить», подтверждаю это."})
        if not result["after"]["cost_complete"]:
            rows.append({"field": "Проверка себестоимости", "before": None, "after": "Себестоимость заполнена не полностью. Прибыль неизвестна."})
        summary = "Применить скидку " + result["percent"] + "%"
    values["_preview"] = {"kind": "fields", "rows": rows}
    return values, summary


def apply(service, name, args):
    service.write_access(True)
    if name == "create_estimate_alternatives":
        service.assistant_workflow_creation = True
        try:
            return service.route("POST", "estimate-workflow", ["alternatives", args["id"], "apply"], {}, args)
        finally:
            service.assistant_workflow_creation = False
    if name in ("record_work_actual_cost", "apply_actual_rate"):
        return service.route("POST", "estimate-workflow", ["actual-cost" if name == "record_work_actual_cost" else "learn-rate", args["id"]], {}, args)
    if name == "set_minimum_margin":
        if str(margin_policy(service)) != args["previous_minimum_margin_pct"]:
            raise DomainError(409, "Минимальная маржа уже изменилась. Обновите предложение")
        return service.route("PATCH", "estimate-workflow", ["margin-policy"], {}, args)
    if name == "update_order_forecast":
        return service.route("PATCH", "estimate-workflow", ["forecast", args["id"]], {}, args)
    return service.route("POST", "estimate-workflow", ["discount", args["id"], "apply"], {}, args)
