"""RuStore push registration, privacy-safe outbox and retrying delivery worker."""
import hmac
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

RUSTORE_SEND_URL = "https://vkpns.rustore.ru/v1/projects/{project_id}/messages:send"
MAX_TITLE = 120
MAX_BODY = 500


def is_configured():
    return bool(os.getenv("RUSTORE_PUSH_PROJECT_ID", "").strip()
                and os.getenv("RUSTORE_PUSH_SERVICE_TOKEN", "").strip())


def _now():
    return int(time.time())


def _safe_text(value, limit, fallback=""):
    text = str(value or "").replace("\x00", " ").strip()
    return (text[:limit] or fallback)


def enqueue(con, workspace_id, notification_id, title, body, entity_id):
    """Queue a minimal push only when the provider is configured."""
    if not is_configured():
        return
    now = _now()
    con.execute(
        "INSERT INTO push_outbox(id,workspace_id,notification_id,title,body,entity_id,created_at,next_attempt_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), workspace_id, notification_id,
         _safe_text(title, MAX_TITLE, "Сметра"),
         _safe_text(body, MAX_BODY, "Есть новое событие в Сметре."),
         _safe_text(entity_id, 100), now, now),
    )


def _valid_installation_id(value):
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError):
        return False


def handle(service, method, rest, data):
    """Handle an authenticated /api/push-devices request."""
    from backend.app import ApiError
    user_id, con = service.user["id"], service.con

    if method == "GET" and not rest:
        rows = con.execute(
            "SELECT installation_id,platform,created_at,updated_at,last_seen "
            "FROM push_devices WHERE user_id=? ORDER BY updated_at DESC LIMIT 20",
            (user_id,),
        ).fetchall()
        return 200, {"devices": [dict(row) for row in rows]}

    if method == "POST" and not rest:
        service.h.throttle("push-register:" + user_id, 20, 3600)
        if not isinstance(data, dict):
            raise ApiError(400, "Некорректные настройки уведомлений")
        token = data.get("token")
        installation_id = data.get("installation_id")
        session_hash = getattr(service.h, "session_token_hash", "")
        if not session_hash:
            raise ApiError(401, "Сессия не найдена. Войдите в аккаунт повторно")
        if (not isinstance(token, str) or not 16 <= len(token) <= 4096
                or any(ord(ch) < 33 or ord(ch) == 127 for ch in token)
                or not _valid_installation_id(installation_id)):
            raise ApiError(400, "Не удалось зарегистрировать устройство для уведомлений")
        now = _now()
        con.execute(
            "DELETE FROM push_devices WHERE token=? AND installation_id<>?",
            (token, installation_id),
        )
        con.execute(
            "INSERT INTO push_devices(id,installation_id,user_id,session_token_hash,token,platform,created_at,updated_at,last_seen) "
            "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(installation_id) DO UPDATE SET "
            "user_id=excluded.user_id,session_token_hash=excluded.session_token_hash,"
            "token=excluded.token,platform=excluded.platform,updated_at=excluded.updated_at,last_seen=excluded.last_seen",
            (str(uuid.uuid4()), installation_id, user_id, session_hash,
             token, "android", now, now, now),
        )
        return 200, {"ok": True}

    if method == "DELETE" and len(rest) in (0, 1):
        if rest and not _valid_installation_id(rest[0]):
            raise ApiError(404, "Устройство не найдено")
        if rest:
            con.execute(
                "DELETE FROM push_devices WHERE user_id=? AND installation_id=?",
                (user_id, rest[0]),
            )
        else:
            con.execute("DELETE FROM push_devices WHERE user_id=?", (user_id,))
        return 200, {"ok": True}

    raise ApiError(404, "Не найдено")


def authenticate_cron(handler):
    from backend.app import ApiError
    secret = (os.getenv("CRON_SECRET") or os.getenv("PUSH_WORKER_SECRET") or "").strip()
    provided = handler.headers.get("Authorization", "")
    if len(secret) < 32 or not hmac.compare_digest(provided, "Bearer " + secret):
        raise ApiError(401, "Нет доступа")


def _send(token, event):
    project_id = os.getenv("RUSTORE_PUSH_PROJECT_ID", "").strip()
    service_token = os.getenv("RUSTORE_PUSH_SERVICE_TOKEN", "").strip()
    if not project_id or not service_token:
        return False, 503
    title = _safe_text(event["title"], MAX_TITLE, "Сметра")
    body = _safe_text(event["body"], MAX_BODY, "Есть новое событие в Сметре.")
    payload = {"message": {
        "token": token,
        "notification": {"title": title, "body": body},
        "data": {"type": "workspace_notification",
                 "notification_id": str(event["notification_id"]),
                 "entity_id": str(event["entity_id"] or "")},
        "android": {"notification": {
            "title": title, "body": body,
            "click_action": "ru.smetra.mobile.OPEN_NOTIFICATIONS",
            "click_action_type": 0,
        }},
    }}
    request = urllib.request.Request(
        RUSTORE_SEND_URL.format(project_id=urllib.parse.quote(project_id, safe="-_.")),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + service_token,
                 "Content-Type": "application/json; charset=utf-8",
                 "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return 200 <= response.status < 300, response.status
    except urllib.error.HTTPError as error:
        return False, int(error.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, 0


def run_batch(con, limit=3):
    """Deliver a bounded batch; rows are leased to avoid concurrent duplicates."""
    if not is_configured():
        return {"ok": True, "configured": False, "processed": 0, "delivered": 0}
    try:
        limit = max(1, min(int(limit), 3))
    except (TypeError, ValueError):
        limit = 3
    processed = delivered = 0
    for _ in range(limit):
        now = _now()
        event = con.execute(
            "UPDATE push_outbox SET attempts=attempts+1,lease_until=?,last_error='' "
            "WHERE id=(SELECT id FROM push_outbox WHERE sent_at IS NULL "
            "AND next_attempt_at<=? AND lease_until<? ORDER BY created_at,id LIMIT 1) "
            "AND sent_at IS NULL AND lease_until<? RETURNING *",
            (now + 45, now, now, now),
        ).fetchone()
        if not event:
            break
        processed += 1
        devices = con.execute(
            "SELECT DISTINCT d.id,d.token FROM push_devices d "
            "JOIN workspace_members m ON m.user_id=d.user_id "
            "JOIN sessions s ON s.user_id=d.user_id AND s.token_hash=d.session_token_hash "
            "WHERE m.workspace_id=? AND s.expires_at>? ORDER BY d.id",
            (event["workspace_id"], now),
        ).fetchall()
        if not devices:
            con.execute(
                "UPDATE push_outbox SET sent_at=?,lease_until=0,last_error='' WHERE id=?",
                (now, event["id"]),
            )
            continue
        failures = []
        with ThreadPoolExecutor(max_workers=min(20, len(devices))) as pool:
            futures = {pool.submit(_send, device["token"], event): device for device in devices}
            for future in as_completed(futures):
                device = futures[future]
                try:
                    ok, status = future.result()
                except Exception:
                    ok, status = False, 0
                if ok:
                    delivered += 1
                elif status in (400, 404):
                    con.execute("DELETE FROM push_devices WHERE id=?", (device["id"],))
                else:
                    failures.append(status)
        if failures and int(event["attempts"]) < 5:
            delay = min(60 * (2 ** max(0, int(event["attempts"]) - 1)), 1800)
            reason = "provider_unavailable" if 0 in failures else "provider_http_" + str(failures[0])
            con.execute(
                "UPDATE push_outbox SET next_attempt_at=?,lease_until=0,last_error=? WHERE id=?",
                (now + delay, reason, event["id"]),
            )
        else:
            reason = "" if not failures else "delivery_failed_after_retries"
            con.execute(
                "UPDATE push_outbox SET sent_at=?,lease_until=0,last_error=? WHERE id=?",
                (now, reason, event["id"]),
            )
    return {"ok": True, "configured": True, "processed": processed, "delivered": delivered}
