"""Conservative, deterministic suggestions for costs often omitted from estimates.

Suggestions never alter totals, infer quantities or prices, or silently edit a quote.
A suggestion must be explicitly accepted in the editor before it becomes a line.
"""

import re


def _normalize(value):
    return str(value or "").lower().replace("ё", "е")


def _has(text, patterns):
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


# Check for the same *cost*, not simply for a word like "material" in an item.
_ALREADY = {
    "consumables": (r"расходн", r"укрывн", r"малярн.{0,12}(лент|скотч|валик|кист)", r"мешк.{0,24}мусор"),
    "delivery": (r"доставк", r"транспортн.{0,15}(расход|услуг|затрат)", r"логистик", r"перевозк.{0,15}материал"),
    "waste": (r"вывоз.{0,24}мусор", r"вывоз.{0,24}отход", r"утилиз", r"вывоз.{0,24}строител", r"контейнер.{0,20}мусор"),
}
_SKIP = {
    "consumables": (r"без\s+расходник", r"расходник.{0,30}не\s+нужн", r"расходник.{0,30}включен"),
    "delivery": (r"без\s+доставк", r"самовывоз", r"доставк.{0,30}включен", r"доставк.{0,30}не\s+(нужн|требу)", r"привез.{0,20}сам"),
    "waste": (r"без\s+вывоз", r"вывоз.{0,30}не\s+(нужн|требу)", r"мусор.{0,30}вывоз.{0,20}сам", r"вывоз.{0,30}включен"),
}
_WORK = (r"ремонт", r"отделк", r"покраск", r"окраск", r"шпаклев", r"штукатур", r"демонтаж", r"снос", r"укладк", r"облицов", r"плиточн", r"монтаж", r"ламинат", r"паркет", r"электромонтаж", r"сантех")
_PAINT = (r"покраск", r"окраск", r"малярн", r"покрасит")
_TILING = (r"укладк.{0,25}плит", r"облицов", r"плиточн", r"кафел", r"керамогранит")
_PLASTER = (r"штукатур", r"шпаклев", r"шпатлев")
_DEMO = (r"демонтаж", r"снос", r"разборк", r"сняти.{0,22}(обо|плит|покрыт)", r"удалени.{0,22}(обо|плит|покрыт)", r"штроблен")
_MATERIAL = (r"материал", r"краск", r"грунтовк", r"плитк", r"кафел", r"ламинат", r"паркет", r"гипсокартон", r"смес[ьи]", r"обо[ие]", r"кабел", r"труб", r"цемент", r"песок", r"крепеж")


def recommend(items, description=""):
    """Return at most three review-only proposals based on known scope.

    Each proposal includes a reason and a unit. Quantity and cost are deliberately
    absent: the UI asks the user to verify them before including the item.
    """
    if not isinstance(items, list):
        return []
    rows = [row for row in items[:200] if isinstance(row, dict)]
    titles = " ".join(_normalize(row.get("name"))[:200] for row in rows)
    context = (_normalize(description)[:8000] + " " + titles).strip()
    existing = " ".join(
        _normalize(row.get("name"))[:200] for row in rows
        if row.get("included", True) is not False or row.get("optional") is True
    )
    if not context or not _has(context, _WORK):
        return []

    found = []

    def offer(kind, name, reason, unit="усл."):
        if _has(existing, _ALREADY[kind]) or _has(context, _SKIP[kind]):
            return
        # An already accepted suggestion must not be offered a second time.
        if _normalize(name) in existing:
            return
        found.append({"kind": kind, "name": name, "reason": reason, "unit": unit})

    if _has(context, _PAINT):
        offer("consumables", "Малярные расходники и укрывные материалы",
              "Проверьте необходимость плёнки, ленты, валиков и кистей. Состав и количество зависят от работ.", "компл.")
    elif _has(context, _TILING):
        offer("consumables", "Расходники для укладки плитки",
              "Проверьте клей, затирку, крестики и СВП. Учтите только то, что не включено в другие позиции.", "компл.")
    elif _has(context, _PLASTER):
        offer("consumables", "Расходники для штукатурных работ",
              "Проверьте грунтовку, сетку, маяки и инструментальные расходники без повторного учёта.", "компл.")
    elif _has(context, _DEMO):
        offer("consumables", "Мешки и расходники для демонтажа",
              "Проверьте упаковку строительного мусора и защитные расходники.", "компл.")
    else:
        offer("consumables", "Расходные материалы для ремонтных работ",
              "Проверьте крепёж и вспомогательные материалы, которых нет в смете.", "компл.")

    has_materials = any(
        _normalize(row.get("category")) in ("material", "materials", "материал", "материалы")
        or (_has(_normalize(row.get("name")), _MATERIAL)
            and not _has(_normalize(row.get("name")),
                         (r"демонтаж", r"снос", r"сняти", r"покраск", r"окраск",
                          r"укладк", r"облицов", r"монтаж", r"замен", r"ремонт")))
        for row in rows if not (row.get("optional") is True and row.get("included") is False)
    ) or _has(_normalize(description), (r"закупк.{0,22}материал", r"материал.{0,22}(закуп|привоз|достав)"))
    if has_materials:
        offer("delivery", "Доставка материалов на объект",
              "Проверьте адрес, объём груза, разгрузку и включена ли доставка в цену поставщика.")
    if _has(context, _DEMO):
        offer("waste", "Вывоз и утилизация строительного мусора",
              "Проверьте объём отходов, погрузку, контейнер и местные требования к утилизации.")
    return found[:3]
