"""AR measurement import. Device provides dimensions, server verifies and computes.

Never treats LiDAR/camera measurements as verified engineering surveys; any
estimate changes still need a deliberate review and publication action.
"""
from decimal import Decimal, ROUND_CEILING
from backend.business import DomainError, choice, string
from backend.construction_math import decimal_value, length_in_metres


def preview(data):
    rooms=data.get("rooms") if isinstance(data,dict) else None
    if not isinstance(rooms,list) or not 1 <= len(rooms) <= 12:
        raise DomainError(400,"Передайте от 1 до 12 измеренных помещений")
    results=[]
    for raw in rooms:
        if not isinstance(raw,dict):
            raise DomainError(400,"Некорректный замер помещения")
        name=string(raw.get("name",""),"Помещение",120,True)
        unit=choice(raw.get("unit","м"),("мм","см","м"),"Единица")
        dimensions={
            k:length_in_metres(raw.get(k),unit)
            for k in ("length","width","height")
        }
        if any(not Decimal("0.5") <= value <= Decimal("100") for value in dimensions.values()):
            raise DomainError(400,"Проверьте размеры помещения: от 0,5 до 100 м")
        openings=decimal_value(raw.get("openings_m2","0"),"Проёмы")
        floor=dimensions["length"]*dimensions["width"]
        perimeter=(dimensions["length"]+dimensions["width"])*2
        walls=perimeter*dimensions["height"]
        if openings>=walls:
            raise DomainError(400,"Площадь проёмов должна быть меньше площади стен")
        rate=decimal_value(raw.get("mix_kg_per_m2","0"),"Расход смеси",maximum=Decimal(100))
        bag=decimal_value(raw.get("bag_kg","25"),"Вес мешка",minimum=Decimal("0.1"),maximum=Decimal(100))
        waste=decimal_value(raw.get("waste_percent","0"),"Запас",maximum=Decimal(100))
        net_walls=walls-openings
        needed_kg=net_walls*rate*(1+waste/100)
        bags=int((needed_kg/bag).to_integral_value(rounding=ROUND_CEILING))
        results.append({
            "name":name,"source":"ar","verified":False,
            "length_m":str(dimensions["length"]),"width_m":str(dimensions["width"]),
            "height_m":str(dimensions["height"]),"floor_m2":str(floor),
            "perimeter_m":str(perimeter),"gross_walls_m2":str(walls),
            "openings_m2":str(openings),"net_walls_m2":str(net_walls),
            "volume_m3":str(floor*dimensions["height"]),
            "mix_kg":str(needed_kg),"bags":bags,"bag_kg":str(bag),
            "mix_kg_per_m2":str(rate),"waste_percent":str(waste)
        })
    return results


def handle(service,obj,method,rest,data):
    if method=="POST" and rest==["scan","preview"]:
        service.h.throttle("scan-preview:"+service.user["id"],20,60)
        return 200,{"rooms":preview(data),"requires_review":True}
    if method=="POST" and rest==["scan","import"]:
        service.h.throttle("scan-import:"+service.user["id"],4,300)
        if data.get("review_confirmed") is not True:
            raise DomainError(400,"Проверьте размеры и подтвердите импорт")
        rooms=preview(data)
        count=service.con.execute(
            "SELECT count(*) FROM construction_zones WHERE object_id=? AND workspace_id=?",
            (obj["id"],service.wid)
        ).fetchone()[0]
        if count+len(rooms)>100:
            raise DomainError(409,"На объекте не может быть больше 100 помещений")
        from backend.construction import add_zone
        zones=[]
        for r in rooms:
            code,result=add_zone(service,obj,{
                "name":r["name"],"kind":"room","dimension_unit":"м",
                "length":r["length_m"],"width":r["width_m"],
                "height":r["height_m"],"openings_m2":r["openings_m2"],
                "notes":"Обмер AR. Требует проверки размеров вручную."
            })
            zones.append(result["zone"])
        # Existing formulas are recalculated in one transaction; active quote
        # associations are invalidated rather than silently changing offers.
        from backend.construction import recalculate,invalidate_quote
        recalculate(service,obj)
        invalidate_quote(service,obj)
        return 201,{"zones":zones,"calculations":rooms,"requires_review":True}
    raise DomainError(404,"Маршрут обмеров не найден")
