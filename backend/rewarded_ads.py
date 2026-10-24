"""Client SDK reward claims: bounded, expiring attempts; never presented as SSV."""
import hashlib
import hmac
import os
import secrets
from backend.business import DomainError, business_date, identity, stamp, transaction
from backend import assistant


def route(service, method, data):
    unit = os.getenv("YANDEX_REWARDED_AD_UNIT_ID", "").strip()
    user_id = service.user["id"]
    today = business_date().isoformat()
    current = assistant.quota(service)
    if method == "GET":
        claimed = service.con.execute(
            "SELECT id FROM assistant_ad_reward_credits WHERE user_id=? AND reward_date=?",
            (user_id, today),
        ).fetchone()
        eligible = bool(unit and current["plan"] == "free" and current["remaining"] <= 0 and not claimed)
        return 200, {"enabled": bool(unit), "available": eligible, "claimed_today": bool(claimed),
                     "amount": 3, "ad_unit_id": unit if eligible else "",
                     "quota": assistant.public_quota(service)}
    if method != "POST":
        raise DomainError(405, "Требуется POST")
    if not unit:
        raise DomainError(503, "Рекламный блок ещё не подключён")
    if current["plan"] != "free":
        raise DomainError(403, "Реклама отключена на платном тарифе")
    with transaction(service.con, lock_scopes=(f"user:{user_id}",)):
        if data.get("operation") == "start":
            if assistant.quota(service)["remaining"] > 0:
                raise DomainError(409, "Сначала израсходуйте доступные запросы")
            if service.con.execute("SELECT id FROM assistant_ad_reward_credits WHERE user_id=? AND reward_date=?", (user_id, today)).fetchone():
                raise DomainError(409, "Бонус за сегодня уже получен")
            service.h.throttle("ad-attempt:" + user_id, 10, 3600)
            attempt_id, nonce, now = identity(), secrets.token_urlsafe(32), stamp()
            service.con.execute(
                "INSERT INTO assistant_ad_attempts(id,user_id,nonce_hash,status,created_at,expires_at) VALUES(?,?,?,'issued',?,?)",
                (attempt_id, user_id, hashlib.sha256(nonce.encode()).hexdigest(), now, now + 600),
            )
            return 200, {"attempt_id": attempt_id, "nonce": nonce, "ad_unit_id": unit, "expires_at": now + 600}
        attempt = service.con.execute("SELECT * FROM assistant_ad_attempts WHERE id=? AND user_id=?",
                                      (str(data.get("attempt_id", ""))[:80], user_id)).fetchone()
        nonce = str(data.get("nonce", ""))[:200]
        if not attempt or not hmac.compare_digest(attempt["nonce_hash"], hashlib.sha256(nonce.encode()).hexdigest()):
            raise DomainError(400, "Недействительная попытка просмотра")
        if attempt["status"] == "completed":
            return 200, {"granted": 3, "replayed": True, "quota": assistant.public_quota(service)}
        if attempt["expires_at"] <= stamp():
            raise DomainError(410, "Попытка просмотра истекла")
        # No trusted server receipt exists in this integration. SDK completion
        # plus one grant/day bounds abuse; a nonce alone does not prove a view.
        now = stamp()
        existing = service.con.execute("SELECT id FROM assistant_ad_reward_credits WHERE user_id=? AND reward_date=?", (user_id, today)).fetchone()
        if existing:
            raise DomainError(409, "Бонус за сегодня уже получен")
        service.con.execute(
            "INSERT INTO assistant_ad_reward_credits(id,user_id,attempt_id,reward_date,amount,remaining,created_at,expires_at) VALUES(?,?,?,?,3,3,?,?)",
            (identity(), user_id, attempt["id"], today, now, now + 86400),
        )
        service.con.execute("UPDATE assistant_ad_attempts SET status='completed',completed_at=? WHERE id=?", (now, attempt["id"]))
    return 200, {"granted": 3, "quota": assistant.public_quota(service)}
