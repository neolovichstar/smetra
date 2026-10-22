"""Guarded, idempotent scheduled renewals for YooKassa saved payment methods."""
import hashlib
import hmac
import os

try:
    from backend import business
except ModuleNotFoundError:
    import business


PLAN_BY_PRODUCT = {
    "pro_solo_month": ("pro_month", 31),
    "pro_solo_year": ("pro_year", 366),
    "smart_supplier_month": ("smart_supplier_month", 31),
    "pro_team_month": ("pro_team_month", 31),
}


def _now():
    try:
        from backend.app import now
    except ModuleNotFoundError:
        from app import now
    return now()


def _uid():
    try:
        from backend.app import uid
    except ModuleNotFoundError:
        from app import uid
    return uid()


def _api_error(status, message):
    try:
        from backend.app import ApiError
    except ModuleNotFoundError:
        from app import ApiError
    return ApiError(status, message)


def _set_past_due(con, subscription_id, error_code, delay=86400):
    t = _now()
    con.execute(
        "UPDATE billing_subscriptions SET status='past_due',next_charge_at=?,updated_at=? "
        "WHERE id=? AND auto_renew=TRUE AND cancel_at_period_end=FALSE",
        (t + delay, t, subscription_id),
    )
    return t


def _workspace_for_subscription(con, sub):
    product = sub["product_code"]
    if product == "pro_team_month":
        return sub["workspace_id"]
    if product == "smart_supplier_month":
        row = con.execute(
            "SELECT workspace_id FROM billing_intents WHERE subscription_id=? AND workspace_id IS NOT NULL "
            "ORDER BY created_at DESC,id DESC LIMIT 1",
            (sub["id"],),
        ).fetchone()
        return row["workspace_id"] if row else None
    return None


def _due_subscriptions(con, t):
    return con.execute(
        "SELECT * FROM billing_subscriptions "
        "WHERE provider='yookassa' AND auto_renew=TRUE "
        "AND status IN ('active','past_due') AND cancel_at_period_end=FALSE "
        "AND next_charge_at IS NOT NULL AND next_charge_at<=? "
        "AND provider_payment_method_id IS NOT NULL "
        "AND renewal_consent_at IS NOT NULL AND renewal_consent_version IS NOT NULL "
        "ORDER BY next_charge_at,id LIMIT 25",
        (t,),
    ).fetchall()


def _prepare_attempt(con, candidate):
    t = _now()
    sub_id = candidate["id"]
    with business.transaction_lock_scope(con, (f"user:{candidate['user_id']}", f"subscription:{sub_id}")):
        con.execute("BEGIN IMMEDIATE")
        try:
            sub = con.execute(
                "SELECT * FROM billing_subscriptions WHERE id=?", (sub_id,)
            ).fetchone()
            if (
                not sub
                or sub["provider"] != "yookassa"
                or not sub["auto_renew"]
                or sub["cancel_at_period_end"]
                or sub["status"] not in ("active", "past_due")
                or not sub["next_charge_at"]
                or int(sub["next_charge_at"]) > t
                or not sub["provider_payment_method_id"]
                or not sub["renewal_consent_at"]
                or not sub["renewal_consent_version"]
            ):
                con.execute("COMMIT")
                return {"action": "skip"}
            period_end = int(sub["current_period_end"])
            latest = con.execute(
                "SELECT * FROM billing_renewal_attempts WHERE subscription_id=? AND period_end=? "
                "ORDER BY attempt_no DESC LIMIT 1",
                (sub_id, period_end),
            ).fetchone()
            if latest and latest["status"] == "pending" and latest["payment_id"]:
                payment = con.execute(
                    "SELECT * FROM payments WHERE id=?", (latest["payment_id"],)
                ).fetchone()
                con.execute("COMMIT")
                return {"action": "sync", "sub": dict(sub), "attempt": dict(latest),
                        "payment": dict(payment) if payment else None}
            if latest and latest["status"] == "prepared" and not latest["provider_payment_id"]:
                attempt = latest
            elif latest and latest["status"] in ("prepared", "pending"):
                # Pending requests are resolved from provider state, not charged again.
                con.execute("COMMIT")
                return {"action": "skip"}
            else:
                attempt_no = int(latest["attempt_no"]) + 1 if latest else 1
                plan_terms = PLAN_BY_PRODUCT.get(sub["product_code"])
                if not plan_terms:
                    con.execute(
                        "UPDATE billing_subscriptions SET auto_renew=FALSE,status='canceled',next_charge_at=NULL,updated_at=? WHERE id=?",
                        (t, sub_id),
                    )
                    con.execute("COMMIT")
                    return {"action": "skip", "reason": "unsupported_product"}
                plan, duration_days = plan_terms
                workspace_id = _workspace_for_subscription(con, sub)
                if sub["product_code"] in ("pro_team_month", "smart_supplier_month") and not workspace_id:
                    con.execute(
                        "UPDATE billing_subscriptions SET auto_renew=FALSE,status='past_due',next_charge_at=NULL,updated_at=? WHERE id=?",
                        (t, sub_id),
                    )
                    con.execute("COMMIT")
                    return {"action": "skip", "reason": "missing_workspace"}
                idem = hashlib.sha256(
                    f"smetra-renewal:v1:{sub_id}:{period_end}:{attempt_no}".encode()
                ).hexdigest()
                attempt_id = _uid()
                con.execute(
                    "INSERT INTO billing_renewal_attempts(id,subscription_id,period_end,attempt_no,idempotency_key,status,started_at) "
                    "VALUES(?,?,?,?,?,'prepared',?)",
                    (attempt_id, sub_id, period_end, attempt_no, idem, t),
                )
                request_key = "renewal_" + idem
                intent_id = _uid()
                con.execute(
                    "INSERT INTO billing_intents(id,user_id,request_key,plan,amount_kopecks,duration_days,variant,source,is_test,payment_id,created_at,bonus_ai_messages,workspace_id,auto_renew_requested,renewal_consent_at,renewal_consent_version,subscription_id) "
                    "VALUES(?,?,?,?,?,?,?,'other',0,NULL,?,0,?,0,NULL,NULL,?)",
                    (intent_id, sub["user_id"], request_key, plan, int(sub["amount_kopecks"]),
                     duration_days, "recurring", t, workspace_id, sub_id),
                )
                attempt = con.execute(
                    "SELECT * FROM billing_renewal_attempts WHERE id=?", (attempt_id,)
                ).fetchone()
            intent = con.execute(
                "SELECT * FROM billing_intents WHERE subscription_id=? AND request_key=?",
                (sub_id, "renewal_" + attempt["idempotency_key"]),
            ).fetchone()
            con.execute("COMMIT")
            return {"action": "charge", "sub": dict(sub), "attempt": dict(attempt),
                    "intent": dict(intent), "workspace_id": _workspace_for_subscription(con, sub)}
        except Exception:
            con.execute("ROLLBACK")
            raise


def _persist_provider_payment(handler, con, sub, attempt, intent, remote):
    t = _now()
    payment_id = None
    with business.transaction_lock_scope(con, (f"user:{sub['user_id']}", f"subscription:{sub['id']}")):
        con.execute("BEGIN IMMEDIATE")
        try:
            existing = con.execute(
                "SELECT * FROM payments WHERE user_id=? AND idempotency_key=?",
                (sub["user_id"], attempt["idempotency_key"]),
            ).fetchone()
            if existing:
                payment = existing
            else:
                payment_id = _uid()
                confirm = remote.get("confirmation")
                confirmation_url = confirm.get("confirmation_url", "") if isinstance(confirm, dict) else ""
                con.execute(
                    "INSERT INTO payments(id,user_id,provider_id,plan,amount_kopecks,status,idempotency_key,confirmation_url,created_at,activated_at) "
                    "VALUES(?,?,?,?,?,'pending',?,?,?,NULL)",
                    (payment_id, sub["user_id"], remote["id"], intent["plan"],
                     int(intent["amount_kopecks"]), attempt["idempotency_key"], confirmation_url, t),
                )
                payment = con.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
            payment_id = payment["id"]
            con.execute(
                "UPDATE billing_intents SET payment_id=? WHERE id=? AND (payment_id IS NULL OR payment_id=?)",
                (payment_id, intent["id"], payment_id),
            )
            con.execute(
                "UPDATE billing_renewal_attempts SET payment_id=?,provider_payment_id=?,status='pending' "
                "WHERE id=?",
                (payment_id, remote["id"], attempt["id"]),
            )
            con.execute("COMMIT")
            return dict(payment)
        except Exception:
            con.execute("ROLLBACK")
            raise


def _mark_attempt(con, attempt_id, status, error_code=None, delay=None, subscription_id=None):
    t = _now()
    with business.transaction_lock_scope(con, (f"subscription:{subscription_id}",) if subscription_id else ()):
        con.execute("BEGIN IMMEDIATE")
        try:
            con.execute(
                "UPDATE billing_renewal_attempts SET status=?,finished_at=?,last_error_code=? WHERE id=?",
                (status, t if status not in ("prepared", "pending") else None,
                 (error_code or "")[:80] or None, attempt_id),
            )
            if delay is not None and subscription_id:
                con.execute(
                    "UPDATE billing_subscriptions SET status='past_due',next_charge_at=?,updated_at=? "
                    "WHERE id=? AND auto_renew=TRUE AND cancel_at_period_end=FALSE",
                    (t + delay, t, subscription_id),
                )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise


def _resolve_existing(handler, con, item):
    sub, attempt, payment = item["sub"], item["attempt"], item["payment"]
    if not payment or not attempt.get("provider_payment_id"):
        return "skipped"
    remote = handler.provider_payment(attempt["provider_payment_id"])
    handler.verify_yookassa_shop(remote)
    handler.apply_payment(con, payment, remote)
    if remote.get("status") == "succeeded" and remote.get("paid") is True:
        _mark_attempt(con, attempt["id"], "succeeded", subscription_id=sub["id"])
        return "succeeded"
    if remote.get("status") == "canceled":
        _mark_attempt(con, attempt["id"], "failed", "payment_canceled", 86400, sub["id"])
        return "failed"
    _mark_attempt(con, attempt["id"], "needs_action", "payment_pending", 86400, sub["id"])
    return "pending"


def _charge(handler, con, item):
    sub, attempt, intent = item["sub"], item["attempt"], item["intent"]
    workspace_id = item["workspace_id"]
    plan = intent["plan"]
    # Cancellation may race with preparation; re-check immediately before contacting
    # the payment provider so a stale scheduled item cannot initiate a new charge.
    current = con.execute(
        "SELECT auto_renew,cancel_at_period_end,status,next_charge_at,current_period_end,provider_payment_method_id "
        "FROM billing_subscriptions WHERE id=?",
        (sub["id"],),
    ).fetchone()
    if (
        not current
        or not current["auto_renew"]
        or current["cancel_at_period_end"]
        or current["status"] not in ("active", "past_due")
        or not current["next_charge_at"]
        or int(current["next_charge_at"]) > _now()
        or int(current["current_period_end"]) != int(attempt["period_end"])
        or current["provider_payment_method_id"] != sub["provider_payment_method_id"]
    ):
        _mark_attempt(con, attempt["id"], "canceled", "renewal_disabled", subscription_id=sub["id"])
        return "skipped"
    metadata = {"user_id": sub["user_id"], "plan": plan}
    if workspace_id:
        metadata["workspace_id"] = workspace_id
    request = {
        "amount": {"value": f"{int(sub['amount_kopecks']) / 100:.2f}", "currency": "RUB"},
        "capture": True,
        "payment_method_id": sub["provider_payment_method_id"],
        "description": "Продление подписки «Сметра»",
        "metadata": metadata,
    }
    try:
        remote = handler.provider_call("/payments", "POST", request, attempt["idempotency_key"])
    except Exception as error:
        # Network timeouts are ambiguous: keep the prepared attempt and reuse its exact
        # idempotency key on the next run, preventing a duplicate off-session charge.
        try:
            from backend.app import ApiError
        except ModuleNotFoundError:
            from app import ApiError
        if isinstance(error, ApiError) and error.status < 500:
            _mark_attempt(con, attempt["id"], "failed", "provider_rejected", 86400, sub["id"])
            return "failed"
        _mark_attempt(con, attempt["id"], "prepared", "provider_unavailable")
        return "retry"

    if (
        not isinstance(remote, dict)
        or remote.get("id") is None
        or remote.get("test") is not False
        or remote.get("amount", {}).get("currency") != "RUB"
        or remote.get("amount", {}).get("value") != f"{int(sub['amount_kopecks']) / 100:.2f}"
        or remote.get("metadata") != metadata
    ):
        _mark_attempt(con, attempt["id"], "failed", "provider_response_mismatch", 86400, sub["id"])
        return "failed"

    payment = _persist_provider_payment(handler, con, sub, attempt, intent, remote)
    if remote.get("status") not in ("succeeded", "pending", "canceled"):
        _mark_attempt(con, attempt["id"], "failed", "unknown_provider_status", 86400, sub["id"])
        return "failed"

    handler.apply_payment(con, payment, remote)
    if remote.get("status") == "succeeded" and remote.get("paid") is True:
        _mark_attempt(con, attempt["id"], "succeeded", subscription_id=sub["id"])
        return "succeeded"
    if remote.get("status") == "canceled":
        _mark_attempt(con, attempt["id"], "failed", "payment_canceled", 86400, sub["id"])
        return "failed"
    _mark_attempt(con, attempt["id"], "needs_action", "payment_pending", 86400, sub["id"])
    return "pending"


def run(handler, con):
    """Called only by the secret-protected Vercel cron route; is disabled by default."""
    try:
        from backend.app import ApiError, yookassa_mode
    except ModuleNotFoundError:
        from app import ApiError, yookassa_mode

    secret = os.getenv("CRON_SECRET", "").strip()
    authorization = handler.headers.get("Authorization", "")
    if len(secret) < 32:
        raise ApiError(503, "Секрет планировщика не настроен")
    if not hmac.compare_digest(authorization, "Bearer " + secret):
        raise ApiError(401, "Нет доступа")
    if os.getenv("YOOKASSA_RECURRING_ENABLED", "").strip().lower() not in ("1", "true", "yes"):
        return {"enabled": False, "processed": 0, "message": "Автопродление выключено"}
    if yookassa_mode() != "live":
        return {"enabled": False, "processed": 0, "message": "Боевой магазин недоступен"}

    t = _now()
    candidates = _due_subscriptions(con, t)
    result = {"enabled": True, "candidates": len(candidates), "succeeded": 0,
              "failed": 0, "pending": 0, "retry": 0, "skipped": 0}
    for candidate in candidates:
        try:
            item = _prepare_attempt(con, candidate)
            action = item.get("action")
            if action == "sync":
                outcome = _resolve_existing(handler, con, item)
            elif action == "charge":
                outcome = _charge(handler, con, item)
            else:
                outcome = "skipped"
            result[outcome] = result.get(outcome, 0) + 1
        except ApiError as error:
            # Keep the rest of the batch running; never log payment credentials or PII.
            result["failed"] += 1
            print({"billing_renewal_error": error.status, "code": "provider_or_db_error"})
        except Exception:
            result["failed"] += 1
            print({"billing_renewal_error": "unexpected", "code": "internal_error"})
    return result
