"""RuStore push registration, privacy-safe outbox and retrying delivery worker."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import hmac
import re
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
MAX_DELIVERIES_PER_BATCH = 100
MAX_DELIVERY_ATTEMPTS = 5


def is_configured():
    return bool(
        os.getenv("RUSTORE_PUSH_PROJECT_ID", "").strip()
        and os.getenv("RUSTORE_PUSH_SERVICE_TOKEN", "").strip()
    )


def _now():
    return int(time.time())


def _safe_text(value, limit, fallback=""):
    text = str(value or "").replace("\x00", " ").strip()
    return text[:limit] or fallback


def enqueue(con, workspace_id, notification_id, title, body, entity_id):
    """Queue a minimal push only when the provider is configured."""
    if not is_configured():
        return
    now = _now()
    con.execute(
        "INSERT INTO push_outbox(id,workspace_id,notification_id,title,body,entity_id,created_at,next_attempt_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            str(uuid.uuid4()),
            workspace_id,
            notification_id,
            _safe_text(title, MAX_TITLE, "Сметра"),
            _safe_text(body, MAX_BODY, "Есть новое событие в Сметре."),
            _safe_text(entity_id, 100),
            now,
            now,
        ),
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
        if (
            not isinstance(token, str)
            or not 16 <= len(token) <= 4096
            or any(ord(ch) < 33 or ord(ch) == 127 for ch in token)
            or not _valid_installation_id(installation_id)
        ):
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
            (
                str(uuid.uuid4()),
                installation_id,
                user_id,
                session_hash,
                token,
                "android",
                now,
                now,
                now,
            ),
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
    """Verify the same short-lived signed invocation pattern used by the existing worker."""
    from backend.app import ApiError

    secret = (os.getenv("ASSISTANT_WORKER_SECRET") or os.getenv("PUSH_WORKER_SECRET") or "").strip()
    raw = handler.headers.get("Authorization", "")
    match = re.fullmatch(r"Bearer v1\.(\d{10})\.([a-f0-9]{32})\.([a-f0-9]{64})", raw)
    if len(secret) < 32 or not match:
        raise ApiError(401, "Нет доступа")
    moment, nonce, signature = match.groups()
    expected = hmac.new(
        secret.encode(),
        ("smetra-push-worker:v1:" + moment + ":" + nonce).encode(),
        hashlib.sha256,
    ).hexdigest()
    try:
        fresh = -30 <= _now() - int(moment) <= 120
    except ValueError:
        fresh = False
    if not fresh or not hmac.compare_digest(signature, expected):
        raise ApiError(401, "Нет доступа")
    handler.throttle("push:worker-nonce:" + nonce, 1, 180)


def _is_invalid_token_error(status, response_body):
    """Interpret documented RuStore token errors without deleting devices for project failures."""
    if status == 410:
        return True
    if status not in (400, 404):
        return False
    raw = response_body.decode("utf-8", errors="replace") if isinstance(response_body, bytes) else str(response_body or "")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        payload = {}
    error = payload.get("error", payload) if isinstance(payload, dict) else {}
    if not isinstance(error, dict):
        error = {}
    code = str(error.get("status", "")).upper()
    message = str(error.get("message", "")).strip().lower()

    if status == 404 and code == "NOT_FOUND":
        # RuStore's documented expired-token response is exactly this generic message.
        return message == "requested entity was not found." or any(
            token_term in message for token_term in ("registration token", "push token", "device token")
        )
    if status == 400 and code == "INVALID_ARGUMENT":
        mentions_registration = any(
            token_term in message for token_term in ("registration token", "push token", "device token")
        )
        invalid_token = any(
            term in message for term in ("invalid", "not a valid", "not registered", "unregistered", "expired")
        )
        return mentions_registration and invalid_token
    return False


def _read_error_body(error, limit=16_384):
    try:
        return error.read(limit)
    except (OSError, ValueError):
        return b""


def _send(token, event):
    """Return (success, HTTP status, token_is_invalid), never the provider response body."""
    project_id = os.getenv("RUSTORE_PUSH_PROJECT_ID", "").strip()
    service_token = os.getenv("RUSTORE_PUSH_SERVICE_TOKEN", "").strip()
    if not project_id or not service_token:
        return False, 503, False
    title = _safe_text(event["title"], MAX_TITLE, "Сметра")
    body = _safe_text(event["body"], MAX_BODY, "Есть новое событие в Сметре.")
    payload = {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": {
                "type": "workspace_notification",
                "notification_id": str(event["notification_id"]),
                "entity_id": str(event["entity_id"] or ""),
            },
            "android": {
                "notification": {
                    "title": title,
                    "body": body,
                    "click_action": "ru.smetra.mobile.OPEN_NOTIFICATIONS",
                    "click_action_type": 0,
                }
            },
        }
    }
    request = urllib.request.Request(
        RUSTORE_SEND_URL.format(project_id=urllib.parse.quote(project_id, safe="-_.")),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + service_token,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return 200 <= response.status < 300, response.status, False
    except urllib.error.HTTPError as error:
        body = _read_error_body(error)
        return False, int(error.code), _is_invalid_token_error(error.code, body)
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, 0, False


def _complete_event_if_finished(con, event_id, now):
    pending = con.execute(
        "SELECT COUNT(*) AS count FROM push_deliveries WHERE outbox_id=? AND completed_at IS NULL",
        (event_id,),
    ).fetchone()["count"]
    if pending:
        next_attempt = con.execute(
            "SELECT MIN(CASE WHEN next_attempt_at>lease_until THEN next_attempt_at ELSE lease_until END) AS next_attempt_at FROM push_deliveries "
            "WHERE outbox_id=? AND completed_at IS NULL",
            (event_id,),
        ).fetchone()["next_attempt_at"]
        con.execute(
            "UPDATE push_outbox SET next_attempt_at=?,lease_until=0,last_error='' WHERE id=? AND sent_at IS NULL",
            (int(next_attempt or now), event_id),
        )
        return False

    failed = con.execute(
        "SELECT COUNT(*) AS count FROM push_deliveries "
        "WHERE outbox_id=? AND completed_at IS NOT NULL AND sent_at IS NULL",
        (event_id,),
    ).fetchone()["count"]
    error = "" if not failed else "delivery_failed_recipients_" + str(failed)
    con.execute(
        "UPDATE push_outbox SET sent_at=?,lease_until=0,last_error=? WHERE id=? AND sent_at IS NULL",
        (now, error, event_id),
    )
    return True


def run_batch(con, limit=3):
    """Deliver bounded recipient batches without resending successful devices."""
    if not is_configured():
        now = _now()
        # Avoid waking the worker every minute while credentials are intentionally absent.
        con.execute(
            "UPDATE push_outbox SET next_attempt_at=?,lease_until=0,last_error='provider_not_configured' "
            "WHERE sent_at IS NULL AND next_attempt_at<=? AND lease_until<?",
            (now + 3600, now, now),
        )
        return {"ok": True, "configured": False, "processed": 0, "delivered": 0}
    try:
        limit = max(1, min(int(limit), 3))
    except (TypeError, ValueError):
        limit = 3

    now = _now()
    # A logout or an expired session must stop future notifications for that installation.
    con.execute(
        "DELETE FROM push_devices WHERE NOT EXISTS "
        "(SELECT 1 FROM sessions s WHERE s.user_id=push_devices.user_id "
        "AND s.token_hash=push_devices.session_token_hash AND s.expires_at>?)",
        (now,),
    )

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

        # A delivery snapshot is not a permanent permission grant. Revoke old
        # retries before the early no-recipient return as well as before sending.
        con.execute(
            "UPDATE push_deliveries SET completed_at=?,lease_until=0,last_error='recipient_access_revoked' "
            "WHERE outbox_id=? AND completed_at IS NULL AND NOT EXISTS ("
            "SELECT 1 FROM push_devices d "
            "JOIN workspace_members m ON m.user_id=d.user_id AND m.workspace_id=push_deliveries.workspace_id "
            "JOIN sessions s ON s.user_id=d.user_id AND s.token_hash=d.session_token_hash "
            "WHERE d.id=push_deliveries.device_id AND s.expires_at>?)",
            (now, event["id"], now),
        )

        devices = con.execute(
            "SELECT DISTINCT d.id,d.token FROM push_devices d "
            "JOIN workspace_members m ON m.user_id=d.user_id "
            "JOIN sessions s ON s.user_id=d.user_id AND s.token_hash=d.session_token_hash "
            "WHERE m.workspace_id=? AND s.expires_at>? ORDER BY d.id",
            (event["workspace_id"], now),
        ).fetchall()
        if not devices:
            _complete_event_if_finished(con, event["id"], now)
            continue

        # Snapshot each eligible recipient once. A retry only works on incomplete deliveries.
        for device in devices:
            con.execute(
                "INSERT OR IGNORE INTO push_deliveries"
                "(id,workspace_id,outbox_id,device_id,next_attempt_at,created_at) VALUES(?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    event["workspace_id"],
                    event["id"],
                    device["id"],
                    now,
                    now,
                ),
            )

        candidates = con.execute(
            "SELECT p.id AS delivery_id,p.device_id,p.attempts,d.token "
            "FROM push_deliveries p JOIN push_devices d ON d.id=p.device_id "
            "JOIN workspace_members m ON m.user_id=d.user_id AND m.workspace_id=p.workspace_id "
            "JOIN sessions s ON s.user_id=d.user_id AND s.token_hash=d.session_token_hash "
            "WHERE p.outbox_id=? AND p.completed_at IS NULL "
            "AND p.workspace_id=? AND s.expires_at>? "
            "AND p.next_attempt_at<=? AND p.lease_until<? "
            "ORDER BY p.created_at,p.id LIMIT ?",
            (event["id"], event["workspace_id"], now, now, now, MAX_DELIVERIES_PER_BATCH),
        ).fetchall()

        work = []
        for candidate in candidates:
            claimed = con.execute(
                "UPDATE push_deliveries SET attempts=attempts+1,lease_until=? "
                "WHERE id=? AND completed_at IS NULL AND lease_until<? RETURNING attempts",
                (now + 45, candidate["delivery_id"], now),
            ).fetchone()
            if claimed:
                item = dict(candidate)
                item["attempts"] = claimed["attempts"]
                work.append(item)

        if work:
            with ThreadPoolExecutor(max_workers=min(20, len(work))) as pool:
                futures = {
                    pool.submit(_send, item["token"], event): item
                    for item in work
                }
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        ok, status, invalid_token = future.result()
                    except Exception:
                        ok, status, invalid_token = False, 0, False

                    if ok:
                        delivered += 1
                        con.execute(
                            "UPDATE push_deliveries SET sent_at=?,completed_at=?,lease_until=0,last_error='' "
                            "WHERE id=? AND completed_at IS NULL",
                            (now, now, item["delivery_id"]),
                        )
                    elif invalid_token:
                        con.execute("DELETE FROM push_devices WHERE id=?", (item["device_id"],))
                    elif int(item["attempts"]) < MAX_DELIVERY_ATTEMPTS:
                        delay = min(60 * (2 ** max(0, int(item["attempts"]) - 1)), 1800)
                        reason = "provider_unavailable" if status == 0 else "provider_http_" + str(status)
                        con.execute(
                            "UPDATE push_deliveries SET next_attempt_at=?,lease_until=0,last_error=? "
                            "WHERE id=? AND completed_at IS NULL",
                            (now + delay, reason, item["delivery_id"]),
                        )
                    else:
                        con.execute(
                            "UPDATE push_deliveries SET completed_at=?,lease_until=0,last_error='delivery_failed_after_retries' "
                            "WHERE id=? AND completed_at IS NULL",
                            (now, item["delivery_id"]),
                        )

        _complete_event_if_finished(con, event["id"], now)

    return {"ok": True, "configured": True, "processed": processed, "delivered": delivered}
