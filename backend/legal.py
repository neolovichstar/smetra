"""Versioned consent and mandatory warning text for AI-generated estimates."""

TERMS_VERSION = "2026-10-19-ai-estimate-v1"

AI_ESTIMATE_DISCLAIMER = (
    'Расчет сгенерирован ИИ-ассистентом "сметра." и является предварительным '
    "черновиком. Обязательно проверьте объемы, технологию и цены перед "
    "подписанием. Сервис не несет ответственности за финансовые риски сторон."
)


def has_current_terms(user):
    """Return true only when the user explicitly accepted the current revision."""
    if user is None:
        return False
    try:
        accepted_at = user["terms_accepted_at"]
        version = user["terms_version"]
    except (KeyError, IndexError, TypeError):
        return False
    try:
        return int(accepted_at or 0) > 0 and version == TERMS_VERSION
    except (TypeError, ValueError):
        return False
