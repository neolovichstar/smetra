"""Durable assistant conversations and curated workspace knowledge."""

from contextlib import contextmanager

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
    if method == "POST" and not parts and data.get("adopt_general") is True or method == "DELETE" and parts == ["general"]:
        with _general_edit_lock(service):
            return _dispatch_conversations(service, method, parts, data)
    return _dispatch_conversations(service, method, parts, data)


@contextmanager
def _general_edit_lock(service):
    from backend.redis_infra import RedisUnavailable, acquire_lock

    try:
        lease = acquire_lock("assistant", service.user["id"], ttl=30)
    except RedisUnavailable:
        raise DomainError(503, "Изменение диалога временно недоступно") from None
    if lease is None:
        raise DomainError(409, "Дождитесь завершения ответа ассистента")
    try:
        yield
    finally:
        lease.release()


def _dispatch_conversations(service, method, parts, data):
    if method == "POST":
        with transaction(service.con):
            operation = None
            if not parts:
                from backend.creation_requests import lookup

                operation, record_id = lookup(service, "conversation", data)
                if record_id:
                    row = service.con.execute(
                        "SELECT * FROM assistant_conversations WHERE id=? AND workspace_id=? AND user_id=?",
                        (record_id, service.wid, service.user["id"]),
                    ).fetchone()
                    if not row:
                        raise DomainError(409, "Диалог этого запроса уже удалён. Начните новый диалог")
                    return 200, {"conversation": dict(row), "replayed": True}
            count = service.con.execute(
                "SELECT count(*) FROM assistant_conversations WHERE workspace_id=? AND user_id=?",
                (service.wid, service.user["id"]),
            ).fetchone()[0]
            if count >= 50:
                raise DomainError(409, "Максимум 50 диалогов. Удалите ненужный диалог")
            result = _conversations(service, method, parts, data)
            if not parts:
                from backend.creation_requests import remember

                remember(service, "conversation", operation, result[1]["conversation"]["id"])
            return result
    return _conversations(service, method, parts, data)


def context_fields(service, data, row=None):
    entity = data.get("context_entity", row["context_entity"] if row else "")
    record_id = data.get("context_id", row["context_id"] if row else "")
    if not isinstance(entity, str) or not isinstance(record_id, str) or bool(entity) != bool(record_id):
        raise DomainError(400, "Контекст должен содержать раздел и ID записи")
    if entity:
        from backend.assistant import verified_context

        verified = verified_context(service, {"entity": entity, "id": record_id})
        record_id = verified["id"]
    return entity, record_id


def _conversations(service, method, parts, data):
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
        context_entity, context_id = context_fields(service, data)
        adopt = data.get("adopt_general", False)
        if not isinstance(adopt, bool):
            raise DomainError(400, "Неверный параметр сохранения общего диалога")
        if adopt:
            _ensure_general_idle(service)
        row = dict(
            id=identity(), workspace_id=service.wid, user_id=service.user["id"],
            title=title, context_entity=context_entity, context_id=context_id,
            pinned=0, created_at=stamp(), updated_at=stamp(),
        )
        service.con.execute(
            "INSERT INTO assistant_conversations(id,workspace_id,user_id,title,context_entity,context_id,pinned,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)", tuple(row.values()),
        )
        if adopt:
            service.con.execute(
                "UPDATE assistant_messages SET conversation_id=? "
                "WHERE conversation_id IS NULL AND workspace_id=? AND user_id=?",
                (row["id"], service.wid, service.user["id"]),
            )
            service.con.execute(
                "UPDATE assistant_jobs SET conversation_id=? "
                "WHERE conversation_id IS NULL AND kind='chat' AND workspace_id=? AND user_id=?",
                (row["id"], service.wid, service.user["id"]),
            )
        return 201, {"conversation": row}
    if method == "POST" and len(parts) == 2 and parts[1] == "fork":
        source = conversation(service, string(parts[0], "Диалог", 80, True))
        message_id = string(data.get("message_id", ""), "Сообщение", 80, True)
        recent = list(reversed(service.con.execute(
            "SELECT id,role,content,created_at FROM assistant_messages "
            "WHERE conversation_id=? AND workspace_id=? AND user_id=? "
            "ORDER BY created_at DESC,id DESC LIMIT 50",
            (source["id"], service.wid, service.user["id"]),
        ).fetchall()))
        selected = next((index for index, item in enumerate(recent) if item["id"] == message_id), None)
        if selected is None:
            raise DomainError(404, "Сообщение для новой ветки не найдено")
        title = string(data.get("title", "Ветка · " + source["title"][:100]), "Название", 120, True)
        fork = dict(id=identity(), workspace_id=service.wid, user_id=service.user["id"],
                    title=title, context_entity=source["context_entity"],
                    context_id=source["context_id"], pinned=0,
                    created_at=stamp(), updated_at=stamp())
        service.con.execute(
            "INSERT INTO assistant_conversations(id,workspace_id,user_id,title,context_entity,context_id,pinned,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)", tuple(fork.values()),
        )
        for item in recent[:selected + 1]:
            service.con.execute(
                "INSERT INTO assistant_messages(id,workspace_id,user_id,role,content,created_at,conversation_id) "
                "VALUES(?,?,?,?,?,?,?)",
                (identity(), service.wid, service.user["id"], item["role"], item["content"],
                 item["created_at"], fork["id"]),
            )
        return 201, {"conversation": fork, "copied_messages": selected + 1}
    if method == "DELETE" and parts == ["general"]:
        with transaction(service.con):
            _ensure_general_idle(service)
            service.con.execute(
                "DELETE FROM assistant_messages WHERE conversation_id IS NULL AND workspace_id=? AND user_id=?",
                (service.wid, service.user["id"]),
            )
        return 200, {"ok": True}
    if len(parts) != 1:
        raise DomainError(404, "Диалог не найден")
    row = conversation(service, string(parts[0], "Диалог", 80, True))
    if method == "GET":
        messages = service.con.execute(
            "SELECT id,role,content,created_at FROM assistant_messages "
            "WHERE conversation_id=? AND workspace_id=? AND user_id=? "
            "ORDER BY created_at DESC,id DESC LIMIT 50",
            (row["id"], service.wid, service.user["id"]),
        ).fetchall()
        return 200, {"conversation": dict(row), "messages": [dict(item) for item in reversed(messages)]}
    if method == "PATCH":
        if not isinstance(data, dict) or not set(data).issubset({"title", "pinned", "context_entity", "context_id"}) or not data:
            raise DomainError(400, "Неверные поля диалога")
        fields = {}
        if "title" in data:
            fields["title"] = string(data["title"], "Название", 120, True)
        if "pinned" in data:
            fields["pinned"] = integer(data["pinned"], "Закрепление", 0, 1)
        # A removed source must not prevent renaming or clearing a conversation.
        if "context_entity" in data or "context_id" in data:
            fields["context_entity"], fields["context_id"] = context_fields(service, data, row)
        fields["updated_at"] = stamp()
        updated = service.con.execute(
            "UPDATE assistant_conversations SET " + ",".join(key + "=?" for key in fields)
            + " WHERE id=? AND workspace_id=? AND user_id=? RETURNING *",
            (*fields.values(), row["id"], service.wid, service.user["id"]),
        ).fetchone()
        if not updated:
            raise DomainError(404, "Диалог не найден")
        return 200, {"conversation": dict(updated)}
    if method == "DELETE":
        with transaction(service.con):
            active = service.con.execute(
                "SELECT id FROM assistant_jobs WHERE conversation_id=? AND workspace_id=? AND user_id=? AND status IN ('queued','running','retry') LIMIT 1",
                (row["id"], service.wid, service.user["id"]),
            ).fetchone()
            if active:
                raise DomainError(409, "Сначала отмените фоновую задачу этого диалога")
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


def _ensure_general_idle(service):
    active = service.con.execute(
        "SELECT id FROM assistant_jobs WHERE conversation_id IS NULL AND kind='chat' "
        "AND workspace_id=? AND user_id=? AND status IN ('queued','running','retry') LIMIT 1",
        (service.wid, service.user["id"]),
    ).fetchone()
    if active:
        raise DomainError(409, "Дождитесь завершения фоновой задачи общего диалога или отмените её")


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
    from backend.profile_memory import memory_items, profile

    personal = [item for item in memory_items(service) if item['enabled'] and
                phrase in (item['title']+' '+item['content']).casefold()] if profile(service.con, service.user)['memory_enabled'] else []
    return {"items": ([
        {"id": item["id"], "title": item["title"], "scope": "personal",
         "excerpt": _SECRET.sub("[секрет скрыт]", item["content"][:1200])}
        for item in personal[:5]
    ] + [
        {"id": row["id"], "title": row["title"],
         "excerpt": _SECRET.sub("[секрет скрыт]", row["content"][:1600])}
        for row in rows
    ])[:5]}
