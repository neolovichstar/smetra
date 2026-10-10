"""Read-only comparison of immutable quote snapshots and a current draft."""

from collections import defaultdict, deque
from decimal import Decimal


ITEM_FIELDS = (
    "name", "description", "category", "quantity", "unit", "unit_price",
    "cost_price", "coefficient", "markup", "discount", "tax", "optional", "included",
)
QUOTE_FIELDS = ("title", "client", "description", "terms", "due_date", "expires_at", "custom_fields")
DECIMALS = {"quantity", "coefficient", "markup", "discount", "tax"}
DEFAULTS = {"quantity": "1", "coefficient": "1", "markup": "0", "discount": "0", "tax": "0",
            "unit_price": 0, "cost_price": 0, "optional": False, "included": True}


def value(row, field):
    result = row.get(field, DEFAULTS.get(field, ""))
    return Decimal(str(result)) if field in DECIMALS else result


def signature(row):
    return tuple(value(row, field) for field in ITEM_FIELDS)


def compare(before, after):
    old, new = before.get("items", []), after.get("items", [])
    matches, used = {}, set()
    ids = {row["line_id"]: index for index, row in enumerate(old) if row.get("line_id")}
    for index, row in enumerate(new):
        previous = ids.get(row.get("line_id"))
        if previous is not None and previous not in used:
            matches[index] = previous
            used.add(previous)
    # Old snapshots have no stable IDs. Match identical rows first, then named
    # rows in occurrence order. Never guess that two renamed legacy rows match.
    for key in (signature, lambda row: (row.get("name", ""), row.get("category", ""), row.get("unit", ""))):
        candidates = defaultdict(deque)
        for index, row in enumerate(old):
            if index not in used:
                candidates[key(row)].append(index)
        for index, row in enumerate(new):
            if index in matches:
                continue
            queue = candidates[key(row)]
            previous = next((candidate for candidate in queue if not row.get("line_id") or not old[candidate].get("line_id")), None)
            if previous is not None:
                queue.remove(previous)
                matches[index] = previous
                used.add(previous)
    old_order = {previous: rank for rank, previous in enumerate(sorted(used))}
    new_order = {index: rank for rank, index in enumerate(sorted(matches))}
    same_currency = before.get("currency", "RUB") == after.get("currency", "RUB")
    changes = []
    unchanged = 0
    for index, row in enumerate(new):
        previous = matches.get(index)
        original = old[previous] if previous is not None else None
        fields = [field for field in ITEM_FIELDS if original is not None and value(original, field) != value(row, field)]
        moved = previous is not None and old_order[previous] != new_order[index]
        if original is not None and not fields and not moved:
            unchanged += 1
            continue
        old_total = original.get("subtotal", 0) if original and original.get("included", True) else 0
        new_total = row.get("subtotal", 0) if row.get("included", True) else 0
        changes.append({"kind": "added" if original is None else "changed" if fields else "moved",
                        "before": original, "after": row, "fields": fields, "moved": moved,
                        "before_position": previous + 1 if previous is not None else None,
                        "after_position": index + 1, "delta_kopecks": new_total - old_total if same_currency else None})
    for index, row in enumerate(old):
        if index not in used:
            changes.append({"kind": "removed", "before": row, "after": None, "fields": [], "moved": False,
                            "before_position": index + 1, "after_position": None,
                            "delta_kopecks": -(row.get("subtotal", 0) if row.get("included", True) else 0) if same_currency else None})
    fields = [{"field": field, "before": before.get(field), "after": after.get(field)}
              for field in QUOTE_FIELDS if before.get(field) != after.get(field)]
    if not same_currency:
        fields.append({"field": "currency", "before": before.get("currency", "RUB"), "after": after.get("currency", "RUB")})
    totals = {"before": before.get("amount_kopecks", 0), "after": after.get("amount_kopecks", 0),
              "before_currency": before.get("currency", "RUB"), "after_currency": after.get("currency", "RUB"),
              "delta_kopecks": after.get("amount_kopecks", 0) - before.get("amount_kopecks", 0) if same_currency else None}
    summary = {kind: sum(row["kind"] == kind for row in changes) for kind in ("added", "removed", "changed", "moved")}
    summary["unchanged"] = unchanged
    return {"items": changes, "fields": fields, "totals": totals, "summary": summary,
            "has_changes": bool(changes or fields or totals["before"] != totals["after"])}
