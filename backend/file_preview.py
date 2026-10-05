"""Authenticated office preview as plain structured data, never user HTML."""

import subprocess

from backend.business import DomainError
from backend.office_documents import VIEWABLE


def route(service, method, file_id):
    if method != "GET":
        raise DomainError(405, "Предпросмотр доступен только для чтения")
    row = service.get("files", file_id)
    if row["mime"] not in VIEWABLE:
        raise DomainError(422, "Этот просмотр предназначен для DOCX, XLSX и CSV")
    service.h.throttle("office-preview:" + service.user["id"], 20, 60)
    from backend.attachments import download
    from backend.file_processing import isolated_extract

    try:
        result = isolated_extract(download(row, service.con).data, "preview:" + row["mime"])
    except (ValueError, OSError, subprocess.TimeoutExpired):
        raise DomainError(422, "Не удалось открыть документ. Скачайте оригинал") from None
    return 200, {"file_id": row["id"], "sha256": row["sha256"], **result}
