"""Premium product-source monitoring for Smetra.

External data is stored as observations and product metadata. It never overwrites
quote arithmetic or approved prices without an explicit user edit.
"""
import hashlib
import html
import ipaddress
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser

from backend import business


DEFAULT_HOSTS = ("petrovich.ru", "leroymerlin.ru", "lemanapro.ru", "vseinstrumenti.ru")
MAX_PAGE_BYTES = 1_500_000
FETCH_TIMEOUT = 8


def _now():
    return int(time.time())


def _id():
    return str(uuid.uuid4())


def _allowed_hosts():
    raw = os.getenv("PRODUCT_SCRAPE_ALLOWED_HOSTS", "")
    values = [part.strip().lower().strip(".") for part in raw.split(",") if part.strip()]
    return tuple(values or DEFAULT_HOSTS)


def _host_allowed(host):
    host = (host or "").lower().rstrip(".")
    return any(host == allowed or host.endswith("." + allowed) for allowed in _allowed_hosts())


def validate_url(value, resolve_dns=True):
    if not isinstance(value, str) or not 8 <= len(value) <= 2048:
        raise business.DomainError(400, "Укажите корректную ссылку на товар")
    try:
        parts = urllib.parse.urlsplit(value.strip())
        host = parts.hostname
        port = parts.port
    except ValueError:
        raise business.DomainError(400, "Некорректный адрес товара") from None
    if (parts.scheme.lower() != "https" or not host or parts.username or parts.password
            or port not in (None, 443) or parts.fragment
            or not _host_allowed(host) or "%" in host):
        raise business.DomainError(400, "Этот домен не разрешён для безопасной проверки цены")
    host = host.encode("idna").decode("ascii").lower().rstrip(".")
    if host in ("localhost",) or "." not in host:
        raise business.DomainError(400, "Адрес товара недопустим")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise business.DomainError(400, "IP-адреса нельзя использовать как источник товара")
    if resolve_dns:
        try:
            addresses = {item[4][0].split("%", 1)[0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        except OSError:
            raise business.DomainError(502, "Не удалось проверить адрес магазина") from None
        if not addresses:
            raise business.DomainError(502, "Магазин не найден в DNS")
        for address in addresses:
            try:
                parsed_ip = ipaddress.ip_address(address)
            except ValueError:
                raise business.DomainError(400, "Некорректный сетевой адрес магазина") from None
            if not parsed_ip.is_global:
                raise business.DomainError(400, "Запрос к внутреннему сетевому адресу запрещён")
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if not k.lower().startswith("utm_") and k.lower() not in
             {"yclid", "gclid", "fbclid", "from", "ref", "source"}]
    canonical = urllib.parse.urlunsplit(("https", host, parts.path or "/", urllib.parse.urlencode(sorted(query)), ""))
    return canonical, host


class _NoCrossHostRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        old = urllib.parse.urlsplit(req.full_url)
        new = urllib.parse.urlsplit(newurl)
        try:
            old_host, new_host = old.hostname or "", new.hostname or ""
            new_port = new.port
        except ValueError:
            return None
        if (self.count > 2 or old.scheme != "https" or new.scheme != "https" or
                old_host.lower() != new_host.lower() or new_port not in (None, 443) or
                not _host_allowed(new_host)):
            return None
        try:
            validate_url(newurl, resolve_dns=False)
        except business.DomainError:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.metas = {}
        self.json_scripts = []
        self._script_type = ""
        self._script = []
        self._in_title = False
        self.title_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = {str(k).lower(): (v or "") for k, v in attrs}
        tag = tag.lower()
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
            value = attrs.get("content", "")
            if key and value:
                self.metas.setdefault(key, value[:4000])
        elif tag == "script":
            self._script_type = attrs.get("type", "").split(";", 1)[0].strip().lower()
            self._script = []
        elif tag == "title":
            self._in_title = True

    def handle_data(self, data):
        if self._script_type == "application/ld+json":
            if sum(map(len, self._script)) < 250_000:
                self._script.append(data)
        if self._in_title and sum(map(len, self.title_parts)) < 500:
            self.title_parts.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "script":
            if self._script_type == "application/ld+json":
                raw = "".join(self._script).strip()
                if raw:
                    self.json_scripts.append(raw[:250_000])
            self._script_type, self._script = "", []
        elif tag == "title":
            self._in_title = False


def _walk_products(value):
    if isinstance(value, list):
        for item in value:
            yield from _walk_products(item)
    elif isinstance(value, dict):
        typ = value.get("@type", [])
        types = [typ] if isinstance(typ, str) else typ if isinstance(typ, list) else []
        if any(str(t).lower() == "product" for t in types):
            yield value
        graph = value.get("@graph")
        if graph is not None:
            yield from _walk_products(graph)
        for key in ("mainEntity", "item", "subjectOf"):
            if key in value and isinstance(value[key], (dict, list)):
                yield from _walk_products(value[key])


def _price_to_kopecks(value):
    if isinstance(value, bool) or value is None:
        return None
    raw = str(value).strip()
    raw = re.sub(r"[^0-9,\.\- ]", "", raw).replace(" ", "")
    if not raw or raw.count("-") > 1:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        amount = Decimal(raw)
        if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
            return None
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def _availability(value):
    text = str(value or "").lower()
    if any(token in text for token in ("outofstock", "soldout", "нет в наличии", "нет в продаже")):
        return "out_of_stock"
    if any(token in text for token in ("preorder", "предзаказ")):
        return "preorder"
    if any(token in text for token in ("backorder", "под заказ")):
        return "backorder"
    if any(token in text for token in ("instock", "в наличии", "есть в наличии")):
        return "in_stock"
    return "unknown"


def _first_image(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return next((x for x in value if isinstance(x, str) and x.startswith("https://")), "")
    if isinstance(value, dict):
        url = value.get("url") or value.get("contentUrl")
        return url if isinstance(url, str) else ""
    return ""


def _extract(page, source_url, hostname):
    title = brand = sku = image_url = unit = ""
    price = None
    availability = "unknown"
    currency = "RUB"
    attrs = {}
    parser = _Page()
    try:
        parser.feed(page.decode("utf-8", "replace"))
    except Exception:
        pass
    products = []
    for raw in parser.json_scripts:
        try:
            products.extend(_walk_products(json.loads(raw)))
        except (ValueError, TypeError, RecursionError):
            continue
    if products:
        product = products[0]
        title = str(product.get("name") or "")[:300]
        brand_value = product.get("brand")
        brand = (brand_value.get("name", "") if isinstance(brand_value, dict) else brand_value or "")
        brand = str(brand)[:160]
        sku = str(product.get("sku") or product.get("mpn") or product.get("productID") or "")[:120]
        image_url = _first_image(product.get("image"))
        raw_attrs = product.get("additionalProperty", [])
        if isinstance(raw_attrs, list):
            for item in raw_attrs[:40]:
                if isinstance(item, dict) and item.get("name"):
                    attrs[str(item["name"])[:80]] = str(item.get("value", ""))[:300]
        offers = product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            price = _price_to_kopecks(offers.get("price") or offers.get("lowPrice"))
            currency = str(offers.get("priceCurrency") or "RUB").upper()[:3]
            availability = _availability(offers.get("availability"))
            unit = str(offers.get("unitText") or "")[:40]
    meta = parser.metas
    title = title or meta.get("og:title") or meta.get("twitter:title") or meta.get("title") or "".join(parser.title_parts)
    brand = brand or meta.get("product:brand") or meta.get("brand", "")
    sku = sku or meta.get("product:retailer_item_id") or meta.get("sku", "")
    image_url = image_url or meta.get("og:image") or meta.get("twitter:image") or ""
    if price is None:
        price = _price_to_kopecks(meta.get("product:price:amount") or meta.get("og:price:amount") or meta.get("price"))
    currency = (meta.get("product:price:currency") or meta.get("og:price:currency") or currency or "RUB").upper()[:3]
    availability = availability if availability != "unknown" else _availability(meta.get("product:availability") or meta.get("availability"))
    if image_url:
        image_parts = urllib.parse.urlsplit(urllib.parse.urljoin(source_url, image_url))
        if image_parts.scheme != "https" or not image_parts.hostname:
            image_url = ""
        else:
            image_url = urllib.parse.urlunsplit((image_parts.scheme, image_parts.netloc, image_parts.path, image_parts.query, ""))
    title = html.unescape(str(title or "").strip())[:300]
    if not title and price is None:
        raise business.DomainError(422, "Не удалось извлечь название или цену. Проверьте ссылку вручную.")
    return {
        "url": source_url, "hostname": hostname, "product_title": title,
        "brand": str(brand)[:160], "sku": str(sku)[:120], "image_url": image_url[:2048],
        "price_kopecks": price, "currency": currency if re.fullmatch(r"[A-Z]{3}", currency) else "RUB",
        "unit": unit, "availability": availability, "product_attributes": attrs,
        "observed_at": _now(),
    }


def fetch_product(value):
    normalized_url, hostname = validate_url(value)
    request = urllib.request.Request(normalized_url, headers={
        "User-Agent": "SmetraProductMonitor/1.0 (+https://smetra.online)",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
    }, method="GET")
    opener = urllib.request.build_opener(_NoCrossHostRedirect())
    try:
        with opener.open(request, timeout=FETCH_TIMEOUT) as response:
            final_url = response.geturl()
            final, final_host = validate_url(final_url, resolve_dns=False)
            if final_host != hostname or response.status < 200 or response.status >= 300:
                raise business.DomainError(422, "Магазин перенаправил запрос на другой адрес")
            chunks = []
            total = 0
            while True:
                chunk = response.read(min(65536, MAX_PAGE_BYTES + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_PAGE_BYTES:
                    raise business.DomainError(413, "Страница товара превышает допустимый размер")
                chunks.append(chunk)
            content_type = response.headers.get_content_type()
            if content_type not in ("text/html", "application/xhtml+xml"):
                raise business.DomainError(415, "Ссылка не ведёт на HTML-страницу товара")
            result = _extract(b"".join(chunks), final, final_host)
            result["normalized_url"] = normalized_url
            result["fingerprint"] = fingerprint(result)
            result["http_status"] = response.status
            return result
    except business.DomainError:
        raise
    except urllib.error.HTTPError as err:
        if 300 <= err.code < 400:
            raise business.DomainError(422, "Магазин перенаправил запрос. Используйте актуальную ссылку.") from None
        raise business.DomainError(502, f"Магазин вернул HTTP {err.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise business.DomainError(502, "Магазин временно недоступен") from None


def fingerprint(product):
    stable = {key: product.get(key) for key in ("product_title", "brand", "sku", "price_kopecks", "currency", "unit", "availability", "image_url", "product_attributes")}
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _require_quote_writer(service):
    if service.role not in ("owner", "admin", "manager", "member"):
        raise business.DomainError(403, "У вас нет прав изменять строки сметы")


def _premium_access(service):
    try:
        from backend.entitlements import workspace_feature_access
    except ModuleNotFoundError:
        from entitlements import workspace_feature_access
    decision = workspace_feature_access(service.con, service.wid, "product_monitor", _now())
    if not decision["allowed"]:
        raise business.DomainError(402, "Эта функция доступна в тарифах «PRO Плюс» и «TEAM»")
    return {"plan": decision["tier"], "team": decision["tier"] == "team"}


def _quote_item(service, quote_id, item_id):
    quote = service.con.execute("SELECT * FROM quotes WHERE id=? AND workspace_id=?", (quote_id, service.wid)).fetchone()
    if not quote:
        raise business.DomainError(404, "Смета не найдена")
    if quote["status"] != "draft" or int(quote["published_version"] or 0) > 0:
        raise business.DomainError(409, "Источник товара можно привязать к черновику. Создайте новую редакцию перед изменением опубликованной сметы.")
    item = None
    payload = None
    for candidate in service.con.execute("SELECT * FROM quote_items WHERE quote_id=? ORDER BY position", (quote_id,)).fetchall():
        try:
            item_data = json.loads(candidate["data"])
        except (ValueError, TypeError):
            continue
        if isinstance(item_data, dict) and item_data.get("line_id") == item_id:
            item, payload = candidate, item_data
            break
    if item is None:
        # Accept a legacy DB row id only for compatibility with older clients.
        candidate = service.con.execute("SELECT * FROM quote_items WHERE id=? AND quote_id=?", (item_id, quote_id)).fetchone()
        if candidate:
            try:
                payload = json.loads(candidate["data"])
            except (ValueError, TypeError):
                payload = None
            if isinstance(payload, dict):
                item = candidate
    if item is None or not isinstance(payload, dict):
        raise business.DomainError(404, "Строка сметы не найдена")
    return quote, item, payload


def _save_metadata(service, quote, item, payload, source_id, product):
    payload.update({
        "product_source_id": source_id,
        "product_title": product.get("product_title", ""),
        "product_brand": product.get("brand", ""),
        "product_sku": product.get("sku", ""),
        "product_url": product.get("url", ""),
        "product_image_url": product.get("image_url", ""),
        "product_price_kopecks": product.get("price_kopecks"),
        "product_currency": product.get("currency", "RUB"),
        "product_unit": product.get("unit", ""),
        "product_availability": product.get("availability", "unknown"),
        "product_attributes": product.get("product_attributes", {}),
        "product_checked_at": product.get("observed_at", _now()),
    })
    service.con.execute("UPDATE quote_items SET data=? WHERE id=? AND quote_id=?", (
        business.packed(payload), item["id"], quote["id"]))
    updated = service.con.execute(
        "UPDATE quotes SET revision=revision+1,updated_at=? WHERE id=? AND workspace_id=? AND revision=?",
        (_now(), quote["id"], service.wid, quote["revision"]),
    )
    if updated.rowcount != 1:
        raise business.DomainError(409, "Смета изменилась. Обновите её перед привязкой товара")


def _observe(con, source_id, workspace_id, product):
    observed = int(product.get("observed_at") or _now())
    fp = product.get("fingerprint") or fingerprint(product)
    con.execute(
        "INSERT INTO product_price_observations(id,workspace_id,source_id,fingerprint,product_title,price_kopecks,currency,availability,image_url,source_url,observed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id,fingerprint) DO NOTHING",
        (_id(), workspace_id, source_id, fp, product.get("product_title", ""), product.get("price_kopecks"),
         product.get("currency", "RUB"), product.get("availability", "unknown"), product.get("image_url", ""),
         product.get("url", ""), observed),
    )


def route(service, method, parts, query, data):
    if not parts or parts == ["features"]:
        access = None
        try:
            access = _premium_access(service)
        except business.DomainError as err:
            if err.status != 402:
                raise
        return 200, {
            "visual_estimates": bool(access), "cloud_drives": bool(access), "product_monitor": bool(access),
            "plan": access["plan"] if access else None,
            "available_plans": ["pro_plus", "team"],
        }
    if parts[0] in ("cloud",):
        from backend import cloud_drives
        return cloud_drives.route(service, method, parts[1:], query, data)
    if parts[0] not in ("products", "product-sources", "price-history", "price-impact"):
        raise business.DomainError(404, "Не найдено")
    access = _premium_access(service)
    if parts == ["price-impact"] and method == "GET":
        service.h.throttle("price-impact:" + service.wid + ":" + service.user["id"], 30, 60)
        from backend.price_impact import calculate_price_impact
        quote_id = str(query.get("quote_id", [""])[0]).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", quote_id):
            raise business.DomainError(400, "Выберите смету для сравнения")
        # Workspace-scoped get() prevents cross-tenant quote reads.
        quote_row = service.get("quotes", quote_id)
        quote = service.quote_view(quote_row)
        rows = service.con.execute(
            "SELECT id,quote_item_id,price_kopecks,currency,unit,availability,"
            "source_status,monitored,last_checked_at,url "
            "FROM product_sources WHERE workspace_id=? AND quote_id=? "
            "AND monitored=1 AND source_status='active' ORDER BY updated_at DESC LIMIT 300",
            (service.wid, quote_id),
        ).fetchall()
        result = calculate_price_impact(quote, [dict(row) for row in rows], _now())
        return 200, result
    if parts == ["products", "preview"] and method == "POST":
        service.h.throttle("product-preview:" + service.wid + ":" + service.user["id"], 12, 60)
        result = fetch_product(data.get("url"))
        return 200, {"product": result, "price_is_observation": True, "financial_price_changed": False}
    if parts == ["product-sources"] and method == "GET":
        quote_id = str(query.get("quote_id", [""])[0])[:100]
        sql = "SELECT id,quote_id,quote_item_id,url,hostname,product_title,brand,sku,image_url,price_kopecks,currency,unit,availability,source_status,monitored,last_checked_at,next_check_at,last_error,created_at FROM product_sources WHERE workspace_id=?"
        args = [service.wid]
        if quote_id:
            sql += " AND quote_id=?"
            args.append(quote_id)
        sql += " ORDER BY updated_at DESC LIMIT 100"
        return 200, {"sources": [dict(row) for row in service.con.execute(sql, args).fetchall()]}
    if parts == ["product-sources"] and method == "POST":
        _require_quote_writer(service)
        service.h.throttle("product-source-create:" + service.wid + ":" + service.user["id"], 20, 3600)
        quote_id = str(data.get("quote_id", ""))[:100]
        item_id = str(data.get("quote_item_id", ""))[:100]
        quote, item, item_data = _quote_item(service, quote_id, item_id)
        # quote_items database row IDs are regenerated on each autosave. Persist the
        # stable line_id stored in JSON so sources survive normal quote edits.
        item_id = str(item_data.get("line_id") or "")
        if not item_id:
            raise business.DomainError(409, "У строки сметы нет стабильного идентификатора. Пересохраните черновик.")
        if type(data.get("revision")) is not int or data["revision"] != quote["revision"]:
            raise business.DomainError(409, "Смета изменилась. Обновите её перед привязкой товара.")
        product = fetch_product(data.get("url"))
        source_id, now = _id(), _now()
        service.con.execute(
            "INSERT INTO product_sources(id,workspace_id,quote_id,quote_item_id,created_by,url,normalized_url,hostname,product_title,brand,sku,image_url,price_kopecks,currency,unit,availability,product_attributes,source_status,monitored,last_fingerprint,last_checked_at,next_check_at,last_http_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',1,?,?,?,?,?,?) ON CONFLICT(workspace_id,quote_item_id,normalized_url) DO UPDATE SET url=excluded.url,product_title=excluded.product_title,brand=excluded.brand,sku=excluded.sku,image_url=excluded.image_url,price_kopecks=excluded.price_kopecks,currency=excluded.currency,unit=excluded.unit,availability=excluded.availability,product_attributes=excluded.product_attributes,source_status='active',monitored=1,last_fingerprint=excluded.last_fingerprint,last_checked_at=excluded.last_checked_at,next_check_at=excluded.next_check_at,last_http_status=excluded.last_http_status,last_error='',updated_at=excluded.updated_at RETURNING id",
            (source_id, service.wid, quote_id, item_id, service.user["id"], product["url"], product["normalized_url"],
             product["hostname"], product["product_title"], product["brand"], product["sku"], product["image_url"],
             product["price_kopecks"], product["currency"], product["unit"], product["availability"],
             business.packed(product["product_attributes"]), product["fingerprint"], now, now + 7 * 86400,
             product["http_status"], now, now),
        )
        saved = service.con.execute("SELECT id FROM product_sources WHERE workspace_id=? AND quote_item_id=? AND normalized_url=?", (
            service.wid, item_id, product["normalized_url"])).fetchone()
        source_id = saved["id"]
        _observe(service.con, source_id, service.wid, product)
        _save_metadata(service, quote, item, item_data, source_id, product)
        service.emit("product_source", source_id, "Товар привязан к смете")
        return 201, {"source_id": source_id, "product": product, "next_check_at": now + 7 * 86400,
                     "quote_revision": int(quote["revision"]) + 1, "financial_price_changed": False}
    if len(parts) == 2 and parts[0] == "product-sources" and method == "DELETE":
        _require_quote_writer(service)
        source_id = parts[1]
        row = service.con.execute("SELECT id FROM product_sources WHERE id=? AND workspace_id=?", (source_id, service.wid)).fetchone()
        if not row:
            raise business.DomainError(404, "Источник не найден")
        service.con.execute("UPDATE product_sources SET monitored=0,source_status='disabled',updated_at=? WHERE id=? AND workspace_id=?", (_now(), source_id, service.wid))
        service.emit("product_source", source_id, "Мониторинг цены остановлен")
        return 200, {"ok": True}
    if len(parts) == 2 and parts[0] == "price-history" and method == "GET":
        source_id = parts[1]
        row = service.con.execute("SELECT id FROM product_sources WHERE id=? AND workspace_id=?", (source_id, service.wid)).fetchone()
        if not row:
            raise business.DomainError(404, "Источник не найден")
        entries = service.con.execute(
            "SELECT product_title,price_kopecks,currency,availability,observed_at,source_url FROM product_price_observations WHERE source_id=? AND workspace_id=? ORDER BY observed_at DESC LIMIT 100",
            (source_id, service.wid)).fetchall()
        return 200, {"history": [dict(item) for item in entries]}
    raise business.DomainError(404, "Не найдено")


def authenticate_cron(handler):
    from backend.app import ApiError
    secret = (os.getenv("CRON_SECRET") or "").strip()
    authorization = handler.headers.get("Authorization", "")
    expected = "Bearer " + secret
    import hmac
    if len(secret) < 32 or not hmac.compare_digest(authorization, expected):
        raise ApiError(401, "Нет доступа")


def run_monitor_batch(con, limit=10):
    """Run bounded due price checks. Failures are recorded; no bad data is treated as a price."""
    due = []
    with business.transaction(con, lock_scopes=("product-monitor-queue",)):
        sql = ("SELECT * FROM product_sources WHERE monitored=1 AND source_status='active' "
               "AND next_check_at<=? AND lease_until<=? ORDER BY next_check_at,id LIMIT ?")
        if getattr(con, "is_postgres", False):
            sql += " FOR UPDATE SKIP LOCKED"
        rows = con.execute(sql, (_now(), _now(), max(1, min(int(limit), 50)))).fetchall()
        for row in rows:
            lease = _id()
            con.execute("UPDATE product_sources SET lease_token=?,lease_until=?,updated_at=? WHERE id=?",
                        (lease, _now() + 120, _now(), row["id"]))
            due.append({**dict(row), "lease_token": lease})
    completed, failed, price_increases = 0, 0, 0
    for source in due:
        try:
            product = fetch_product(source["url"])
            previous_price = source["price_kopecks"]
            previous_fp = source["last_fingerprint"]
            now = _now()
            with business.transaction(con, lock_scopes=(f"product-source:{source['id']}", f"workspace:{source['workspace_id']}")):
                current = con.execute("SELECT * FROM product_sources WHERE id=? AND lease_token=?", (source["id"], source["lease_token"])).fetchone()
                if not current:
                    continue
                con.execute(
                    "UPDATE product_sources SET product_title=?,brand=?,sku=?,image_url=?,price_kopecks=?,currency=?,unit=?,availability=?,product_attributes=?,last_fingerprint=?,last_checked_at=?,next_check_at=?,last_http_status=?,last_error='',attempts=0,lease_token='',lease_until=0,updated_at=? WHERE id=? AND lease_token=?",
                    (product["product_title"], product["brand"], product["sku"], product["image_url"],
                     product["price_kopecks"], product["currency"], product["unit"], product["availability"],
                     business.packed(product["product_attributes"]), product["fingerprint"], now, now + 7 * 86400,
                     product["http_status"], now, source["id"], source["lease_token"]),
                )
                _observe(con, source["id"], source["workspace_id"], product)
                if (previous_price is not None and product["price_kopecks"] is not None
                        and product["currency"] == current["currency"]
                        and product["price_kopecks"] > previous_price):
                    delta = product["price_kopecks"] - previous_price
                    pct = round(delta / previous_price * 100, 2) if previous_price else None
                    note_key = hashlib.sha256(f"{source['id']}:{previous_fp}:{product['fingerprint']}".encode()).hexdigest()
                    notification_id = hashlib.sha256(("price:"+note_key).encode()).hexdigest()[:32]
                    existing = con.execute("SELECT 1 FROM notifications WHERE id=?", (notification_id,)).fetchone()
                    if not existing:
                        message = f"{product['product_title'] or 'Товар'} подорожал на {pct:.2f}%"
                        con.execute("INSERT INTO notifications(id,workspace_id,message,entity_id,created_at) VALUES(?,?,?,?,?)",
                                    (notification_id, source["workspace_id"], message[:1000], source["quote_id"], now))
                        from backend.push import enqueue
                        enqueue(con, source["workspace_id"], notification_id, "Товар из сметы подорожал",
                                f"{(product['product_title'] or 'Товар')[:100]}: цена увеличилась. Откройте Сметру, чтобы проверить актуальную стоимость.",
                                source["quote_id"])
                        price_increases += 1
            completed += 1
        except Exception as error:
            failed += 1
            now = _now()
            try:
                with business.transaction(con, lock_scopes=(f"product-source:{source['id']}",)):
                    con.execute(
                        "UPDATE product_sources SET attempts=MIN(attempts+1,12),last_error=?,last_http_status=?,next_check_at=?,lease_token='',lease_until=0,updated_at=? WHERE id=? AND lease_token=?",
                        (str(getattr(error, "message", "Ошибка проверки источника"))[:500],
                         getattr(error, "status", None), now + min(86400, 300 * (2 ** min(int(source["attempts"] or 0), 8))),
                         now, source["id"], source["lease_token"]),
                    )
            except Exception:
                pass
    return {"checked": completed, "failed": failed, "price_increases": price_increases, "claimed": len(due)}
