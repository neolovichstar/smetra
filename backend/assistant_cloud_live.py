"""Live, workspace-scoped provider search for the assistant.

Search requires the current user's connected Google/Yandex OAuth account. It
does not require a synced folder and never saves provider file contents.
A short-lived encrypted reference, not a raw provider file ID or download URL,
is passed to the model for a subsequent read.
"""
import json
import re

from cryptography.fernet import InvalidToken

from backend.business import DomainError, string
from backend import cloud_drives

_TOKEN_LIFETIME = 1800
_MAX_PROVIDER_CALLS = 3
_MAX_RESULTS = 6
_MAX_NAME_LEN = 250
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_STOP = frozenset({
    "и", "в", "на", "с", "по", "для", "из", "о", "об", "у", "найди",
    "найти", "файл", "файлы", "документ", "документы", "мой", "мои",
    "пдф", "pdf", "гугл", "гугле", "google", "диске", "диск",
    "яндекс", "yandex", "drive", "создай", "смету", "смета",
})


def _words(query):
    words = [part.casefold() for part in _WORDS.findall(query)]
    filtered = [word for word in words if word not in _STOP and len(word) >= 2]
    # Google Drive's name contains indexes individual words. Keep the search
    # bounded, so a user prompt cannot generate huge provider-side queries.
    return filtered[:5]


def _connection_rows(service):
    # Important: do not silently search a coworker's personal Drive merely
    # because their OAuth connection belongs to the same workspace.
    return service.con.execute(
        "SELECT * FROM cloud_connections WHERE workspace_id=? AND user_id=? "
        "AND status='active' ORDER BY updated_at DESC LIMIT 4",
        (service.wid, service.user["id"]),
    ).fetchall()


def _file_match(name, terms):
    if not terms:
        return True
    lowered = name.casefold()
    return any(term in lowered for term in terms)


def _rank(name, phrase, terms):
    n = name.casefold()
    return (int(bool(phrase and phrase.casefold() in n)) * 20
            + sum(4 if term in n else 0 for term in terms)
            + int(n.endswith(".pdf")))


def _google_search(con, connection, terms):
    quoted = [term.replace("\\", "").replace("'", "\\'")[:60] for term in terms]
    conditions = [f"name contains '{word}'" for word in quoted if word]
    q = "trashed = false and mimeType != 'application/vnd.google-apps.folder'"
    if conditions:
        q += " and (" + " or ".join(conditions) + ")"
    seen_pages = set()
    token = ""
    results = []
    limited = False
    for _ in range(_MAX_PROVIDER_CALLS):
        params = {
            "q": q, "pageSize": 100,
            "fields": "nextPageToken,files(id,name,mimeType,size,trashed)",
            "orderBy": "modifiedTime desc",
        }
        if token:
            params["pageToken"] = token
        payload = cloud_drives._google_api(con, connection, "/files", params)
        entries = payload.get("files", [])
        if not isinstance(entries, list):
            raise DomainError(502, "Google Диск вернул некорректный список")
        for item in entries[:100]:
            if not isinstance(item, dict) or item.get("trashed"):
                continue
            fid = item.get("id")
            name = item.get("name")
            provider_mime = item.get("mimeType")
            if not (isinstance(fid, str) and 1 <= len(fid) <= 300 and
                    isinstance(name, str) and name and
                    isinstance(provider_mime, str)):
                continue
            native = provider_mime in (
                "application/vnd.google-apps.document",
                "application/vnd.google-apps.spreadsheet",
                "application/vnd.google-apps.presentation",
            )
            mime = "application/pdf" if native else cloud_drives._mime_for(name, provider_mime)
            try:
                size = max(1, int(item.get("size") or 0)) if native else int(item.get("size") or 0)
            except (ValueError, TypeError):
                continue
            if (mime in cloud_drives.SUPPORTED_FILES and size > 0
                    and _file_match(name, terms)):
                results.append({
                    "provider_file_id": fid, "name": name[:_MAX_NAME_LEN],
                    "mime": mime, "provider_mime": provider_mime, "size": size,
                })
        next_token = payload.get("nextPageToken") or ""
        if not isinstance(next_token, str) or len(next_token) > 2048 or next_token in seen_pages:
            raise DomainError(502, "Google Диск вернул некорректную страницу результатов")
        if not next_token:
            break
        seen_pages.add(next_token)
        token = next_token
        limited = True
    return results, limited


def _yandex_search(con, connection, terms):
    results, limited = [], False
    for index in range(_MAX_PROVIDER_CALLS):
        offset = index * 100
        payload = cloud_drives._yandex_api(con, connection, "/resources/files", {
            "limit": 100, "offset": offset, "fields": "items.name,items.path,items.mime_type,items.size,items.type,limit,offset",
        })
        entries = payload.get("items", [])
        if not isinstance(entries, list):
            raise DomainError(502, "Яндекс.Диск вернул некорректный список")
        for item in entries[:100]:
            if not isinstance(item, dict):
                continue
            path, name = item.get("path"), item.get("name")
            if (not isinstance(path, str) or not path.startswith("disk:/")
                    or len(path) > 2048 or ".." in path.split("/")
                    or not isinstance(name, str) or not name):
                continue
            provider_mime = str(item.get("mime_type") or "application/octet-stream")[:120]
            mime = cloud_drives._mime_for(name, provider_mime)
            try:
                size = int(item.get("size") or 0)
            except (ValueError, TypeError):
                continue
            if mime in cloud_drives.SUPPORTED_FILES and size > 0 and _file_match(name, terms):
                results.append({
                    "provider_file_id": path, "name": name[:_MAX_NAME_LEN],
                    "mime": mime, "provider_mime": provider_mime, "size": size,
                })
        if len(entries) < 100:
            break
        limited = True
    return results, limited


def _seal(service, connection, item):
    data = {
        "v": 1, "w": service.wid, "u": service.user["id"],
        "c": connection["id"], "p": connection["provider"],
        "f": item["provider_file_id"],
    }
    token = cloud_drives._fernet().encrypt(json.dumps(
        data, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).decode("ascii")
    return "live." + token


def search(service, query=""):
    phrase = string(query, "Поиск в облаке", 100)
    terms = _words(phrase)
    connections = _connection_rows(service)
    files, errors, limited = [], [], False
    for row in connections:
        connection = dict(row)
        if connection["provider"] not in ("google_drive", "yandex_disk"):
            continue
        try:
            cloud_drives._worker_access(service.con, connection)
            if connection["provider"] == "google_drive":
                items, capped = _google_search(service.con, connection, terms)
            else:
                items, capped = _yandex_search(service.con, connection, terms)
            limited = limited or capped or len(items) > _MAX_RESULTS
            items.sort(key=lambda item: _rank(item["name"], phrase, terms), reverse=True)
            for item in items[:_MAX_RESULTS]:
                files.append({
                    "id": _seal(service, connection, item),
                    "name": item["name"], "mime": item["mime"],
                    "size": item["size"], "provider": connection["provider"],
                    "account": connection["account_label"], "folder": "Весь диск",
                })
        except DomainError as exc:
            errors.append({"provider": connection["provider"], "error": exc.message})
    files.sort(key=lambda item: _rank(item["name"], phrase, terms), reverse=True)
    return {
        "files": files[:_MAX_RESULTS],
        "connected_accounts_searched": len(connections),
        "limited": limited or len(files) > _MAX_RESULTS,
        "errors": errors,
        "note": (
            "Поиск выполняется прямо в подключённом облаке, без привязки папки или "
            "сохранения документа в базе Сметры. id — краткоживущая зашифрованная "
            "ссылка для read_cloud_file. Если limited=true или есть errors, поиск неполный. "
            "Если files пуст, нельзя утверждать, что файла нет во всём облаке."
        ),
    }


def resolve(service, reference):
    raw = string(reference, "Облачный файл", 2400, True)
    if not raw.startswith("live.") or len(raw) > 2400:
        raise DomainError(400, "Недопустимая ссылка на облачный файл")
    try:
        data = json.loads(cloud_drives._fernet().decrypt(
            raw[5:].encode("ascii"), ttl=_TOKEN_LIFETIME,
        ).decode("utf-8"))
    except (InvalidToken, UnicodeError, ValueError, TypeError):
        raise DomainError(410, "Срок доступа к облачному файлу истёк. Найдите его снова.") from None
    if not isinstance(data, dict) or data.get("v") != 1:
        raise DomainError(400, "Некорректная облачная ссылка")
    if data.get("w") != service.wid or data.get("u") != service.user["id"]:
        raise DomainError(403, "Нет доступа к облачному файлу")
    connection = cloud_drives._connection(service, string(data.get("c"), "Подключение", 100, True))
    if connection["status"] != "active" or connection["user_id"] != service.user["id"] or connection["provider"] != data.get("p"):
        raise DomainError(403, "Доступ к облачному подключению прекращён")
    cloud_drives._worker_access(service.con, connection)
    fid = string(data.get("f"), "Файл провайдера", 2048, True)
    if connection["provider"] == "google_drive":
        if not 1 <= len(fid) <= 300 or not all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in fid):
            raise DomainError(400, "Некорректный идентификатор Google файла")
        info = cloud_drives._google_api(service.con, connection,
            "/files/" + fid,
            {"fields": "id,name,mimeType,size,trashed"})
        if info.get("trashed") or info.get("id") != fid:
            raise DomainError(404, "Файл удалён или больше недоступен")
        provider_mime = str(info.get("mimeType") or "")
        native = provider_mime in (
            "application/vnd.google-apps.document",
            "application/vnd.google-apps.spreadsheet",
            "application/vnd.google-apps.presentation",
        )
        name = str(info.get("name") or "")[:_MAX_NAME_LEN]
        mime = "application/pdf" if native else cloud_drives._mime_for(name, provider_mime)
        size = max(1, int(info.get("size") or 0)) if native else int(info.get("size") or 0)
    else:
        if not fid.startswith("disk:/") or len(fid) > 2048 or ".." in fid.split("/"):
            raise DomainError(400, "Некорректный путь Яндекс файла")
        info = cloud_drives._yandex_api(service.con, connection, "/resources", {
            "path": fid, "fields": "name,path,size,mime_type,type",
        })
        if info.get("type") != "file" or info.get("path") != fid:
            raise DomainError(404, "Файл удалён или больше недоступен")
        name = str(info.get("name") or "")[:_MAX_NAME_LEN]
        provider_mime = str(info.get("mime_type") or "")
        mime = cloud_drives._mime_for(name, provider_mime)
        size = int(info.get("size") or 0)
    return connection, {
        "name": name, "size": size, "mime": mime,
        "provider_file_id": fid, "provider_mime": provider_mime,
        "folder_name": "Весь диск",
    }
