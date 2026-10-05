"""Workspace-scoped file metadata, with optimistic checks independent of content."""

import hashlib
from pathlib import Path

from backend.business import DomainError, packed, string

REFERENCES = {"quotes": "quote_id", "clients": "client_id", "projects": "project_id",
              "construction": "construction_id"}
TABLES = {"quotes": "quotes", "clients": "clients", "projects": "projects",
          "construction": "construction_objects"}
FIELDS = ("name", "sha256", "public", *REFERENCES.values())


def ensure_movable(service, row):
    if row["public"]:
        raise DomainError(409, "Публичное вложение нельзя переносить; прикрепите отдельную копию")
    for table, field in (("construction_defects", "photo_file_id"),
                         ("construction_log_photos", "file_id"),
                         ("construction_purchases", "receipt_file_id")):
        if service.con.execute(f"SELECT 1 FROM {table} WHERE {field}=? AND workspace_id=? LIMIT 1",
                               (row["id"], service.wid)).fetchone():
            raise DomainError(409, "Файл используется в дефекте, журнале или закупке; перенесите копию")


def fingerprint(row):
    return hashlib.sha256(packed({key: row[key] for key in FIELDS}).encode()).hexdigest()


def public_metadata(row):
    return {**{key: row[key] for key in ("id", "name", "mime", "size", "sha256", "created_at",
                                        "public", *REFERENCES.values())},
            "metadata_etag": fingerprint(row)}


def changes(service, row, data):
    if not isinstance(data, dict) or not set(data).issubset({"name", "target", "target_id"}):
        raise DomainError(400, "Неверные поля файла")
    values = {}
    if "name" in data:
        name = string(data["name"], "Название", 180, True)
        if (name != data["name"] or name.endswith(".") or
                any(ord(char) < 32 or char in '\\/:<>|?*"' for char in name) or
                Path(name).suffix.lower() != Path(row["name"]).suffix.lower()):
            raise DomainError(400, "Сохраните расширение файла; название не должно содержать путь")
        values["name"] = name
    if "target" in data or "target_id" in data:
        target = data.get("target")
        if target not in REFERENCES:
            raise DomainError(400, "Выберите клиента, смету, заказ или объект")
        destination = service.get(TABLES[target], string(data.get("target_id", ""), "Запись", 80, True))
        refs = {field: destination["id"] if kind == target else None
                for kind, field in REFERENCES.items()}
        if any(row[field] != value for field, value in refs.items()):
            ensure_movable(service, row)
            values.update(refs)
    values = {key: value for key, value in values.items() if row[key] != value}
    if not values:
        raise DomainError(409, "Файл уже содержит эти данные")
    return values


def update(service, row, values, expected):
    service.write_access()
    if fingerprint(row) != expected:
        raise DomainError(409, "Файл изменился. Обновите данные перед изменением")
    if not values or not set(values).issubset({"name", *REFERENCES.values()}):
        raise DomainError(400, "Неверные поля файла")
    if set(values).intersection(REFERENCES.values()):
        ensure_movable(service, row)
    conditions = " AND ".join(f"coalesce({field},'')=?" if field in REFERENCES.values()
                              else f"{field}=?" for field in FIELDS)
    changed = service.con.execute(
        f"UPDATE files SET {','.join(key+'=?' for key in values)} "
        f"WHERE id=? AND workspace_id=? AND {conditions} RETURNING *",
        (*values.values(), row["id"], service.wid, *(row[key] if row[key] is not None else "" for key in FIELDS)),
    ).fetchone()
    if not changed:
        raise DomainError(409, "Файл изменился. Обновите данные перед изменением")
    service.emit("file", row["id"], "Данные файла изменены", changed["name"])
    return 200, {"file": public_metadata(changed)}


def route(service, method, file_id, data):
    row = service.get("files", string(file_id, "Файл", 80, True))
    if method == "GET":
        from backend import file_processing

        return 200, {"file": public_metadata(row), "processing": file_processing.state(service, row)}
    if method != "PATCH":
        raise DomainError(405, "Метод не поддерживается")
    service.write_access()
    if not isinstance(data, dict) or not isinstance(data.get("metadata_etag"), str):
        raise DomainError(400, "Обновите данные файла перед изменением")
    expected = data["metadata_etag"]
    return update(service, row, changes(service, row, {key: value for key, value in data.items()
                                                    if key != "metadata_etag"}), expected)
