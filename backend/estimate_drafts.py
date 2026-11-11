"""AI estimate drafts: strict normalisation of the model's create_quotes call.

The model proposes sections, lines, units, quantities and prices; the server
checks every value, refuses inconsistent data and computes all money with the
same deterministic quote math as manual editing (backend.business.calculate).
Unknown prices stay 0 and estimated prices are labelled, so a draft is never
presented as a confirmed professional calculation.
"""
from backend.business import DomainError, calculate, string

PRICE_STATUSES = ("confirmed", "estimate", "unknown")
KINDS = ("work", "material")
ESTIMATE_NOTE = "Цена ориентировочная — уточните."
UNKNOWN_NOTE = "Цена неизвестна — укажите."
MAX_ASSUMPTIONS = 12

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Понятное название работы или материала"},
        "quantity": {"type": "string", "description": "Количество числом, например \"20\" или \"12.5\""},
        "unit": {"type": "string", "description": "Единица: м², м, м³, шт., кг, л, упак., компл., усл., т"},
        "unit_price": {"type": "integer", "description": "Цена за единицу в копейках. Неизвестна — 0 и price_status=unknown."},
        "category": {"type": "string", "description": "Раздел сметы: «Демонтаж», «Электромонтаж», «Материалы: пол» и т. п."},
        "kind": {"type": "string", "enum": list(KINDS), "description": "work — работа, material — материал"},
        "price_status": {
            "type": "string", "enum": list(PRICE_STATUSES),
            "description": "confirmed — цена пользователя, из расценок или проверенного источника; "
                           "estimate — ориентировочная оценка; unknown — цены нет (unit_price=0)",
        },
        "description": {"type": "string", "description": "Короткое пояснение: что входит, откуда объём"},
    },
    "required": ["name", "quantity", "unit", "unit_price", "category", "kind", "price_status"],
    "additionalProperties": False,
}

EXTRA_PROPERTIES = {
    "assumptions": {
        "type": "array", "maxItems": MAX_ASSUMPTIONS, "items": {"type": "string"},
        "description": "Явные предварительные допущения: размеры, объёмы, регион, класс материалов, которых не было в запросе",
    },
    "region": {"type": "string", "description": "Регион или город работ, если известен"},
}


def _key(row):
    return (row["category"].casefold(), row["name"].casefold(), row["unit"].casefold())



def _catalog_key(name, unit):
    """Only exact normalized work/material names and units are price-compatible."""
    return (" ".join(name.casefold().replace("ё", "е").split()),
            " ".join(unit.casefold().split()))


def enrich_catalog_prices(service, args):
    """Fill *unknown* RUB prices from unambiguous workspace-owned catalogue rows.

    Never override a user/model-supplied price, apply rates from another
    workspace, mix units or silently guess that two different items are alike.
    A catalogue price is a stored rate, not proof of a current market quote.
    """
    items = args.get("items")
    if (args.get("currency") or "RUB") != "RUB" or not isinstance(items, list):
        return args
    missing = [item for item in items if isinstance(item, dict)
               and item.get("price_status", "unknown") == "unknown"
               and item.get("unit_price", 0) == 0
               and isinstance(item.get("name"), str)
               and isinstance(item.get("unit"), str)]
    if not missing:
        return args

    rows = service.con.execute(
        "SELECT name,unit,price FROM catalog_items "
        "WHERE workspace_id=? AND price>0 LIMIT 5000", (service.wid,)
    ).fetchall()
    prices = {}
    for row in rows:
        key = _catalog_key(row["name"], row["unit"])
        value = row["price"]
        if key not in prices:
            prices[key] = value
        elif prices[key] != value:
            prices[key] = None  # conflicting saved rates require human review

    filled = []
    for item in items:
        if item not in missing:
            filled.append(item)
            continue
        price = prices.get(_catalog_key(item["name"], item["unit"]))
        if type(price) is not int or price <= 0:
            filled.append(item)
            continue
        note = "Расценка из вашего каталога Сметры; проверьте актуальность."
        description = item.get("description") or ""
        if not isinstance(description, str):
            filled.append(item)  # let the regular validator report bad input
            continue
        filled.append({
            **item, "unit_price": price, "price_status": "confirmed",
            "description": (description + " " + note).strip()[:1000],
        })
    return {**args, "items": filled}


def normalize(args):
    """Validate a create_quotes call and return (arguments for /quotes, preview)."""
    items = args.get("items")
    if not isinstance(items, list) or not items:
        raise DomainError(400, "Добавьте позиции сметы: работы и материалы с количеством и единицей")
    if len(items) > 200:
        raise DomainError(400, "В смете может быть до 200 позиций")
    lines, seen = [], set()
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise DomainError(400, f"Позиция {index}: некорректный формат")
        kind = item.get("kind", "work")
        if kind not in KINDS:
            raise DomainError(400, f"Позиция {index}: kind должен быть work или material")
        status = item.get("price_status", "unknown")
        if status not in PRICE_STATUSES:
            raise DomainError(400, f"Позиция {index}: неизвестный price_status")
        price = item.get("unit_price", 0)
        if type(price) is not int or price < 0:
            raise DomainError(400, f"Позиция {index}: цена — целое число копеек не меньше 0")
        if status == "unknown" and price:
            raise DomainError(400, f"Позиция {index}: при price_status=unknown цена должна быть 0")
        if status != "unknown" and not price:
            status = "unknown"
        line = {
            "name": string(item.get("name", ""), f"Позиция {index}", 200, True),
            "quantity": str(item.get("quantity", "1")).strip().replace(",", "."),
            "unit": string(item.get("unit", "") or "шт.", f"Единица позиции {index}", 30, True),
            "unit_price": price,
            "category": string(item.get("category", "") or ("Материалы" if kind == "material" else "Работы"), "Раздел", 100),
            "description": string(item.get("description", ""), "Пояснение", 1000),
            "visual_role": kind,
        }
        note = ESTIMATE_NOTE if status == "estimate" else UNKNOWN_NOTE if status == "unknown" else ""
        if note and note not in line["description"]:
            line["description"] = (line["description"] + " " + note).strip()[:1000]
        if _key(line) in seen:
            raise DomainError(409, f"Позиция {index} «{line['name']}» повторяется в разделе «{line['category']}». Объедините количество в одну строку")
        seen.add(_key(line))
        lines.append((line, status))
    # Group lines by section in the order sections first appear, so the
    # stored quote reads as a structured document.
    order = []
    for line, _ in lines:
        if line["category"] not in order:
            order.append(line["category"])
    lines.sort(key=lambda pair: order.index(pair[0]["category"]))
    computed, total, _ = calculate([line for line, _ in lines], allow_zero_total=True)

    assumptions = args.get("assumptions") or []
    if not isinstance(assumptions, list) or len(assumptions) > MAX_ASSUMPTIONS:
        raise DomainError(400, f"Допущений может быть до {MAX_ASSUMPTIONS}")
    assumptions = [string(value, "Допущение", 300, True) for value in assumptions]
    region = string(args.get("region", "") or "", "Регион", 120)
    description = string(args.get("description", "") or "", "Описание", 3000)
    notes = []
    if region:
        notes.append("Регион: " + region + ".")
    if assumptions:
        notes.append("Допущения ИИ (проверьте):\n" + "\n".join("• " + value for value in assumptions))
    statuses = [status for _, status in lines]
    if "estimate" in statuses or "unknown" in statuses:
        notes.append("Черновик ИИ: часть цен ориентировочная или не указана — это не окончательный расчёт.")
    full_description = "\n\n".join(part for part in [description, *notes] if part)[:5000]

    sections = []
    for name in order:
        rows = [
            {"name": row["name"], "unit": row["unit"], "quantity": row["quantity"], "unit_price": row["unit_price"],
             "subtotal": row["subtotal"], "kind": line["visual_role"], "price_status": status, "description": row["description"]}
            for row, (line, status) in zip(computed, lines) if row["category"] == name
        ]
        sections.append({"name": name, "rows": rows, "subtotal": sum(row["subtotal"] for row in rows)})
    arguments = {
        "title": string(args.get("title", "") or "Смета", "Название", 120, True),
        "client": string(args.get("client", "") or "Клиент не указан", "Клиент", 120, True),
        "description": full_description,
        "currency": args.get("currency") or "RUB",
        "items": [line for line, _ in lines],
    }
    for optional in ("client_id", "terms", "due_date"):
        if args.get(optional):
            arguments[optional] = args[optional]
    preview = {
        "kind": "quote_draft",
        "title": arguments["title"],
        "currency": arguments["currency"],
        "sections": sections,
        "total": total,
        "assumptions": assumptions,
        "region": region,
        "counts": {
            "lines": len(lines),
            "works": sum(1 for line, _ in lines if line["visual_role"] == "work"),
            "materials": sum(1 for line, _ in lines if line["visual_role"] == "material"),
            "estimated": statuses.count("estimate"),
            "unknown": statuses.count("unknown"),
        },
    }
    return arguments, preview
