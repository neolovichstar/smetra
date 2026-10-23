"""Deterministic fingerprints and financial checks for published estimate snapshots.

Hashes identify a particular published version; they are not authentication
tokens and MUST NOT grant access to any resource.
"""
import hashlib
import json


class InvalidSnapshot(ValueError):
    """Quote totals or stored line calculations do not match the snapshot."""


def fingerprint(snapshot):
    """Stable, order-insensitive SHA-256 of one financial snapshot."""
    if not isinstance(snapshot, dict):
        raise InvalidSnapshot("Snapshot must be an object")
    canonical = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_totals(snapshot, calculate):
    """Reject mismatches before publishing, keeping the legacy data model intact.

    The independent backend calculator is injected to avoid a circular import.
    Existing non-itemized quotes have their own total, and are not recalculated
    from lines that do not exist.
    """
    if not isinstance(snapshot, dict):
        raise InvalidSnapshot("Snapshot must be an object")
    total = snapshot.get("amount_kopecks")
    if type(total) is not int or not 1 <= total <= 10_000_000_000:
        raise InvalidSnapshot("Invalid estimate total")
    items = snapshot.get("items", [])
    if snapshot.get("itemized"):
        if not isinstance(items, list) or not items:
            raise InvalidSnapshot("Itemized estimate has no lines")
        rows, expected_total, expected_internal = calculate(items)
        if expected_total != total:
            raise InvalidSnapshot("Total differs from the sum of estimate lines")
        saved_internal = snapshot.get("internal_cost")
        if type(saved_internal) is not int or saved_internal != expected_internal:
            raise InvalidSnapshot("Internal cost differs from the sum of lines")
        for stored, derived in zip(items, rows):
            for field in ("subtotal", "tax_amount", "internal_cost"):
                if field in stored and (
                    type(stored[field]) is not int or stored[field] != derived[field]
                ):
                    raise InvalidSnapshot("Stored line total differs from calculation")
    elif items:
        raise InvalidSnapshot("Non-itemized estimate unexpectedly contains lines")
    return fingerprint(snapshot)
