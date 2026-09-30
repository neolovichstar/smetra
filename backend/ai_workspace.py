"""Durable assistant conversations and curated workspace knowledge."""

from backend.business import DomainError, choice, identity, integer, stamp, string, transaction


def conversation(service, conversation_id):
    row = service.con.execute(
        "SELECT * FROM assistant_conversations WHERE id=? AND workspace_id=? AND user_id=?",
        (conversation_id, service.wid, service.user["id"]),
    ).fetchone()
    if not row:
        raise DomainError(404, "Диалог не найден")
    return row


def conversations(service, method, parts, data):
    if method == "GET" and not parts:
        rows = service.con.execute(
            "SELECT id,title,context_entity,context_id,pinned,created_at,updated_at "
            "FROM assistant_conversations WHERE workspace_id=? AND user_id=? "
            "ORDER BY pinned DESC,updated_at DESC LIMIT 50",
            (service.wid, service.user["id"]),
        ).fetchall()
        return 200, {"items": [dict(row) for row in rows]}
    if method == "POST" and not parts:
        title = string(data.get("title", "Новый диалог"), "Название", 120, True)
        context_entity = data.get("context_entity") or ""
        context_id = data.get("context_id") or ""
        if context_entity:
            from backend.assistant import verified_context

            verified_context(service, {"entity": context_entity, "id": context_id})
        row = dict(
            id=identity(), workspace_id=service.wid, user_id=service.user["id"],
            title=title, context_entity=context_entity, context_id=context_id,
            pinned=0, created_at=stamp(), updated_at=stamp(),
        )
        service.con.execute(
            "INSERT INTO assistant_conversations(id,workspace_id,user_id,title,context_entity,context_id,pinned,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)", tuple(row.values()),
        )
        return 201, {"conversation": row}
    if len(parts) != 1:
        raise DomainError(404, "Диалог не найден")
    row = conversation(service, string(parts[0], "Диалог", 80, True))
    if method == "GET":
        messages = service.con.execute(
            "SELECT role,content,created_at FROM assistant_messages "
            "WHERE conversation_id=? AND workspace_id=? AND user_id=? "
            "ORDER BY created_at DESC,id DESC LIMIT 50",
            (row["id"], service.wid, service.user["id"]),
        ).fetchall()
        return 200, {"conversation": dict(row), "messages": [dict(item) for item in reversed(messages)]}
    if method == "PATCH":
        if not isinstance(data, dict) or not set(data).issubset({"title", "pinned"}) or not data:
            raise DomainError(400, "Неверные поля диалога")
        title = string(data.get("title", row["title"]), "Название", 120, True)
        pinned = integer(data.get("pinned", row["pinned"]), "Закрепление", 0, 1)
        service.con.execute(
            "UPDATE assistant_conversations SET title=?,pinned=?,updated_at=? WHERE id=? AND workspace_id=? AND user_id=?",
            (title, pinned, stamp(), row["id"], service.wid, service.user["id"]),
        )
        return 200, {"conversation": dict(row, title=title, pinned=pinned)}
    if method == "DELETE":
        with transaction(service.con):
            service.con.execute(
                "DELETE FROM assistant_messages WHERE conversation_id=? AND workspace_id=? AND user_id=?",
                (row["id"], service.wid, service.user["id"]),
            )
            service.con.execute(
                "DELETE FROM assistant_conversations WHERE id=? AND workspace_id=? AND user_id=?",
                (row["id"], service.wid, service.user["id"]),
            )
        return 200, {"ok": True}
    raise DomainError(405, "Метод не поддерживается")


def knowledge(service, method, parts, data):
    if method == "GET" and not parts:
        rows = service.con.execute(
            "SELECT id,title,content,kind,enabled,created_at,updated_at FROM workspace_knowledge "
            "WHERE workspace_id=? ORDER BY kind DESC,updated_at DESC LIMIT 50",
            (service.wid,),
        ).fetchall()
        return 200, {"items": [dict(row) for row in rows],
                     "can_edit": service.role in ("owner", "admin", "manager")}
    if method != "GET":
        service.write_access(True)
    if method == "POST" and not parts:
        count = service.con.execute(
            "SELECT count(*) FROM workspace_knowledge WHERE workspace_id=?", (service.wid,)
        ).fetchone()[0]
        if count >= 30:
            raise DomainError(409, "В базе знаний максимум 30 записей")
        item = dict(
            id=identity(), workspace_id=service.wid,
            title=string(data.get("title", ""), "Название", 120, True),
            content=string(data.get("content", ""), "Содержание", 12000, True),
            kind=choice(data.get("kind", "reference"), ("reference", "rule"), "Тип записи"),
            enabled=integer(data.get("enabled", 1), "Активность", 0, 1),
            created_by=service.user["id"], created_at=stamp(), updated_at=stamp(),
        )
        service.con.execute(
            "INSERT INTO workspace_knowledge(id,workspace_id,title,content,kind,enabled,created_by,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)", tuple(item.values()),
        )
        return 201, {"item": item}
    if len(parts) != 1:
        raise DomainError(404, "Запись не найдена")
    row = service.get("workspace_knowledge", string(parts[0], "Запись", 80, True))
    if method == "GET":
        return 200, {"item": dict(row)}
    if method == "PATCH":
        if not isinstance(data, dict) or not set(data).issubset({"title", "content", "kind", "enabled"}) or not data:
            raise DomainError(400, "Неверные поля записи")
        title = string(data.get("title", row["title"]), "Название", 120, True)
        content = string(data.get("content", row["content"]), "Содержание", 12000, True)
        kind = choice(data.get("kind", row["kind"]), ("reference", "rule"), "Тип записи")
        enabled = integer(data.get("enabled", row["enabled"]), "Активность", 0, 1)
        service.con.execute(
            "UPDATE workspace_knowledge SET title=?,content=?,kind=?,enabled=?,updated_at=? "
            "WHERE id=? AND workspace_id=?",
            (title, content, kind, enabled, stamp(), row["id"], service.wid),
        )
        return 200, {"item": dict(row, title=title, content=content, kind=kind, enabled=enabled)}
    if method == "DELETE":
        service.con.execute(
            "DELETE FROM workspace_knowledge WHERE id=? AND workspace_id=?", (row["id"], service.wid)
        )
        return 200, {"ok": True}
    raise DomainError(405, "Метод не поддерживается")


def active_rules(service):
    rows = service.con.execute(
        "SELECT title,content FROM workspace_knowledge WHERE workspace_id=? AND kind='rule' AND enabled=1 "
        "ORDER BY updated_at DESC LIMIT 5", (service.wid,),
    ).fetchall()
    # Owner-curated rules are user preferences, subordinate to the safety prompt.
    return "\n".join(f"{row['title']}: {row['content'][:800]}" for row in rows)[:3000]


def find_knowledge(service, query=""):
    phrase = string(query, "Поиск", 100).strip().casefold()
    if len(phrase) < 2:
        return {"items": []}
    rows = service.con.execute(
        "SELECT id,title,content FROM workspace_knowledge WHERE workspace_id=? AND enabled=1 "
        "AND (instr(lower(title),?)>0 OR instr(lower(content),?)>0) "
        "ORDER BY updated_at DESC LIMIT 5",
        (service.wid, phrase, phrase),
    ).fetchall()
    from backend.assistant_files import _SECRET

    return {"items": [
        {"id": row["id"], "title": row["title"],
         "excerpt": _SECRET.sub("[секрет скрыт]", row["content"][:1600])}
        for row in rows
    ]}
