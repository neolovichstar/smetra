"""Platega transaction validation; never trust a browser return or a callback alone."""

import os
import re
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit


PREFIX = "platega:"
UUID_PATTERN = re.compile(r"[0-9a-fA-F-]{36}\Z")


def mode():
    """Fail closed: Platega has no implied live/test environment."""
    if (os.getenv("PLATEGA_MODE", "off").lower() == "live"
            and os.getenv("PLATEGA_MERCHANT_ID", "").strip()
            and os.getenv("PLATEGA_API_KEY", "").strip()):
        return "live"
    return "off"


def transaction_id(value):
    if not isinstance(value, str) or not UUID_PATTERN.fullmatch(value):
        raise ValueError("invalid transaction id")
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise ValueError("invalid transaction id") from None


def kopecks(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError("invalid amount")
    try:
        amount = Decimal(str(value)) * 100
    except InvalidOperation:
        raise ValueError("invalid amount") from None
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise ValueError("invalid amount")
    return int(amount)


def payment_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("invalid redirect")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port
            or parsed.hostname not in ("pay.platega.io", "app.platega.io")):
        raise ValueError("invalid redirect")
    return value


def create_request(user, intent, description, return_url):
    amount = int(intent["amount_kopecks"])
    return {
        "paymentDetails": {"amount": amount // 100 if amount % 100 == 0 else amount / 100, "currency": "RUB"},
        "description": description,
        "return": return_url,
        "failedUrl": return_url,
        "payload": intent["id"],
        "metadata": {"userId": user["id"], "user_email": user["email"]},
    }


def creation_to_legacy(result, user, intent):
    """Adapt Platega's checkout response to Smetra's persisted payment model."""
    if not isinstance(result, dict) or result.get("status") != "PENDING":
        raise ValueError("invalid checkout response")
    merchant = result.get("merchantId")
    if merchant is not None and merchant != os.environ["PLATEGA_MERCHANT_ID"]:
        raise ValueError("wrong merchant")
    payment_id = PREFIX + transaction_id(result.get("transactionId"))
    return {
        "id": payment_id,
        "test": False,
        "amount": {"value": f"{intent['amount_kopecks'] / 100:.2f}", "currency": "RUB"},
        "metadata": {"user_id": user["id"], "plan": intent["plan"], "customer_email": user["email"]},
        "confirmation": {"confirmation_url": payment_url(result.get("url") or result.get("redirect"))},
    }


def verified_to_legacy(remote, local, intent):
    """Revalidate ownership, amount and order reference from Platega's authenticated GET."""
    if not isinstance(remote, dict):
        raise ValueError("invalid status response")
    merchant = remote.get("merchantId", remote.get("mechantId"))
    if merchant is not None and merchant != os.environ["PLATEGA_MERCHANT_ID"]:
        raise ValueError("wrong merchant")
    amount = remote.get("paymentDetails")
    if (PREFIX + transaction_id(remote.get("id")) != local["provider_id"]
            or not isinstance(amount, dict)
            or amount.get("currency") != "RUB"
            or kopecks(amount.get("amount")) != int(local["amount_kopecks"])
            or remote.get("payload") != intent["id"]):
        raise ValueError("payment mismatch")
    status = remote.get("status")
    if status not in {"PENDING", "CONFIRMED", "CANCELED", "CHARGEBACKED", "DISPUTED", "PARTIALLY_REFUNDED"}:
        raise ValueError("unknown payment status")
    status_legacy = {"PENDING": "pending", "CONFIRMED": "succeeded", "CANCELED": "canceled"}.get(status)
    return {
        "id": local["provider_id"], "test": False,
        "amount": {"value": f"{local['amount_kopecks'] / 100:.2f}", "currency": "RUB"},
        "metadata": {"user_id": local["user_id"], "plan": local["plan"]},
        "status": status_legacy, "paid": status == "CONFIRMED",
    }
