"""Assistant token packs: one-time purchases that top up the token wallet.

Price per million falls with volume (graduated, like tax bands), so a larger
amount is never cheaper in total than a smaller one. Cost basis: the paid
assistant model costs about $0.75 per million mixed input/output tokens
(roughly 70 ₽ with the provider and payment fees); the cheapest band keeps a
margin above that even if every token is spent on the paid model.

The payment provider's confirmation stays the only grant authority: tokens are
credited in apply_payment, once per payment, and taken back on a full refund.
"""
import re

from backend.business import DomainError

MILLION = 1_000_000
MIN_MILLIONS, MAX_MILLIONS = 1, 50
# (upper bound in millions, kopecks per million inside the band)
BANDS = ((2, 24900), (9, 21600), (24, 18900), (MAX_MILLIONS, 16000))
PACKS = (
    {"millions": 1, "label": "Попробовать"},
    {"millions": 3, "label": "Для работы"},
    {"millions": 10, "label": "Популярный", "featured": True},
    {"millions": 25, "label": "Для команды"},
)
CODE = re.compile(r"tokens_([1-9][0-9]?)m")


def code(millions):
    return f"tokens_{millions}m"


def millions_of(plan):
    """Millions for a token purchase code, or None for any other product."""
    match = CODE.fullmatch(plan or "")
    if not match:
        return None
    value = int(match.group(1))
    return value if MIN_MILLIONS <= value <= MAX_MILLIONS else None


def price(millions):
    """Total price in kopecks for a whole number of millions."""
    if isinstance(millions, bool) or not isinstance(millions, int) or not MIN_MILLIONS <= millions <= MAX_MILLIONS:
        raise DomainError(400, f"Можно купить от {MIN_MILLIONS} до {MAX_MILLIONS} млн токенов")
    total, start = 0, 0
    for upper, rate in BANDS:
        if millions <= start:
            break
        total += (min(millions, upper) - start) * rate
        start = upper
    return total


def offer():
    """Everything the purchase screen needs; prices come only from here."""
    base = BANDS[0][1]
    return {
        "unit": "tokens",
        "min_millions": MIN_MILLIONS,
        "max_millions": MAX_MILLIONS,
        "bands": [{"up_to_millions": upper, "kopecks_per_million": rate} for upper, rate in BANDS],
        "packs": [
            {**pack, "code": code(pack["millions"]), "tokens": pack["millions"] * MILLION,
             "amount_kopecks": price(pack["millions"]),
             "saving_kopecks": base * pack["millions"] - price(pack["millions"])}
            for pack in PACKS
        ],
    }
