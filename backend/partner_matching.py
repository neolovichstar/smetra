"""Partner material offers for the assistant.

Deterministic server code decides what to offer; the model only presents it:

- only materials the user actually needs: lines of the user's own estimate, or
  materials the user named, never a generic product feed;
- work lines ("укладка плитки", "монтаж ...") are not products and are skipped;
- only available products of active partners with a currently verified domain;
- fair across partners: among equally relevant products the partner with fewer
  offers in this answer goes first, and ties rotate per user and per day, so
  no single partner is shown by default;
- the buy link goes through the tracked /api/partners/out/{id} redirect.
"""
import datetime as dt
import hashlib
import os
import re

MAX_MATERIALS = 20
TIE_BAND = 0.85  # candidates within 85% of the best score count as equally relevant
MIN_SCORE = 0.5

WORK_WORDS = {
    "укладк", "монтаж", "демонт", "устрой", "устан", "покрас", "окрас",
    "работ", "услуг", "достав", "вывоз", "разбор", "подгот", "выравн", "нанес", "облиц", "прокла",
    "замен", "ремон", "сборк", "разметк", "резк", "сверл", "заливк", "стяжк", "оклейк", "поклейк",
}
# Where the material goes, not what it is. Doors, windows and baths are products, so they stay.
PLACE_EXACT = {"стен", "пол", "полу", "шт", "м2", "кв", "для", "под", "без", "или", "при", "все"}
PLACE_PREFIX = {"стен", "пото", "комн", "сану", "кухн", "кори", "балк", "метр"}
ENDINGS = sorted("ами ями ого его ому ему ыми ими ых их ая яя ое ее ые ие ой ей ий ый ую юю ом ем ах ях ов ев а я ы и у ю е о ь".split(),
                 key=len, reverse=True)
WORD_RE = re.compile(r"[a-zа-яё0-9]+(?:[x×][0-9]+)*", re.IGNORECASE)


def stem(word):
    word = word.casefold().replace("ё", "е").replace("×", "x")
    if word.isdigit() or any(ch.isdigit() for ch in word):
        return word
    for ending in ENDINGS:
        if len(word) - len(ending) >= 3 and word.endswith(ending):
            word = word[: -len(ending)]
            break
    return word[:6]


def tokens(text):
    result = []
    for raw in WORD_RE.findall(str(text or "")):
        if len(raw) < 2 or (len(raw) < 3 and not any(ch.isdigit() for ch in raw)):
            continue
        token = stem(raw)
        if token in PLACE_EXACT or token[:4] in PLACE_PREFIX:
            continue
        result.append(token)
    return result


def is_work(name):
    """A line that starts with an operation ("Укладка плитки") is labour, not a product."""
    words = WORD_RE.findall(str(name or "").casefold())
    if not words:
        return False
    # "Шпаклевание", "грунтование", "нанесение": the operation, while "шпаклёвка" is the product.
    if re.search(r"(ание|ение|ания|ения|ировка)$", words[0]):
        return True
    head = stem(words[0])
    return any(head[:5] == work[:5] if len(work) >= 5 else head.startswith(work) for work in WORK_WORDS)


def _same(a, b):
    if any(ch.isdigit() for ch in a) or any(ch.isdigit() for ch in b):
        return a == b
    n = min(len(a), len(b), 5)
    return n >= 3 and a[:n] == b[:n]


def score(need, product):
    """Share of the material's words found in the product title; the first word (the noun) is required."""
    if not need or not product:
        return 0.0
    if not any(_same(need[0], p) for p in product):
        return 0.0
    hits = sum(1 for word in need if any(_same(word, p) for p in product))
    return hits / len(need)


def _clean_materials(materials):
    result, seen = [], set()
    for item in materials[:MAX_MATERIALS * 3]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()[:200]
        if not name or is_work(name):
            continue
        words = tokens(name)
        if not words or tuple(words) in seen:
            continue
        seen.add(tuple(words))
        quantity = str(item.get("quantity", "") or "").strip()[:20]
        unit = str(item.get("unit", "") or "").strip()[:30]
        result.append({"name": name, "quantity": quantity, "unit": unit, "words": words})
        if len(result) >= MAX_MATERIALS:
            break
    return result


def _candidates(con, words):
    """Products of verified, active partners that share the material's main word."""
    from backend.partner_integrations import VERIFICATION_TTL
    import time

    head = words[0]
    pattern = "%" + head[:5].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return con.execute(
        "SELECT p.id,p.name,p.search_name,p.price_kopecks,p.partner_id,a.name AS partner "
        "FROM partner_products p JOIN partner_accounts a ON a.id=p.partner_id "
        "JOIN partner_domain_verifications v ON v.partner_id=a.id AND v.domain=a.allowed_host AND v.status='verified' "
        "WHERE a.active=1 AND p.available=1 AND v.verified_at>? AND p.search_name LIKE ? ESCAPE '\\' "
        "ORDER BY p.id LIMIT 200",
        (int(time.time()) - VERIFICATION_TTL, pattern),
    ).fetchall()


def _rotation(user_id, partner_id):
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    return hashlib.sha256(f"{user_id}:{day}:{partner_id}".encode()).hexdigest()


def offers_for(con, user_id, materials, origin=None):
    origin = (origin or os.getenv("PUBLIC_ORIGIN") or "https://smetra.online").rstrip("/")
    needs = _clean_materials(materials)
    scored = []
    for need in needs:
        options = []
        for row in _candidates(con, need["words"]):
            value = score(need["words"], tokens(row["name"]))
            if value >= MIN_SCORE:
                options.append((value, row))
        scored.append((need, options))
    # Materials with fewer options choose first, so a rare item is not left
    # without its only partner because of the fairness balance.
    order = sorted(range(len(scored)), key=lambda i: (len(scored[i][1]), i))
    used = {}
    picked = {}
    for index in order:
        need, options = scored[index]
        if not options:
            continue
        best = max(value for value, _ in options)
        band = [(value, row) for value, row in options if value >= best * TIE_BAND]
        value, row = min(band, key=lambda item: (
            used.get(item[1]["partner_id"], 0),          # spread across partners
            -round(item[0], 2),                          # then relevance
            _rotation(user_id, item[1]["partner_id"]),   # then a daily rotation
            item[1]["price_kopecks"],
        ))
        used[row["partner_id"]] = used.get(row["partner_id"], 0) + 1
        picked[index] = {
            "product_id": row["id"], "product": row["name"], "price_kopecks": row["price_kopecks"],
            "partner": row["partner"], "buy_url": f"{origin}/api/partners/out/{row['id']}",
            "relevance": round(value, 2),
        }
    items, missing = [], []
    for index, (need, _) in enumerate(scored):
        entry = {"material": need["name"], "quantity": need["quantity"], "unit": need["unit"]}
        if index in picked:
            items.append({**entry, "offer": picked[index]})
        else:
            missing.append(need["name"])
    return {
        "offers": items,
        "not_found": missing,
        "partners": len(used),
        "label": "Партнёрское предложение",
        "note": "Цены и наличие — по данным магазина-партнёра. Покупка оформляется на сайте магазина.",
    }


def offers_for_quote(service, quote_id):
    """Material lines of one estimate the user can see."""
    import json

    service.get("quotes", quote_id)  # workspace access check: raises 404 for others' estimates
    rows = service.con.execute(
        "SELECT data FROM quote_items WHERE quote_id=? ORDER BY position", (quote_id,)
    ).fetchall()
    materials = []
    for row in rows:
        item = json.loads(row["data"])
        if item.get("included") is False:
            continue
        materials.append({"name": item.get("product_title") or item.get("name", ""),
                          "quantity": item.get("quantity", ""), "unit": item.get("unit", "")})
    return offers_for(service.con, service.user["id"], materials)
