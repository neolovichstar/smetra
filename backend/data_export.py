"""Owner-only, paged workspace export primitives.

The browser assembles pages into a ZIP so serverless responses stay small.
Secrets and bearer links are deliberately excluded from every exported row.
"""

import hashlib
import re
import zlib

try:
    from backend.business import DomainError
    from backend.attachments import download as download_attachment
    from backend.documents import Download
except ModuleNotFoundError:
    from business import DomainError
    from attachments import download as download_attachment
    from documents import Download


TABLES = (
    "workspace_members", "clients", "catalog_items", "quotes", "quote_items", "quote_versions",
    "activity", "projects", "project_stages", "tasks", "leads",
    "project_payments", "expenses", "comments", "notifications",
    "notification_reads", "custom_field_definitions", "estimate_templates",
    "documents", "files", "intake_forms", "client_requests",
    "assistant_conversations", "assistant_messages", "workspace_knowledge",
    "file_text_chunks", "file_versions", "construction_objects",
    "construction_zones", "construction_measurements", "construction_quantities",
    "construction_facts", "construction_defects", "construction_daily_logs",
    "construction_log_photos", "construction_suppliers", "construction_purchases",
    "construction_changes", "construction_price_batches", "catalog_price_history",
    "assistant_memory", "user_profiles",
)

SCOPES = {
    "workspace_members": ("SELECT workspace_id,user_id,role FROM workspace_members WHERE workspace_id=? ORDER BY user_id",),
    "quote_items": ("SELECT qi.* FROM quote_items qi JOIN quotes q ON q.id=qi.quote_id WHERE q.workspace_id=? ORDER BY q.id,qi.position,qi.id",),
    "quote_versions": ("SELECT qv.* FROM quote_versions qv JOIN quotes q ON q.id=qv.quote_id WHERE q.workspace_id=? ORDER BY q.id,qv.version",),
    "file_text_chunks": ("SELECT * FROM file_text_chunks WHERE workspace_id=? ORDER BY file_id,page",),
    "construction_log_photos": ("SELECT * FROM construction_log_photos WHERE workspace_id=? ORDER BY log_id,file_id",),
    "notification_reads": ("SELECT nr.* FROM notification_reads nr JOIN notifications n ON n.id=nr.notification_id WHERE n.workspace_id=? AND nr.user_id=? ORDER BY nr.notification_id", "user"),
    "assistant_conversations": ("SELECT * FROM assistant_conversations WHERE workspace_id=? AND user_id=? ORDER BY created_at,id", "user"),
    "assistant_messages": ("SELECT * FROM assistant_messages WHERE workspace_id=? AND user_id=? ORDER BY created_at,id", "user"),
    "assistant_memory": ("SELECT * FROM assistant_memory WHERE workspace_id=? AND user_id=? ORDER BY created_at,id", "user"),
    "user_profiles": ("SELECT * FROM user_profiles WHERE user_id=?", "profile"),
}

SECRET_KEYS = re.compile(r"(?:^|_)(?:token|secret|password|verifier|challenge|session|storage_name|idempotency_key)(?:$|_)|(?:public_.*(?:url|link)|share_?url)$", re.I)


def _owner(service):
    if service.role != "owner":
        raise DomainError(403, "Экспорт доступен владельцу рабочего пространства")


def _query(service, table, offset=0, limit=100):
    if table not in TABLES:
        raise DomainError(404, "Раздел экспорта не найден")
    scope = SCOPES.get(table)
    if scope:
        sql, *modes = scope
        mode = modes[0] if modes else "workspace"
        params = (service.wid, service.user["id"]) if mode == "user" else ((service.user["id"],) if mode == "profile" else (service.wid,))
        if mode == "profile":
            sql += " ORDER BY user_id"
    else:
        sql = f"SELECT * FROM {table} WHERE workspace_id=? ORDER BY id"
        params = (service.wid,)
    return service.con.execute(sql + " LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()


def _count(service, table):
    scope = SCOPES.get(table)
    if scope:
        sql, *modes = scope
        mode = modes[0] if modes else "workspace"
        params = (service.wid, service.user["id"]) if mode == "user" else ((service.user["id"],) if mode == "profile" else (service.wid,))
        return service.con.execute(f"SELECT count(*) FROM ({sql}) export_rows", params).fetchone()[0]
    return service.con.execute(f"SELECT count(*) FROM {table} WHERE workspace_id=?", (service.wid,)).fetchone()[0]


def _clean(value):
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items() if not SECRET_KEYS.search(str(key))}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, bytes):
        return {"encoding": "base64", "data": __import__("base64").b64encode(value).decode("ascii")}
    if isinstance(value, str) and value.lstrip()[:1] in ("{", "["):
        try:
            return __import__("json").dumps(_clean(__import__("json").loads(value)), ensure_ascii=False, separators=(",", ":"))
        except (ValueError, TypeError):
            pass
    return value


def _row(table, row):
    value = dict(row)
    # File payloads and history are separate authenticated downloads. Never put
    # server paths or compressed binary blobs into the JSON data stream.
    value.pop("storage_name", None)
    if table == "file_versions":
        value.pop("content", None)
        value["size"] = _version_content(row)[1]
    return _clean(value)


def _version_content(row):
    try:
        content = zlib.decompress(bytes(row["content"]))
    except zlib.error:
        raise DomainError(409, "История файла повреждена") from None
    if hashlib.sha256(content).hexdigest() != row["sha256"]:
        raise DomainError(409, "История файла повреждена")
    return content, len(content)


def route(service, method, parts, query):
    _owner(service)
    if method != "GET":
        raise DomainError(405, "Метод не поддерживается")
    if not parts:
        workspace = service.con.execute(
            "SELECT id,name,currency,settings,created_at FROM workspaces WHERE id=?",
            (service.wid,),
        ).fetchone()
        if not workspace:
            raise DomainError(404, "Рабочее пространство не найдено")
        tables = []
        for table in TABLES:
            tables.append({"name": table, "count": _count(service, table)})
        file_rows = service.con.execute(
            "SELECT id,name,mime,size,sha256,quote_id,project_id,client_id,public,created_at FROM files WHERE workspace_id=? ORDER BY id",
            (service.wid,),
        ).fetchall()
        versions = service.con.execute(
            "SELECT id,file_id,revision,sha256,size,content,created_at FROM file_versions WHERE workspace_id=? ORDER BY id",
            (service.wid,),
        ).fetchall()
        return 200, {
            "format": "smetra-workspace-export",
            "version": 1,
            "created_at": __import__("time").time_ns() // 1_000_000_000,
            "workspace_id": service.wid,
            "workspace": _clean({**dict(workspace), "settings": __import__("json").loads(workspace["settings"])}),
            "user": {key: service.user[key] for key in ("id", "name", "email", "created_at")},
            "tables": tables,
            "files": [dict(row) for row in file_rows],
            "file_versions": [
                {"id": row["id"], "file_id": row["file_id"], "revision": row["revision"],
                 "sha256": row["sha256"], "size": _version_content(row)[1], "created_at": row["created_at"]}
                for row in versions
            ],
            "total_file_bytes": sum(row["size"] for row in file_rows),
        }
    if parts[0] == "data" and len(parts) == 2:
        table = parts[1]
        try:
            offset = max(0, min(int(query.get("offset", ["0"])[0]), 2_147_483_647))
            limit = max(1, min(int(query.get("limit", ["100"])[0]), 200))
        except (TypeError, ValueError):
            raise DomainError(400, "Некорректная страница экспорта") from None
        return 200, {"items": [_row(table, row) for row in _query(service, table, offset, limit)]}
    if parts[0] == "files" and len(parts) == 2:
        row = service.con.execute(
            "SELECT * FROM files WHERE id=? AND workspace_id=?", (parts[1], service.wid)
        ).fetchone()
        if not row:
            raise DomainError(404, "Файл не найден")
        item = download_attachment(row, service.con)
        if hashlib.sha256(item.data).hexdigest() != row["sha256"] or len(item.data) != row["size"]:
            raise DomainError(409, "Файл изменился или повреждён. Повторите экспорт")
        return 200, Download(item.data, item.mime, "smetra-" + row["id"] + ".bin")
    if parts[0] == "versions" and len(parts) == 2:
        row = service.con.execute(
            "SELECT id,file_id,revision,sha256,size,content FROM file_versions WHERE id=? AND workspace_id=?",
            (parts[1], service.wid),
        ).fetchone()
        if not row:
            raise DomainError(404, "Версия файла не найдена")
        content, _size = _version_content(row)
        return 200, Download(content, "application/octet-stream", "smetra-version.bin")
    raise DomainError(404, "Раздел экспорта не найден")
