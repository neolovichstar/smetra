"""Replay creation requests inside the caller's serialized write transaction."""

import hashlib
import json

from backend.business import DomainError, stamp, string


def lookup(service, kind, data):
    key = service.h.headers.get("Idempotency-Key", "")
    if not key:
        return None, None
    key_hash = hashlib.sha256(string(key, "Ключ операции", 100, True).encode()).hexdigest()
    payload = {key: value for key, value in data.items() if key != "_request_key"}
    request_hash = hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    previous = service.con.execute(
        "SELECT request_hash,record_id FROM creation_requests "
        "WHERE workspace_id=? AND user_id=? AND kind=? AND key_hash=?",
        (service.wid, service.user["id"], kind, key_hash),
    ).fetchone()
    if previous and previous["request_hash"] != request_hash:
        raise DomainError(409, "Этот ключ уже использован для другого запроса")
    return (key_hash, request_hash), previous["record_id"] if previous else None


def remember(service, kind, operation, record_id):
    if operation is not None:
        service.con.execute(
            "INSERT INTO creation_requests(workspace_id,user_id,kind,key_hash,request_hash,record_id,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (service.wid, service.user["id"], kind, *operation, record_id, stamp()),
        )
