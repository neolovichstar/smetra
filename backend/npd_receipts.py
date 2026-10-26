"""NPD receipt fulfilment: only genuine tax receipts are emailed.

YooKassa's successful payment is not a tax receipt. A human or an
AUTHORIZED NPD tax partner must register the income first and provide
the actual FNS receipt link. Never auto-create fake receipts.
"""
import os
import re
import time
import urllib.parse

URL_PATH = re.compile(r"/api/v1/receipt/([0-9]{12})/([a-zA-Z0-9_-]{6,100})/print\Z")


class NpdReceiptError(ValueError):
    pass


def timestamp():
    return int(time.time())


def verified_receipt_url(value):
    if not isinstance(value, str) or len(value) > 350:
        raise NpdReceiptError("Укажите ссылку на настоящий чек из «Мой налог»")
    try:
        url = urllib.parse.urlsplit(value)
    except ValueError:
        raise NpdReceiptError("Некорректный адрес чека") from None
    if (
        url.scheme != "https" or url.hostname != "lknpd.nalog.ru"
        or url.port not in (None, 443)
        or url.username or url.password or url.query or url.fragment
        or "\\" in value or any(ord(c) < 32 for c in value)
    ):
        raise NpdReceiptError("Разрешена только прямая ссылка на чек ФНС")
    match = URL_PATH.fullmatch(url.path)
    if not match or match[1] != os.getenv("NPD_SELLER_INN", "713304603876"):
        raise NpdReceiptError("Чек должен быть выпущен от имени исполнителя «Сметры»")
    return value


def note_payment(con, payment_id):
    """Called only on YooKassa-verified pending -> succeeded transitions."""
    terms = con.execute(
        "SELECT b.is_test FROM billing_intents b JOIN payments p ON p.id=b.payment_id "
        "WHERE p.id=? AND p.status='succeeded'", (payment_id,)
    ).fetchone()
    if not terms or terms["is_test"]:
        return False
    t = timestamp()
    return con.execute(
        "INSERT INTO npd_receipt_deliveries(payment_id,status,created_at,updated_at) "
        "VALUES(?,'awaiting_tax',?,?) ON CONFLICT(payment_id) DO NOTHING",
        (payment_id, t, t),
    ).rowcount > 0


def mark_refund(con, payment_id):
    """A refund needs a separate tax correction by the operator/provider."""
    return con.execute(
        "UPDATE npd_receipt_deliveries SET status='refunded',updated_at=? "
        "WHERE payment_id=? AND status<>'refunded'",
        (timestamp(), payment_id),
    ).rowcount


def attach_tax_receipt(con, payment_id, url):
    """Admin-only; URL validation does not independently verify fiscal content."""
    if not isinstance(payment_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", payment_id):
        raise NpdReceiptError("Некорректный идентификатор платежа")
    link = verified_receipt_url(url)
    info = con.execute(
        "SELECT p.id,p.status,b.is_test FROM payments p "
        "JOIN billing_intents b ON b.payment_id=p.id WHERE p.id=?", (payment_id,)
    ).fetchone()
    if not info or info["status"] != "succeeded" or info["is_test"]:
        raise NpdReceiptError("Нет подтверждённой боевой оплаты")
    refunded = con.execute(
        "SELECT 1 FROM refunds WHERE payment_id=? AND status='succeeded'",
        (payment_id,),
    ).fetchone()
    if refunded:
        raise NpdReceiptError("Платёж возвращён; требуется корректировка в «Мой налог»")
    row = con.execute(
        "SELECT receipt_url,status FROM npd_receipt_deliveries WHERE payment_id=?",
        (payment_id,),
    ).fetchone()
    if not row:
        raise NpdReceiptError("Не обнаружена запись фискального контроля")
    if row["receipt_url"] and row["receipt_url"] != link:
        raise NpdReceiptError("Замена зарегистрированного чека требует отдельной проверки")
    if row["status"] in ("sent", "sending", "refunded"):
        return {"payment_id": payment_id, "status": row["status"]}
    t = timestamp()
    con.execute(
        "UPDATE npd_receipt_deliveries SET receipt_url=?,status='queued',"
        "next_attempt_at=?,updated_at=?,last_error=NULL "
        "WHERE payment_id=? AND status IN ('awaiting_tax','queued','needs_review')",
        (link, t, t, payment_id),
    )
    return {"payment_id": payment_id, "status": "queued"}


def list_receipts(con, limit=75):
    limit = max(1, min(int(limit), 100))
    rows = con.execute(
        "SELECT d.payment_id,d.status,d.attempts,d.created_at,d.sent_at,"
        "d.updated_at,p.amount_kopecks,p.plan,u.email "
        "FROM npd_receipt_deliveries d JOIN payments p ON p.id=d.payment_id "
        "JOIN users u ON u.id=p.user_id "
        "ORDER BY d.created_at DESC,d.payment_id DESC LIMIT ?", (limit,)
    ).fetchall()
    return {"items": [dict(r) for r in rows]}


def dispatch(con, mail_fn, limit=8, payment_id=None):
    """Bounded delivery of tax-issued URLs; never a substitute for FNS issuance.

    A crashed send remains 'sending' for manual review instead of automatic
    blind resend, because an SMTP server might already have accepted the mail.
    """
    t = timestamp()
    cap = max(1, min(int(limit), 15))
    if payment_id:
        rows = con.execute(
            "SELECT d.payment_id,d.receipt_url,p.amount_kopecks,u.email "
            "FROM npd_receipt_deliveries d JOIN payments p ON p.id=d.payment_id "
            "JOIN users u ON u.id=p.user_id "
            "WHERE d.status='queued' AND d.payment_id=? AND d.next_attempt_at<=? "
            "AND p.status='succeeded' AND NOT EXISTS "
            "(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded') "
            "LIMIT ?", (payment_id, t, cap),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT d.payment_id,d.receipt_url,p.amount_kopecks,u.email "
            "FROM npd_receipt_deliveries d JOIN payments p ON p.id=d.payment_id "
            "JOIN users u ON u.id=p.user_id "
            "WHERE d.status='queued' AND d.next_attempt_at<=? "
            "AND p.status='succeeded' AND NOT EXISTS "
            "(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded') "
            "ORDER BY d.next_attempt_at,d.payment_id LIMIT ?", (t, cap),
        ).fetchall()
    sent = failed = 0
    for row in rows:
        claim = con.execute(
            "UPDATE npd_receipt_deliveries "
            "SET status='sending',attempts=attempts+1,updated_at=? "
            "WHERE payment_id=? AND status='queued' AND next_attempt_at<=?",
            (t, row["payment_id"], t),
        )
        if claim.rowcount != 1:
            continue
        try:
            if not row["email"] or not row["receipt_url"]:
                raise ValueError("Missing destination or genuine FNS receipt")
            message = (
                "Здравствуйте!\n\n"
                "Чек из ФНС «Мой налог» по оплате в сервисе «Сметра»:\n"
                + row["receipt_url"]
                + "\n\nСумма платежа: "
                + f"{row['amount_kopecks'] / 100:.2f} ₽"
                + "\n\nЕсли оплата вам не знакома, сообщите на support@smetra.online."
            )
            mail_fn(row["email"], "Сметра — чек из «Мой налог»", message)
        except Exception as exc:
            failed += 1
            # Error class only, never SMTP content, email, passwords or receipts.
            con.execute(
                "UPDATE npd_receipt_deliveries SET status='needs_review',"
                "last_error=?,updated_at=? WHERE payment_id=? AND status='sending'",
                (type(exc).__name__[:70], timestamp(), row["payment_id"]),
            )
        else:
            sent += 1
            con.execute(
                "UPDATE npd_receipt_deliveries "
                "SET status='sent',sent_at=?,updated_at=?,last_error=NULL "
                "WHERE payment_id=? AND status='sending'",
                (timestamp(), timestamp(), row["payment_id"]),
            )
    return {"sent": sent, "needs_review": failed}
