"""Reviewable, reversible price changes for a construction object's quantities."""

import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from backend.business import DomainError, identity, packed, stamp
from backend.construction_math import decimal_value, priced


def _selection(data):
    ids = data.get("ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or any(
        not isinstance(value, str) or not 1 <= len(value) <= 100 for value in ids
    ) or len(set(ids)) != len(ids):
        raise DomainError(400, "Выберите от 1 до 50 разных позиций")
    percent = decimal_value(
        data.get("percent"), "Изменение цены", minimum=Decimal("-100"),
        maximum=Decimal("1000"),
    )
    if percent == 0:
        raise DomainError(400, "Укажите изменение цены, отличное от нуля")
    return sorted(ids), percent


def _rows(service, obj, ids, lock=False):
    if lock:
        for item_id in ids:
            # Works on SQLite and PostgreSQL and serializes with ordinary row edits.
            service.con.execute(
                "UPDATE construction_quantities SET updated_at=updated_at "
                "WHERE id=? AND object_id=? AND workspace_id=?",
                (item_id, obj["id"], service.wid),
            )
    rows = [service.con.execute(
        "SELECT * FROM construction_quantities WHERE id=? AND object_id=? AND workspace_id=?",
        (item_id, obj["id"], service.wid),
    ).fetchone() for item_id in ids]
    if any(row is None for row in rows):
        raise DomainError(404, "Одна из позиций объекта не найдена")
    return rows


def _fingerprint(obj, rows):
    body = packed({"quote_id": obj["quote_id"], "rows": [dict(row) for row in rows]})
    return hashlib.sha256(body.encode()).hexdigest()


def _preview(rows, percent):
    changes = []
    for row in rows:
        old = row["unit_price"]
        new = int((Decimal(old) * (1 + percent / 100)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP,
        ))
        if new > 100_000_000_000:
            raise DomainError(400, "Новая расценка слишком велика")
        before = priced(row["quantity"], old, row["price_coefficient"],
                        row["markup_percent"], row["discount_percent"])
        after = priced(row["quantity"], new, row["price_coefficient"],
                       row["markup_percent"], row["discount_percent"])
        changes.append({
            "id": row["id"], "title": row["title"], "kind": row["kind"],
            "old_unit_price": old, "new_unit_price": new,
            "old_total": before, "new_total": after,
        })
    if all(item["old_unit_price"] == item["new_unit_price"] for item in changes):
        raise DomainError(400, "Цена выбранных позиций не изменится")
    return changes


def preview(service, obj, data):
    ids, percent = _selection(data)
    rows = _rows(service, obj, ids)
    changes = _preview(rows, percent)
    return 200, {
        "changes": changes, "percent": str(percent),
        "expected_hash": _fingerprint(obj, rows),
        "old_total": sum(item["old_total"] for item in changes),
        "new_total": sum(item["new_total"] for item in changes),
    }


def apply(service, obj, data):
    ids, percent = _selection(data)
    expected = data.get("expected_hash")
    if not isinstance(expected, str) or len(expected) != 64:
        raise DomainError(400, "Сначала откройте предпросмотр изменений")
    # The object lock also serializes two concurrent bulk changes and quote creation.
    service.con.execute(
        "UPDATE construction_objects SET updated_at=updated_at WHERE id=? AND workspace_id=?",
        (obj["id"], service.wid),
    )
    obj = service.get("construction_objects", obj["id"])
    rows = _rows(service, obj, ids, lock=True)
    if _fingerprint(obj, rows) != expected:
        raise DomainError(409, "Расценки изменились. Откройте предпросмотр заново")
    changes = _preview(rows, percent)
    for item in changes:
        if item["old_unit_price"] != item["new_unit_price"]:
            service.update("construction_quantities", item["id"], {
                "unit_price": item["new_unit_price"], "updated_at": stamp(),
            })
    if obj["quote_id"]:
        service.update("construction_objects", obj["id"], {
            "quote_id": None, "updated_at": stamp(),
        })
    updated_obj = service.get("construction_objects", obj["id"])
    updated_rows = _rows(service, updated_obj, ids)
    batch_id = identity()
    service.con.execute(
        "DELETE FROM construction_price_batches WHERE workspace_id=? AND object_id=? AND created_at<?",
        (service.wid, obj["id"], stamp() - 7 * 86400),
    )
    service.insert("construction_price_batches", {
        "id": batch_id, "workspace_id": service.wid, "object_id": obj["id"],
        "created_by": service.user["id"], "created_at": stamp(), "undone_at": None,
        "before_json": packed([{"id": item["id"], "unit_price": item["old_unit_price"]}
                               for item in changes]),
        "after_hash": _fingerprint(updated_obj, updated_rows),
    })
    service.emit("construction_price_batch", batch_id, "Расценки обновлены",
                 f"{len(changes)} позиций · {percent}%")
    return 200, {"batch_id": batch_id, "changes": changes,
                 "quote_recreation_required": bool(obj["quote_id"])}


def undo(service, obj, batch_id):
    batch = service.con.execute(
        "SELECT * FROM construction_price_batches WHERE id=? AND object_id=? AND workspace_id=?",
        (batch_id, obj["id"], service.wid),
    ).fetchone()
    if not batch:
        raise DomainError(404, "Массовая правка не найдена")
    if batch["undone_at"]:
        raise DomainError(409, "Эта правка уже отменена")
    if batch["created_at"] < stamp() - 7 * 86400:
        raise DomainError(409, "Срок отмены этой правки истёк")
    before = json.loads(batch["before_json"])
    ids = sorted(item["id"] for item in before)
    service.con.execute(
        "UPDATE construction_objects SET updated_at=updated_at WHERE id=? AND workspace_id=?",
        (obj["id"], service.wid),
    )
    obj = service.get("construction_objects", obj["id"])
    rows = _rows(service, obj, ids, lock=True)
    if _fingerprint(obj, rows) != batch["after_hash"]:
        raise DomainError(409, "Позиции изменились после правки. Автоматическая отмена небезопасна")
    for item in before:
        service.update("construction_quantities", item["id"], {
            "unit_price": item["unit_price"], "updated_at": stamp(),
        })
    service.update("construction_price_batches", batch_id, {"undone_at": stamp()})
    service.emit("construction_price_batch", batch_id, "Массовая правка расценок отменена")
    return 200, {"ok": True, "restored": len(before)}
