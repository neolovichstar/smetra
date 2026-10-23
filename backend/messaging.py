"""Private chats, workspace conversations, user directory and ticketed AI support."""
import json
import re
import secrets
import time
import uuid
from urllib.parse import unquote

from backend.business import DomainError, packed, transaction

try:
    from backend.support_ai import answer_result as support_answer_result
except ModuleNotFoundError:
    from support_ai import answer_result as support_answer_result


COMMUNITY = (
    ("community_general", "Общий чат", "general"),
    ("community_finishing", "Отделка", "finishing"),
    ("community_electrical", "Электрика", "electrical"),
    ("community_plumbing", "Сантехника", "plumbing"),
    ("community_subcontract", "Биржа субподряда", "subcontract"),
)


def _now():
    return int(time.time())


def _now_ms():
    return time.time_ns() // 1_000_000


def _id():
    return str(uuid.uuid4())


def _topic():
    return secrets.token_urlsafe(32)


def _api_error(status, message):
    # Use the shared domain error type so the active request handler catches
    # the same exception even when loaded by a test runner or serverless shim.
    return DomainError(status, message)


def _body(handler):
    value = handler.body()
    if not isinstance(value, dict):
        raise _api_error(400, "Некорректные данные")
    return value


def _clean(value, field, maximum, required=True):
    if not isinstance(value, str):
        raise _api_error(400, f"Поле «{field}» заполнено неверно")
    value = value.replace("\x00", "").strip()
    if (required and not value) or len(value) > maximum:
        raise _api_error(400, f"Поле «{field}» заполнено неверно")
    return value


def _public_user(row):
    return {
        "id": row["user_id"],
        "public_id": row["public_id"],
        "name": row["display_name"],
        "profession": row["profession"] or "",
        "company": row["company"] or "",
    }


def _ticket(con, ticket_id, user_id=None):
    query = (
        "SELECT s.*,u.name AS user_name,u.email AS user_email,u.public_id,c.realtime_topic "
        "FROM support s JOIN users u ON u.id=s.user_id LEFT JOIN conversations c ON c.id=s.conversation_id WHERE s.id=?"
    )
    params = [ticket_id]
    if user_id is not None:
        query += " AND s.user_id=?"
        params.append(user_id)
    row = con.execute(query, tuple(params)).fetchone()
    if not row:
        raise _api_error(404, "Обращение не найдено")
    return row


def _ticket_view(row):
    return {
        "id": row["id"],
        "subject": row["subject"],
        "status": row["status"],
        "priority": row["priority"],
        "needs_human": bool(row["needs_human"]),
        "ai_state": row["ai_state"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "conversation_id": row["conversation_id"],
        "realtime_topic": row["realtime_topic"] if row["realtime_topic"] else None,
        "user_id": row["user_id"],
        "user_name": row["user_name"],
        "user_email": row["user_email"],
        "public_id": row["public_id"],
    }


def _messages(con, conversation_id, limit=100):
    rows = con.execute(
        "SELECT m.id,m.conversation_id,m.sender_id,m.sender_role,m.body,m.payload,m.created_at,m.edited_at,"
        "u.name AS sender_name,u.public_id AS sender_public_id "
        "FROM messages m LEFT JOIN users u ON u.id=m.sender_id "
        "WHERE m.conversation_id=? AND m.deleted_at IS NULL "
        "ORDER BY m.created_at DESC,m.id DESC LIMIT ?",
        (conversation_id, max(1, min(100, limit))),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "sender_id": row["sender_id"],
            "sender_role": row["sender_role"],
            "sender_name": row["sender_name"] or {"ai": "Помощник Сметры", "system": "Сметра", "admin": "Поддержка"}.get(row["sender_role"], "Пользователь"),
            "sender_public_id": row["sender_public_id"],
            "body": row["body"],
            "payload": row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"] or "{}"),
            "created_at": row["created_at"],
            "edited_at": row["edited_at"],
        }
        for row in reversed(rows)
    ]


def _insert_message(con, conversation_id, sender_id, role, body, payload=None):
    # Millisecond epoch plus a per-conversation monotonic fence keeps bursts ordered.
    latest = con.execute(
        "SELECT coalesce(max(created_at),0) FROM messages WHERE conversation_id=?",
        (conversation_id,),
    ).fetchone()[0]
    message_time = max(_now_ms(), int(latest or 0) + 1)
    con.execute(
        "INSERT INTO messages(id,conversation_id,sender_id,sender_role,body,payload,created_at) VALUES(?,?,?,?,?,?,?)",
        (_id(), conversation_id, sender_id, role, body, packed(payload or {}), message_time),
    )
    con.execute("UPDATE conversations SET updated_at=? WHERE id=?", (_now(), conversation_id))
    return message_time


def _add_member(con, conversation_id, user_id, role="member"):
    moment = _now()
    con.execute(
        "INSERT INTO conversation_members(conversation_id,user_id,role,joined_at,last_read_at) "
        "VALUES(?,?,?,?,0) ON CONFLICT(conversation_id,user_id) DO NOTHING",
        (conversation_id, user_id, role, moment),
    )


def _is_member(con, conversation_id, user_id):
    return con.execute(
        "SELECT role FROM conversation_members WHERE conversation_id=? AND user_id=?",
        (conversation_id, user_id),
    ).fetchone()


def ensure_quote_conversation(con, quote, user, workspace_id):
    """Create one private chat for the immutable published estimate version."""
    if not quote or not workspace_id:
        return None
    quote = dict(quote)
    if not quote.get("id"):
        return None
    existing = con.execute(
        "SELECT id FROM conversations WHERE kind='quote' AND quote_id=?",
        (quote["id"],),
    ).fetchone()
    if existing:
        return existing["id"]
    moment = _now()
    conversation_id = _id()
    title = _clean(str(quote.get("title") or "Обсуждение сметы"), "Тема", 180)
    con.execute(
        "INSERT INTO conversations(id,kind,title,workspace_id,quote_id,created_by,status,created_at,updated_at,realtime_topic) "
        "VALUES(?,?,?,?,?,?,'active',?,?,?)",
        (conversation_id, "quote", title, workspace_id, quote["id"], user["id"], moment, moment, _topic()),
    )
    _add_member(con, conversation_id, user["id"], "owner")
    # If the quote names an existing account's email, invite that account into this estimate-only chat.
    client_email = ""
    if quote.get("client_id"):
        client = con.execute(
            "SELECT email FROM clients WHERE id=? AND workspace_id=?",
            (quote["client_id"], workspace_id),
        ).fetchone()
        if client:
            client_email = str(client["email"] or "").strip().lower()
    if client_email:
        customer = con.execute(
            "SELECT u.id FROM users u WHERE lower(u.email)=? AND u.blocked=0 AND u.deleted_at IS NULL",
            (client_email,),
        ).fetchone()
        if customer and customer["id"] != user["id"]:
            _add_member(con, conversation_id, customer["id"], "customer")
    return conversation_id


def _ensure_community(con):
    moment = _now()
    for room_id, title, category in COMMUNITY:
        con.execute(
            "INSERT INTO conversations(id,kind,title,category,created_by,status,created_at,updated_at,realtime_topic) "
            "VALUES(?,'community',?,?,NULL,'active',?,?,?) ON CONFLICT(id) DO NOTHING",
            (room_id, title, category, moment, moment, _topic()),
        )


def _conversations_for_user(con, user_id):
    rows = con.execute(
        "SELECT c.id,c.kind,c.title,c.workspace_id,c.quote_id,c.object_id,c.category,c.status,c.created_at,c.updated_at,c.realtime_topic,"
        "cm.role AS member_role,cm.last_read_at,"
        "(SELECT m.body FROM messages m WHERE m.conversation_id=c.id AND m.deleted_at IS NULL ORDER BY m.created_at DESC,m.id DESC LIMIT 1) AS last_message,"
        "(SELECT m.created_at FROM messages m WHERE m.conversation_id=c.id AND m.deleted_at IS NULL ORDER BY m.created_at DESC,m.id DESC LIMIT 1) AS last_message_at,"
        "(SELECT count(*) FROM messages m WHERE m.conversation_id=c.id AND m.deleted_at IS NULL AND m.created_at>cm.last_read_at "
        "AND (m.sender_id IS NULL OR m.sender_id<>?)) AS unread_count "
        "FROM conversations c JOIN conversation_members cm ON cm.conversation_id=c.id "
        "WHERE cm.user_id=? AND c.status='active' ORDER BY c.updated_at DESC,c.id DESC LIMIT 80",
        (user_id, user_id),
    ).fetchall()
    result = []
    for row in rows:
        value = dict(row)
        if value["kind"] == "direct":
            other = con.execute(
                "SELECT u.name,u.public_id FROM conversation_members cm JOIN users u ON u.id=cm.user_id "
                "WHERE cm.conversation_id=? AND cm.user_id<>? LIMIT 1",
                (row["id"], user_id),
            ).fetchone()
            value["title"] = other["name"] if other else "Личный чат"
            value["other_public_id"] = other["public_id"] if other else None
        if value["kind"] == "quote" and value["quote_id"]:
            quote = con.execute("SELECT title,client,amount_kopecks,currency,approval_state,published_version FROM quotes WHERE id=?", (value["quote_id"],)).fetchone()
            if quote:
                value["quote"] = dict(quote)
        return_value = value
        result.append(return_value)
    return result


def _active_team(con, user_id, workspace_id):
    return con.execute(
        "SELECT w.id,w.name,w.seat_limit,w.plan,w.subscription_status,w.entitlement_until,m.role "
        "FROM workspaces w JOIN workspace_members m ON m.workspace_id=w.id "
        "WHERE w.id=? AND m.user_id=? AND w.plan='pro_team' AND w.subscription_status='active' "
        "AND w.entitlement_until>? LIMIT 1",
        (workspace_id, user_id, _now()),
    ).fetchone()


def _ensure_workspace_chat(con, user, workspace_id, object_id):
    workspace = _active_team(con, user["id"], workspace_id)
    if not workspace:
        raise _api_error(403, "Чаты объектов доступны при активном тарифе TEAM")
    project = con.execute(
        "SELECT id,name FROM projects WHERE id=? AND workspace_id=?",
        (object_id, workspace_id),
    ).fetchone()
    if not project:
        raise _api_error(404, "Объект не найден в этом рабочем пространстве")
    existing = con.execute(
        "SELECT id FROM conversations WHERE kind='workspace' AND workspace_id=? AND object_id=?",
        (workspace_id, object_id),
    ).fetchone()
    if existing:
        conversation_id = existing["id"]
    else:
        moment = _now()
        conversation_id = _id()
        con.execute(
            "INSERT INTO conversations(id,kind,title,workspace_id,object_id,created_by,status,created_at,updated_at,realtime_topic) "
            "VALUES(?,'workspace',?,?,?,?, 'active',?,?,?)",
            (conversation_id, project["name"], workspace_id, object_id, user["id"], moment, moment, _topic()),
        )
    members = con.execute(
        "SELECT user_id,role FROM workspace_members WHERE workspace_id=?",
        (workspace_id,),
    ).fetchall()
    if len(members) > min(5, int(workspace["seat_limit"] or 5)):
        raise _api_error(409, "В TEAM превышено число участников; проверьте список команды")
    for member in members:
        member_role = "owner" if member["role"] == "owner" else "member"
        _add_member(con, conversation_id, member["user_id"], member_role)
    return conversation_id


def _messages_for_conversation(con, user, conversation_id, method, handler):
    membership = _is_member(con, conversation_id, user["id"])
    if not membership:
        raise _api_error(404, "Переписка не найдена")
    row = con.execute(
        "SELECT * FROM conversations WHERE id=? AND kind<>'support'",
        (conversation_id,),
    ).fetchone()
    if not row:
        raise _api_error(404, "Переписка не найдена")
    if method == "GET":
        moment = _now_ms()
        con.execute(
            "UPDATE conversation_members SET last_read_at=? WHERE conversation_id=? AND user_id=?",
            (moment, conversation_id, user["id"]),
        )
        return {"conversation": dict(row), "messages": _messages(con, conversation_id)}
    if method != "POST":
        raise _api_error(405, "Метод не поддерживается")
    handler.throttle("chat-message:" + user["id"], 80, 60)
    data = _body(handler)
    body = _clean(data.get("message"), "Сообщение", 4000)
    _insert_message(con, conversation_id, user["id"], "user", body, {})
    if row["workspace_id"]:
        try:
            from backend import revenue
            revenue.record(con, user["id"], "chat_message_sent", key="chat:" + conversation_id + ":" + user["id"] + ":" + str(_now() // 60))
        except Exception:
            pass
    return {"ok": True, "messages": _messages(con, conversation_id)}


def _support_messages(con, ticket):
    return _messages(con, ticket["conversation_id"], 100)


def _support_context(con, user):
    plan = user["plan"] if int(user["entitlement_until"] or 0) > _now() else "free"
    quote_count = con.execute("SELECT count(*) FROM quotes WHERE user_id=?", (user["id"],)).fetchone()[0]
    role = con.execute(
        "SELECT role FROM workspace_members WHERE user_id=? ORDER BY workspace_id LIMIT 1",
        (user["id"],),
    ).fetchone()
    return {"plan": plan, "quote_count": int(quote_count or 0), "workspace_role": role["role"] if role else ""}


def _make_support_ticket(con, user, data):
    message = _clean(data.get("message"), "Сообщение", 2000)
    subject = data.get("subject")
    if not subject:
        subject = message.split(":", 1)[0] if ":" in message and len(message.split(":", 1)[0]) < 80 else "Вопрос в поддержку"
    subject = _clean(subject, "Тема обращения", 100)
    moment = _now()
    ticket_id, conversation_id = _id(), _id()
    con.execute(
        "INSERT INTO conversations(id,kind,title,created_by,status,created_at,updated_at,realtime_topic) VALUES(?,'support',?,?,'active',?,?,?)",
        (conversation_id, subject, user["id"], moment, moment, _topic()),
    )
    con.execute(
        "INSERT INTO support(id,user_id,message,status,created_at,subject,needs_human,conversation_id,updated_at,priority,ai_state) "
        "VALUES(?,?,?,'open',?,?,0,?,?,'normal','active')",
        (ticket_id, user["id"], message, moment, subject, conversation_id, moment),
    )
    _add_member(con, conversation_id, user["id"], "owner")
    _insert_message(con, conversation_id, user["id"], "user", message, {})
    return _ticket(con, ticket_id, user["id"])


def _support_user_reply(con, user, ticket_id, message):
    ticket = _ticket(con, ticket_id, user["id"])
    body = _clean(message, "Сообщение", 4000)
    moment = _now()
    con.execute(
        "UPDATE support SET status='open',updated_at=? WHERE id=? AND user_id=?",
        (moment, ticket_id, user["id"]),
    )
    _insert_message(con, ticket["conversation_id"], user["id"], "user", body, {})
    ticket = _ticket(con, ticket_id, user["id"])
    if ticket["needs_human"]:
        return ticket, _support_messages(con, ticket)
    recent = _messages(con, ticket["conversation_id"], 12)
    outcome = support_answer_result(recent, _support_context(con, user))
    _insert_message(con, ticket["conversation_id"], None, "ai", outcome["text"], {})
    if outcome["needs_human"]:
        con.execute(
            "UPDATE support SET needs_human=1,status='open',ai_state='human',priority=?,updated_at=? WHERE id=?",
            (outcome["priority"], _now(), ticket_id),
        )
        _insert_message(
            con, ticket["conversation_id"], None, "system",
            "Помощник передал обращение сотруднику, потому что вопрос требует проверки человеком.",
            {},
        )
    else:
        con.execute(
            "UPDATE support SET updated_at=?,ai_state='active' WHERE id=?",
            (_now(), ticket_id),
        )
    ticket = _ticket(con, ticket_id, user["id"])
    return ticket, _support_messages(con, ticket)


def _escalate(con, user, ticket_id):
    ticket = _ticket(con, ticket_id, user["id"])
    if not ticket["needs_human"]:
        moment = _now()
        con.execute(
            "UPDATE support SET needs_human=1,status='open',ai_state='human',updated_at=? WHERE id=?",
            (moment, ticket_id),
        )
        _insert_message(
            con, ticket["conversation_id"], None, "system",
            "Пользователь попросил подключить сотрудника поддержки.", {},
        )
        try:
            from backend.app import audit, event
            audit(con, user["id"], "support.human_requested", ticket_id, ticket["subject"])
            event(con, user["id"], "support_human_requested")
        except Exception:
            pass
    ticket = _ticket(con, ticket_id, user["id"])
    return ticket, _support_messages(con, ticket)


def handle(handler, con, user, method, path, query):
    user_id = user["id"]
    current = _now()

    if path == "/api/people" and method == "GET":
        handler.throttle("people-search:" + user_id, 60, 60)
        term = str(query.get("q", [""])[0] or "").strip()
        if len(term) < 2:
            return {"items": []}
        term = _clean(term, "Поиск", 80)
        rows = con.execute(
            "SELECT d.public_id,d.user_id,d.display_name,d.profession,d.company FROM user_directory d "
            "JOIN users u ON u.id=d.user_id WHERE (d.visible=1 OR upper(d.public_id)=upper(?)) AND u.blocked=0 AND u.deleted_at IS NULL "
            "AND d.user_id<>? AND (instr(lower(d.public_id),lower(?))>0 OR instr(lower(d.display_name),lower(?))>0 "
            "OR instr(lower(d.profession),lower(?))>0 OR instr(lower(d.company),lower(?))>0) "
            "ORDER BY CASE WHEN upper(d.public_id)=upper(?) THEN 0 ELSE 1 END,lower(d.display_name) LIMIT 20",
            (term, user_id, term, term, term, term, term),
        ).fetchall()
        return {"items": [_public_user(row) for row in rows]}

    if path == "/api/community" and method == "GET":
        _ensure_community(con)
        rows = con.execute(
            "SELECT c.id,c.title,c.category,c.created_at,c.updated_at,"
            "(SELECT count(*) FROM conversation_members cm WHERE cm.conversation_id=c.id) AS members,"
            "EXISTS(SELECT 1 FROM conversation_members cm WHERE cm.conversation_id=c.id AND cm.user_id=?) AS joined "
            "FROM conversations c WHERE c.kind='community' AND c.status='active' ORDER BY c.category",
            (user_id,),
        ).fetchall()
        return {"items": [dict(row) for row in rows]}

    if path.startswith("/api/community/") and path.endswith("/join") and method == "POST":
        room_id = unquote(path.removeprefix("/api/community/").removesuffix("/join").strip("/"))
        _ensure_community(con)
        room = con.execute("SELECT id FROM conversations WHERE id=? AND kind='community'", (room_id,)).fetchone()
        if not room:
            raise _api_error(404, "Группа не найдена")
        _add_member(con, room_id, user_id, "member")
        return {"ok": True, "conversation_id": room_id, "messages": _messages(con, room_id, 80)}

    if path == "/api/conversations" and method == "GET":
        _ensure_community(con)
        return {"items": _conversations_for_user(con, user_id), "community": []}

    if path == "/api/conversations" and method == "POST":
        data = _body(handler)
        kind = data.get("kind", "direct")
        if kind == "direct":
            public_id = _clean(data.get("target_public_id", data.get("target_id", "")), "ID собеседника", 20).upper()
            target = con.execute(
                "SELECT u.id,u.name,u.public_id FROM users u JOIN user_directory d ON d.user_id=u.id "
                "WHERE upper(u.public_id)=? AND d.visible=1 AND u.blocked=0 AND u.deleted_at IS NULL",
                (public_id,),
            ).fetchone()
            if not target:
                raise _api_error(404, "Пользователь по этому ID не найден")
            if target["id"] == user_id:
                raise _api_error(400, "Нельзя создать личный чат с самим собой")
            low, high = sorted((user_id, target["id"]))
            existing = con.execute(
                "SELECT conversation_id FROM direct_chat_pairs WHERE user_low=? AND user_high=?",
                (low, high),
            ).fetchone()
            if existing:
                return {"conversation_id": existing["conversation_id"], "created": False}
            moment, conversation_id = current, _id()
            con.execute(
                "INSERT INTO conversations(id,kind,title,created_by,status,created_at,updated_at,realtime_topic) VALUES(?,'direct',?,?, 'active',?,?,?)",
                (conversation_id, target["name"], user_id, moment, moment, _topic()),
            )
            _add_member(con, conversation_id, user_id, "owner")
            _add_member(con, conversation_id, target["id"], "member")
            con.execute(
                "INSERT INTO direct_chat_pairs(user_low,user_high,conversation_id,created_at) VALUES(?,?,?,?) "
                "ON CONFLICT(user_low,user_high) DO NOTHING",
                (low, high, conversation_id, moment),
            )
            pair = con.execute(
                "SELECT conversation_id FROM direct_chat_pairs WHERE user_low=? AND user_high=?",
                (low, high),
            ).fetchone()
            return {"conversation_id": pair["conversation_id"], "created": pair["conversation_id"] == conversation_id}

        if kind == "workspace":
            workspace_id = _clean(data.get("workspace_id") or handler.headers.get("X-Workspace-ID", ""), "Рабочее пространство", 100)
            object_id = _clean(data.get("object_id", ""), "Объект", 100)
            conversation_id = _ensure_workspace_chat(con, user, workspace_id, object_id)
            return {"conversation_id": conversation_id, "created": True}

        if kind == "quote":
            quote_id = _clean(data.get("quote_id", ""), "Смета", 100)
            quote = con.execute(
                "SELECT * FROM quotes WHERE id=? AND workspace_id=?",
                (quote_id, data.get("workspace_id") or handler.headers.get("X-Workspace-ID", "")),
            ).fetchone()
            if not quote:
                raise _api_error(404, "Смета не найдена в выбранном рабочем пространстве")
            workspace_id = quote["workspace_id"]
            if not con.execute("SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?", (workspace_id, user_id)).fetchone():
                raise _api_error(404, "Смета не найдена")
            conversation_id = ensure_quote_conversation(con, dict(quote), user, workspace_id)
            return {"conversation_id": conversation_id, "created": True}
        raise _api_error(400, "Неизвестный тип переписки")

    if path.startswith("/api/conversations/") and path.endswith("/messages"):
        conversation_id = unquote(path.removeprefix("/api/conversations/").removesuffix("/messages").strip("/"))
        result = _messages_for_conversation(con, user, conversation_id, method, handler)
        return result

    if path == "/api/support":
        if method == "GET":
            rows = con.execute(
                "SELECT s.id,s.subject,s.status,s.priority,s.needs_human,s.ai_state,s.created_at,s.updated_at,s.conversation_id,"
                "(SELECT m.body FROM messages m WHERE m.conversation_id=s.conversation_id ORDER BY m.created_at DESC,m.id DESC LIMIT 1) AS last_message "
                "FROM support s WHERE s.user_id=? ORDER BY s.updated_at DESC,s.created_at DESC LIMIT 50",
                (user_id,),
            ).fetchall()
            return {"items": [dict(row) for row in rows]}
        if method == "POST":
            handler.throttle("support:" + user_id, 10, 3600)
            data = _body(handler)
            with transaction(con):
                ticket = _make_support_ticket(con, user, data)
                recent = _messages(con, ticket["conversation_id"], 12)
                outcome = support_answer_result(recent, _support_context(con, user))
                _insert_message(con, ticket["conversation_id"], None, "ai", outcome["text"], {})
                if outcome["needs_human"]:
                    con.execute(
                        "UPDATE support SET needs_human=1,status='open',ai_state='human',priority=?,updated_at=? WHERE id=?",
                        (outcome["priority"], _now(), ticket["id"]),
                    )
                    _insert_message(
                        con, ticket["conversation_id"], None, "system",
                        "Помощник передал обращение сотруднику, потому что вопрос требует проверки человеком.",
                        {},
                    )
                else:
                    con.execute("UPDATE support SET updated_at=?,ai_state='active' WHERE id=?", (_now(), ticket["id"]))
                ticket = _ticket(con, ticket["id"], user_id)
            return {"ticket": _ticket_view(ticket), "messages": _support_messages(con, ticket)}

    support_match = re.fullmatch(r"/api/support/([^/]+)/messages", path)
    if support_match:
        ticket_id = unquote(support_match.group(1))
        if method == "GET":
            ticket = _ticket(con, ticket_id, user_id)
            con.execute(
                "UPDATE conversation_members SET last_read_at=? WHERE conversation_id=? AND user_id=?",
                (_now_ms(), ticket["conversation_id"], user_id),
            )
            return {"ticket": _ticket_view(ticket), "messages": _support_messages(con, ticket)}
        if method == "POST":
            handler.throttle("support-message:" + user_id, 30, 60)
            body = _clean(_body(handler).get("message"), "Сообщение", 4000)
            with transaction(con):
                ticket, messages = _support_user_reply(con, user, ticket_id, body)
            return {"ticket": _ticket_view(ticket), "messages": messages}

    escalate_match = re.fullmatch(r"/api/support/([^/]+)/escalate", path)
    if escalate_match and method == "POST":
        with transaction(con):
            ticket, messages = _escalate(con, user, unquote(escalate_match.group(1)))
        return {"ticket": _ticket_view(ticket), "messages": messages}

    admin_match = re.fullmatch(r"/api/admin/support/([^/]+)/messages", path)
    if admin_match:
        if user["role"] != "admin":
            raise _api_error(403, "Доступ только сотрудникам поддержки")
        ticket_id = unquote(admin_match.group(1))
        ticket = _ticket(con, ticket_id)
        _add_member(con, ticket["conversation_id"], user_id, "admin")
        if method == "GET":
            con.execute(
                "UPDATE conversation_members SET last_read_at=? WHERE conversation_id=? AND user_id=?",
                (_now_ms(), ticket["conversation_id"], user_id),
            )
            return {"ticket": _ticket_view(ticket), "messages": _support_messages(con, ticket)}
        if method == "POST":
            handler.throttle("admin-support-reply:" + user_id, 120, 60)
            message = _clean(_body(handler).get("message"), "Ответ", 4000)
            with transaction(con):
                _add_member(con, ticket["conversation_id"], user_id, "admin")
                _insert_message(con, ticket["conversation_id"], user_id, "admin", message, {})
                previous_state = ticket["ai_state"]
                con.execute(
                    "UPDATE support SET assigned_admin_id=?,status='open',ai_state='human',updated_at=? WHERE id=?",
                    (user_id, _now(), ticket_id),
                )
                if previous_state != "human":
                    _insert_message(con, ticket["conversation_id"], None, "system", "К переписке подключился сотрудник поддержки.", {})
                ticket = _ticket(con, ticket_id)
                return {"ticket": _ticket_view(ticket), "messages": _support_messages(con, ticket)}
    admin_conversation_match = re.fullmatch(r"/api/admin/conversations/([^/]+)/messages", path)
    if admin_conversation_match:
        if user["role"] != "admin":
            raise _api_error(403, "Доступ только администраторам")
        conversation_id = unquote(admin_conversation_match.group(1))
        conversation = con.execute(
            "SELECT id,kind,title,workspace_id,quote_id,object_id,category,status,created_by,created_at,updated_at "
            "FROM conversations WHERE id=? AND kind<>'support'",
            (conversation_id,),
        ).fetchone()
        if not conversation:
            raise _api_error(404, "Переписка не найдена")
        if method != "GET":
            raise _api_error(405, "В административном просмотре переписка доступна только для чтения")
        participants = con.execute(
            "SELECT cm.user_id,cm.role,cm.joined_at,COALESCE(u.public_id,'') AS public_id,"
            "COALESCE(u.name,'Удалённый пользователь') AS name "
            "FROM conversation_members cm LEFT JOIN users u ON u.id=cm.user_id "
            "WHERE cm.conversation_id=? ORDER BY cm.joined_at,cm.user_id",
            (conversation_id,),
        ).fetchall()
        try:
            from backend.app import audit
            audit(con, user["id"], "admin.conversation.read", conversation_id, str(conversation["kind"]))
        except Exception:
            pass
        return {
            "conversation": dict(conversation),
            "participants": [dict(row) for row in participants],
            "messages": _messages(con, conversation_id, 100),
            "read_only": True,
        }

    raise _api_error(404, "Не найдено")
