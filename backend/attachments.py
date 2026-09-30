import base64
import hashlib
import io
import os
from pathlib import Path

try:
    from backend.business import DomainError, identity, integer, stamp, string
    from backend.documents import Download
except ModuleNotFoundError:
    from business import DomainError, identity, integer, stamp, string
    from documents import Download


def directory():
    return Path(
        os.getenv(
            "UPLOAD_DIR", str(Path(__file__).resolve().parents[1] / "data/uploads")
        )
    ).resolve()


def download(row, con=None):
    if con is not None and getattr(con, "is_postgres", False):
        payload = con.execute(
            "SELECT content FROM file_payloads WHERE file_id=?", (row["id"],)
        ).fetchone()
        if not payload:
            raise DomainError(404, "Файл не найден")
        content = bytes(payload[0])
    else:
        root = directory()
        path = (root / row["storage_name"]).resolve()
        if path.parent != root or not path.is_file():
            raise DomainError(404, "Файл не найден")
        content = path.read_bytes()
    # Always attachment, never browser-executable user content.
    suffix = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "application/pdf": ".pdf",
        "text/plain": ".txt",
    }[row["mime"]]
    if row["mime"] == "text/plain" and Path(row["name"]).suffix.lower() == ".md":
        suffix = ".md"
    return Download(content, row["mime"], "smetra-" + row["id"] + suffix)


def route(service, method, parts, query, data):
    if method == "PATCH" and len(parts) == 1:
        row = service.get("files", parts[0])
        if row["mime"] != "text/plain" or Path(row["name"]).suffix.lower() != ".md":
            raise DomainError(400, "Редактировать здесь можно только Markdown-файлы")
        if data.get("sha256") != row["sha256"]:
            raise DomainError(409, "Файл изменился. Обновите страницу перед сохранением")
        try:
            raw = base64.b64decode(data.get("content", ""), validate=True)
            body = raw.decode("utf-8-sig")
            if not 1 <= len(raw) <= 1_000_000 or "\0" in body:
                raise ValueError("markdown bounds")
        except (ValueError, TypeError, UnicodeError):
            raise DomainError(400, "Markdown должен содержать текст UTF-8 до 1 МБ") from None
        used = service.con.execute(
            "SELECT coalesce(sum(size),0) FROM files WHERE workspace_id=?", (service.wid,)
        ).fetchone()[0]
        if used - row["size"] + len(raw) > 100_000_000:
            raise DomainError(413, "Лимит хранилища пространства — 100 МБ")
        digest = hashlib.sha256(raw).hexdigest()
        updated = service.con.execute(
            "UPDATE files SET size=?,sha256=? WHERE id=? AND workspace_id=? AND sha256=? RETURNING id",
            (len(raw), digest, row["id"], service.wid, row["sha256"]),
        ).fetchone()
        if not updated:
            raise DomainError(409, "Файл изменился. Обновите страницу перед сохранением")
        if getattr(service.con, "is_postgres", False):
            service.con.execute("UPDATE file_payloads SET content=? WHERE file_id=?", (raw, row["id"]))
        else:
            path = (directory() / row["storage_name"]).resolve()
            if path.parent != directory() or not path.is_file():
                raise DomainError(404, "Файл не найден")
            path.write_bytes(raw)
        from backend.assistant_files import index_file

        service.con.execute("DELETE FROM file_text_chunks WHERE file_id=? AND workspace_id=?", (row["id"], service.wid))
        index_file(service, {**dict(row), "sha256": digest}, raw)
        service.emit("file", row["id"], "Markdown-документ изменён", row["name"])
        return 200, {"file": {"id": row["id"], "name": row["name"], "size": len(raw), "sha256": digest}}
    if method == "GET":
        if parts:
            return 200, download(service.get("files", parts[0]), service.con)
        for key in ("quote_id", "project_id", "client_id", "construction_id"):
            if query.get(key):
                table = {
                    "quote_id": "quotes",
                    "project_id": "projects",
                    "client_id": "clients",
                    "construction_id": "construction_objects",
                }[key]
                service.get(table, query[key][0])
                return 200, {
                    "max_upload_bytes": int(os.getenv("MAX_UPLOAD_BYTES", "5000000")),
                    "items": [
                        dict(r)
                        for r in service.con.execute(
                            f"SELECT id,name,mime,size,sha256,public,created_at FROM files WHERE workspace_id=? AND {key}=? ORDER BY created_at DESC LIMIT 100",
                            (service.wid, query[key][0]),
                        )
                    ],
                }
        phrase = string(query.get("q", [""])[0], "Поиск", 100)
        return 200, {
            "items": [dict(row) for row in service.con.execute(
                "SELECT id,name,mime,size,sha256,public,created_at,quote_id,project_id,client_id,construction_id "
                "FROM files WHERE workspace_id=? AND instr(lower(name),lower(?))>0 "
                "ORDER BY created_at DESC LIMIT 50 OFFSET ?",
                (service.wid, phrase, service.page(query)),
            )],
        }
    if method == "DELETE" and parts:
        row = service.get("files", parts[0])
        service.con.execute(
            "DELETE FROM files WHERE id=? AND workspace_id=?", (row["id"], service.wid)
        )
        # Physical orphan cleanup is a separate maintenance operation after DB commits.
        service.emit("file", row["id"], "Вложение удалено")
        return 200, {"ok": True}
    if method != "POST":
        raise DomainError(405, "Метод не поддерживается")
    references = {
        key: data.get(key) or None for key in ("quote_id", "project_id", "client_id", "construction_id")
    }
    assistant_upload = data.get("assistant_upload") is True
    if sum(bool(v) for v in references.values()) != (0 if assistant_upload else 1):
        raise DomainError(400, "Привяжите файл к одной записи")
    for key, table in (
        ("quote_id", "quotes"),
        ("project_id", "projects"),
        ("client_id", "clients"),
        ("construction_id", "construction_objects"),
    ):
        if references[key]:
            service.get(table, references[key])
    name = string(data.get("name", ""), "Имя файла", 180, True)
    extension = Path(name).suffix.lower()
    if extension not in (".png", ".jpg", ".jpeg", ".pdf", ".txt", ".md"):
        raise DomainError(400, "Разрешены PNG, JPEG, PDF, TXT и MD")
    if assistant_upload and extension not in (".pdf", ".txt", ".md"):
        raise DomainError(400, "Ассистент читает PDF, TXT и MD")
    try:
        raw = base64.b64decode(data.get("content", ""), validate=True)
    except (ValueError, TypeError):
        raise DomainError(400, "Некорректное содержимое файла") from None
    maximum = int(os.getenv("MAX_UPLOAD_BYTES", "5000000"))
    if not 1 <= len(raw) <= maximum:
        raise DomainError(413, f"Максимальный размер файла — {maximum // 1_000_000} МБ")
    if extension in (".png", ".jpg", ".jpeg"):
        try:
            from PIL import Image

            with Image.open(io.BytesIO(raw)) as img:
                if img.width * img.height > 20_000_000 or img.format not in (
                    "PNG",
                    "JPEG",
                ):
                    raise ValueError("image bounds")
                expected = "PNG" if extension == ".png" else "JPEG"
                if img.format != expected:
                    raise ValueError("extension mismatch")
                img.verify()
            # Discard metadata and trailing/polyglot payloads.
            with Image.open(io.BytesIO(raw)) as img:
                output = io.BytesIO()
                img.convert("RGBA" if expected == "PNG" else "RGB").save(
                    output, format=expected
                )
                raw = output.getvalue()
            mime = "image/png" if expected == "PNG" else "image/jpeg"
        except ImportError:
            raise DomainError(
                503, "Установите зависимости обработки изображений"
            ) from None
        except Exception:
            raise DomainError(
                400, "Изображение повреждено или слишком большое"
            ) from None
    elif extension == ".pdf":
        if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-1024:]:
            raise DomainError(400, "Неверный формат PDF")
        if any(
            marker in raw
            for marker in (
                b"/JavaScript",
                b"/JS",
                b"/Launch",
                b"/EmbeddedFile",
                b"/OpenAction",
                b"/AA",
            )
        ):
            raise DomainError(
                400,
                "PDF содержит активные элементы. Экспортируйте плоскую копию документа",
            )
        try:
            from pypdf import PdfReader
            from pypdf.generic import DictionaryObject, ArrayObject, IndirectObject

            reader = PdfReader(io.BytesIO(raw), strict=True)
            if reader.is_encrypted or len(reader.pages) > 300:
                raise ValueError("encrypted or too many pages")
            seen = set()
            forbidden = {
                "/JavaScript",
                "/JS",
                "/Launch",
                "/EmbeddedFiles",
                "/EmbeddedFile",
                "/OpenAction",
                "/AA",
                "/RichMedia",
                "/XFA",
            }

            def inspect(value, depth=0):
                if depth > 50 or len(seen) > 20000:
                    raise ValueError("object limits")
                if isinstance(value, IndirectObject):
                    key = (value.idnum, value.generation)
                    if key in seen:
                        return
                    seen.add(key)
                    value = value.get_object()
                if isinstance(value, DictionaryObject):
                    if forbidden.intersection(value.keys()):
                        raise ValueError("active content")
                    for child in value.values():
                        inspect(child, depth + 1)
                elif isinstance(value, ArrayObject):
                    for child in value:
                        inspect(child, depth + 1)

            inspect(reader.trailer)
        except ImportError:
            raise DomainError(503, "Установите pypdf для проверки PDF") from None
        except Exception:
            raise DomainError(
                400, "PDF не прошёл проверку структуры и активного содержимого"
            ) from None
        mime = "application/pdf"
    else:
        try:
            text = raw.decode("utf-8-sig")
            if "\0" in text:
                raise ValueError("null")
        except (UnicodeError, ValueError):
            raise DomainError(400, "TXT должен содержать текст UTF-8") from None
        mime = "text/plain"
    used = service.con.execute(
        "SELECT coalesce(sum(size),0) FROM files WHERE workspace_id=?", (service.wid,)
    ).fetchone()[0]
    if used + len(raw) > 100_000_000:
        raise DomainError(413, "Лимит хранилища пространства — 100 МБ")
    public = integer(data.get("public", 0), "Публичность", 0, 1)
    if public and not references["quote_id"]:
        raise DomainError(400, "Публичный файл должен быть привязан к смете")
    fid = identity()
    storage = fid + ".bin"
    values = dict(
        id=fid,
        workspace_id=service.wid,
        **references,
        name=name,
        mime=mime,
        size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        storage_name=storage,
        public=public,
        created_at=stamp(),
    )
    if getattr(service.con, "is_postgres", False):
        service.insert("files", values)
        service.con.execute(
            "INSERT INTO file_payloads(file_id,content) VALUES(?,?)", (fid, raw)
        )
        from backend.assistant_files import index_file

        index_file(service, values, raw)
        service.emit("file", fid, "Файл прикреплён", name)
    else:
        root = directory()
        root.mkdir(parents=True, exist_ok=True)
        path = root / storage
        path.write_bytes(raw)
        try:
            service.insert("files", values)
            from backend.assistant_files import index_file

            index_file(service, values, raw)
            service.emit("file", fid, "Файл прикреплён", name)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    return 201, {
        "file": {key: values[key] for key in ("id", "name", "mime", "size", "sha256", "public")}
    }
