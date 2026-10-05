"""Reviewable file/document actions; no arbitrary paths, external sends or payments."""

import hashlib
import json

from backend.business import DomainError, stamp, string
from backend.file_metadata import REFERENCES, TABLES, changes, fingerprint, update


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def list_documents(service, query):
    rows = service.con.execute(
        "SELECT id,name,kind,template,number,quote_id,project_id,created_at FROM documents "
        "WHERE workspace_id=? AND instr(lower(name),lower(?))>0 ORDER BY created_at DESC LIMIT 20",
        (service.wid, query),
    ).fetchall()
    return {"items": [dict(row) for row in rows]}


def read_document(service, document_id):
    row = service.get("documents", document_id)
    snapshot = json.loads(row["snapshot"])
    # A saved client document is the source, never the current internal project state.
    return {**{key: row[key] for key in ("id", "name", "kind", "template", "number", "quote_id", "project_id")},
            "snapshot": {key: snapshot[key] for key in
                         ("title", "client", "description", "terms", "currency", "amount_kopecks", "paid", "version")
                         if key in snapshot},
            "items": [{key: item[key] for key in ("name", "quantity", "unit", "unit_price", "subtotal")
                       if key in item} for item in snapshot.get("items", [])[:50]],
            "pdf_url": "/api/documents/" + row["id"] + "/pdf"}


def prepare_resource(service, name, args):
    if name == "create_document":
        from backend.documents import prepare_document

        values = {key: value for key, value in args.items() if key in ("quote_id", "kind", "template")}
        document = prepare_document(service, values)
        quote = service.get("quotes", document["quote_id"])
        snapshot = json.loads(document["snapshot"])
        values.update(_source_revision=quote["revision"], _snapshot_hash=digest(snapshot),
                      _preview={"kind": "fields", "currency": snapshot.get("currency", "RUB"), "rows": [
                          {"field": "document", "before": None, "after": document["name"]},
                          {"field": "source", "before": None, "after": snapshot.get("title", "Смета")},
                          {"field": "template", "before": None, "after": document["template"]},
                          {"field": "amount", "before": None, "after": snapshot["amount_kopecks"]},
                      ]})
        return values, "Создать документ · " + document["name"]
    row = service.get("files", string(args.get("id", ""), "Файл", 80, True))
    payload = ({"name": args.get("name")} if name == "rename_file" else
               {"target": args.get("target"), "target_id": args.get("target_id")})
    values = changes(service, row, payload)
    rows = [{"field": "name", "before": row["name"], "after": values["name"]}] if name == "rename_file" else []
    if name == "move_file":
        before = "Вложения ассистента"
        for kind, field in REFERENCES.items():
            if row[field]:
                old = service.get(TABLES[kind], row[field])
                before = old["title"] if kind == "quotes" else old["name"]
        target = service.get(TABLES[payload["target"]], payload["target_id"])
        after = target["title"] if payload["target"] == "quotes" else target["name"]
        rows.append({"field": "attachment", "before": before, "after": after})
    return {"id": row["id"], **payload, "_etag": fingerprint(row),
            "_undo_fields": {key: row[key] for key in values},
            "_preview": {"kind": "fields", "rows": rows}}, (
                "Переименовать файл · " if name == "rename_file" else "Перенести файл · ") + row["name"][:100]


def apply_resource(service, name, args):
    if name == "create_document":
        from backend.documents import prepare_document

        quote = service.get("quotes", args["quote_id"])
        if quote["revision"] != args["_source_revision"]:
            raise DomainError(409, "Смета изменилась. Обновите предложение документа")
        # The caller's write transaction serializes numbering (BEGIN IMMEDIATE /
        # the PostgreSQL adapter's transaction-scoped advisory lock).
        document = prepare_document(service, args)
        if digest(json.loads(document["snapshot"])) != args["_snapshot_hash"]:
            raise DomainError(409, "Данные документа изменились. Обновите предложение")
        service.insert("documents", document)
        service.emit("document", document["id"], "Документ сформирован", document["name"])
        return 201, {"document": {key: value for key, value in document.items() if key != "snapshot"}}, {
            "mode": "created_document", "id": document["id"], "digest": digest(document)}
    row = service.get("files", args["id"])
    payload = {key: value for key, value in args.items() if key in ("name", "target", "target_id")}
    values = changes(service, row, payload)
    before = {key: row[key] for key in values}
    status, result = update(service, row, values, args["_etag"])
    return status, result, {"mode": "file_metadata", "id": row["id"], "fields": before,
                            "etag": result["file"]["metadata_etag"]}


def document_preview(service, action_id):
    from backend.documents import Download, pdf, prepare_document

    row = service.con.execute(
        "SELECT * FROM assistant_actions WHERE id=? AND workspace_id=? AND user_id=?",
        (string(action_id, "Предложение", 80, True), service.wid, service.user["id"]),
    ).fetchone()
    if not row or row["tool"] != "create_document":
        raise DomainError(404, "Предложение документа не найдено")
    if row["status"] != "pending" or row["expires_at"] < stamp():
        raise DomainError(409, "Предложение больше не доступно")
    args = json.loads(row["arguments"])
    quote = service.get("quotes", args["quote_id"])
    document = prepare_document(service, args)
    if quote["revision"] != args["_source_revision"] or digest(json.loads(document["snapshot"])) != args["_snapshot_hash"]:
        raise DomainError(409, "Источник документа изменился. Обновите предложение")
    return 200, Download(pdf(document), "application/pdf", "smetra-document-preview.pdf")


def undo_resource(service, state):
    if state["mode"] == "created_document":
        row = service.get("documents", state["id"])
        if digest(dict(row)) != state["digest"]:
            raise DomainError(409, "Документ изменился. Отмена недоступна")
        service.con.execute("DELETE FROM documents WHERE id=? AND workspace_id=?", (row["id"], service.wid))
        return {"document_id": row["id"], "deleted": True}
    row = service.get("files", state["id"])
    if state["mode"] == "file_metadata":
        # Revalidate destination and references before restoring a previous attachment.
        for kind, field in REFERENCES.items():
            if state["fields"].get(field):
                service.get(TABLES[kind], state["fields"][field])
        if any(field in state["fields"] for field in REFERENCES.values()):
            for kind, field in REFERENCES.items():
                if state["fields"].get(field):
                    changes(service, row, {"target": kind, "target_id": state["fields"][field]})
                    break
            else:
                if row["public"]:
                    raise DomainError(409, "Публичное вложение нельзя отсоединять")
        return update(service, row, state["fields"], state["etag"])[1]
    if state["mode"] == "markdown":
        if row["sha256"] != state["sha256"]:
            raise DomainError(409, "Документ изменился. Отмена не перезапишет новые изменения")
        previous = service.con.execute(
            "SELECT id FROM file_versions WHERE id=? AND file_id=? AND workspace_id=?",
            (state["version_id"], row["id"], service.wid),
        ).fetchone()
        if not previous:
            raise DomainError(409, "Предыдущая версия документа больше недоступна")
        return service.route("POST", "files", [row["id"], "versions", previous["id"], "restore"], {},
                             {"sha256": row["sha256"]})[1]
    raise DomainError(409, "Это действие нельзя отменить")
