"""Shared safety policy for AI-generated estimates and legal-consent gates."""

LEGAL_CONSENT_VERSION = "2026-10-19-ai-estimate-v1"
REGISTRATION_CONSENT_VERSION = "2026-10-19-registration-v1"

AI_ESTIMATE_DISCLAIMER = (
    'Расчет сгенерирован ИИ-ассистентом "сметра." и является предварительным черновиком. '
    "Обязательно проверьте объемы, технологию и цены перед подписанием. "
    "Сервис не несет ответственности за финансовые риски сторон."
)


def has_current_consent(connection, user_id):
    """Return true only for an explicit acceptance of the current AI-estimate terms."""
    if not isinstance(user_id, str) or not user_id:
        return False
    try:
        row = connection.execute(
            "SELECT 1 FROM legal_acceptances "
            "WHERE user_id=? AND document_version=? LIMIT 1",
            (user_id, LEGAL_CONSENT_VERSION),
        ).fetchone()
    except Exception:
        # Missing/inaccessible consent storage must fail closed, never grant access.
        return False
    return row is not None
