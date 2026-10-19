"""Versioned legal acceptance and fixed AI-estimate review notice."""
import time

TERMS_VERSION = "2026-10-19"
DISCLAIMER_VERSION = "2026-10-19"
AI_ESTIMATE_DISCLAIMER = (
    'Расчет сгенерирован ИИ-ассистентом "сметра." и является предварительным '
    "черновиком. Обязательно проверьте объемы, технологию и цены перед "
    "подписанием. Сервис не несет ответственности за финансовые риски сторон."
)
CONSENT_ERROR = (
    "Для работы со сметами примите Пользовательское соглашение и "
    "Политику отказа от ответственности (As Is)."
)


def has_valid_consent(data):
    return (
        isinstance(data, dict)
        and data.get("terms_accepted") is True
        and data.get("disclaimer_accepted") is True
        and data.get("terms_version") == TERMS_VERSION
        and data.get("disclaimer_version") == DISCLAIMER_VERSION
    )


def record_acceptance(con, user_id, source="web", accepted_at=None):
    if source not in ("registration", "web", "android", "api"):
        source = "api"
    con.execute(
        "INSERT INTO legal_acceptances"
        "(user_id,terms_version,disclaimer_version,accepted_at,source) "
        "VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
        "terms_version=excluded.terms_version,disclaimer_version=excluded.disclaimer_version,"
        "accepted_at=excluded.accepted_at,source=excluded.source",
        (user_id, TERMS_VERSION, DISCLAIMER_VERSION,
         int(accepted_at if accepted_at is not None else time.time()), source),
    )


def acceptance_status(con, user_id):
    row = con.execute(
        "SELECT terms_version,disclaimer_version,accepted_at,source "
        "FROM legal_acceptances WHERE user_id=?", (user_id,)
    ).fetchone()
    accepted = bool(
        row and row["terms_version"] == TERMS_VERSION
        and row["disclaimer_version"] == DISCLAIMER_VERSION
    )
    return {
        "accepted": accepted,
        "terms_version": TERMS_VERSION,
        "disclaimer_version": DISCLAIMER_VERSION,
        "accepted_at": row["accepted_at"] if accepted else None,
    }


def has_current_acceptance(con, user_id):
    return acceptance_status(con, user_id)["accepted"]
