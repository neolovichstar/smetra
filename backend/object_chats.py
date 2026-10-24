"""Durable TEAM object conversations. Realtime carries invalidations, never authority."""
import base64
import hashlib
import hmac
import json
import os

from backend.business import DomainError, identity, stamp, string
from backend.entitlements import workspace_feature_access


def require_team(service):
    if not workspace_feature_access(service.con, service.wid, "object_chats", stamp())["allowed"]:
        raise DomainError(402, "Чаты объектов доступны в TEAM")


def realtime_ticket(service, thread):
    secret = os.getenv("SUPABASE_REALTIME_JWT_SECRET", "")
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    api_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    if len(secret) < 32 or not url.startswith("https://") or not api_key:
        return {"configured": False}
    session_hash = getattr(service.h, "session_token_hash", "")
    if len(session_hash) != 64:
        raise DomainError(401, "Обновите вход в аккаунт")
    def encoded(value):
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")
    moment = stamp()
    head = encoded({"alg": "HS256", "typ": "JWT"})
    claims = encoded({"role": "authenticated", "sub": service.user["id"], "aud": "authenticated",
                      "iat": moment, "exp": moment + 120, "smetra_session": session_hash})
    unsigned = head + "." + claims
    signature = base64.urlsafe_b64encode(hmac.new(secret.encode(), unsigned.encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return {"configured": True, "url": url, "api_key": api_key, "access_token": unsigned + "." + signature,
            "expires_at": moment + 120, "topic": "smetra:object:" + service.wid + ":" + thread["id"]}


def route(service, method, rest, query, data):
    require_team(service)
    if not rest:
        if method == "GET":
            return 200, {"items": [dict(r) for r in service.con.execute(
                "SELECT t.*,o.name AS object_name FROM object_chat_threads t "
                "JOIN construction_objects o ON o.id=t.object_id AND o.workspace_id=t.workspace_id "
                "WHERE t.workspace_id=? ORDER BY t.created_at DESC,t.id LIMIT 100", (service.wid,))]}
        if method == "POST":
            service.write_access(True)
            obj = service.get("construction_objects", string(data.get("object_id", ""), "Объект", 100, True))
            service.con.execute(
                "INSERT INTO object_chat_threads(id,workspace_id,object_id,title,created_by,created_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(workspace_id,object_id) DO NOTHING",
                (identity(), service.wid, obj["id"], obj["name"], service.user["id"], stamp()))
            row = service.con.execute("SELECT * FROM object_chat_threads WHERE workspace_id=? AND object_id=?",
                                      (service.wid, obj["id"])).fetchone()
            return 200, {"thread": dict(row)}
    if not rest:
        raise DomainError(405, "Действие недоступно")
    thread = service.get("object_chat_threads", rest[0])
    service.get("construction_objects", thread["object_id"])
    if rest[1:] == ["realtime"] and method == "GET":
        return 200, realtime_ticket(service, thread)
    if rest[1:] == ["messages"]:
        if method == "GET":
            raw = query.get("after", ["0"])[0]
            if not isinstance(raw, str) or not raw.isascii() or not raw.isdigit() or len(raw) > 15:
                raise DomainError(400, "Некорректный курсор сообщений")
            after = int(raw)
            if after > thread["next_sequence"]:
                raise DomainError(409, "Обновите историю чата")
            if after:
                rows = service.con.execute(
                    "SELECT * FROM object_chat_messages WHERE thread_id=? AND workspace_id=? AND sequence>? "
                    "ORDER BY sequence LIMIT 100", (thread["id"], service.wid, after)).fetchall()
            else:
                rows = list(reversed(service.con.execute(
                    "SELECT * FROM object_chat_messages WHERE thread_id=? AND workspace_id=? "
                    "ORDER BY sequence DESC LIMIT 100", (thread["id"], service.wid)).fetchall()))
            return 200, {"items": [dict(r) for r in rows], "latest_sequence": thread["next_sequence"]}
        if method == "POST":
            body = string(data.get("body", ""), "Сообщение", 4000, True)
            if "\x00" in body:
                raise DomainError(400, "Некорректное сообщение")
            key = string(service.h.headers.get("Idempotency-Key", ""), "Ключ сообщения", 100, True)
            if len(key) < 16:
                raise DomainError(400, "Ключ сообщения слишком короткий")
            previous = service.con.execute(
                "SELECT * FROM object_chat_messages WHERE thread_id=? AND sender_id=? AND client_key=?",
                (thread["id"], service.user["id"], key)).fetchone()
            if previous:
                if previous["body"] != body:
                    raise DomainError(409, "Ключ уже использован для другого сообщения")
                return 200, {"message": dict(previous), "replayed": True}
            service.h.throttle("object-chat:" + service.user["id"], 30, 60)
            sequence = service.con.execute(
                "UPDATE object_chat_threads SET next_sequence=next_sequence+1 WHERE id=? AND workspace_id=? RETURNING next_sequence",
                (thread["id"], service.wid)).fetchone()[0]
            value = dict(id=identity(), workspace_id=service.wid, thread_id=thread["id"], sequence=sequence,
                         sender_id=service.user["id"], sender_name=service.user["name"], body=body,
                         client_key=key, created_at=stamp())
            service.insert("object_chat_messages", value)
            return 201, {"message": value}
    raise DomainError(404, "Действие чата не найдено")
