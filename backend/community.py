"""Private messaging, object/community conversations, and AI-first support."""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from backend.app import ORIGIN, audit, now, uid, yookassa_mode
from backend.business import DomainError as ApiError

# PostgreSQL stores all application tables in a private schema. Registering the
# extra names lets the existing parameterized SQL adapter apply its schema safely.
try:
    from backend import postgres as _postgres
    _postgres.TABLES = _postgres.TABLES | frozenset(
        {"chat_conversations", "chat_members", "chat_messages", "app_presence", "billing_subscriptions"}
    )
except (ImportError, AttributeError):
    pass

COMMUNITIES = {
    "general": "Общий чат",
    "finishing": "Отделка",
    "electrical": "Электрика",
    "plumbing": "Сантехника",
    "subcontract": "Биржа субподряда",
}
HUMAN_PATTERN = re.compile(
    r"\b(оператор\w*|сотрудник\w*|человек\w*|менеджер\w*|специалист\w*\s+поддержки|живой\s+человек)\b|"
    r"позови(те)?\s+(кого-то|сотрудника|человека)|"
    r"соедини(те)?\s+(с|меня)|"
    r"нужен\s+(человек|сотрудник|оператор)|"
    r"позвать\s+(сотрудника|оператора|человека)",
    re.IGNORECASE,
)
PUBLIC_ID_PATTERN = re.compile(r"^(?:SM-?)?([A-F0-9]{32})$", re.IGNORECASE)


def make_public_id(user_id):
    """A stable, non-secret public lookup ID derived from the account UUID."""
    compact = str(user_id or "").replace("-", "").upper()
    return "SM-" + compact if re.fullmatch(r"[A-F0-9]{32}", compact) else ""


def normalize_public_id(value):
    candidate = str(value or "").strip().upper().replace(" ", "")
    match = PUBLIC_ID_PATTERN.fullmatch(candidate)
    return match.group(1) if match else None


def wants_human(text):
    return bool(HUMAN_PATTERN.search(str(text or "")))


def handles(path):
    # Do not shadow unrelated legacy profile/support endpoints. This API only
    # owns the exact routes below; every other route falls through to app.py.
    exact = {
        "/api/profile/id",
        "/api/profile/directory",
        "/api/profile/chats",
        "/api/profile/quote-chats",
        "/api/profile/object-chats",
        "/api/profile/communities",
        "/api/profile/presence",
        "/api/support",
        "/api/support/threads",
    }
    return (
        path in exact
        or bool(re.fullmatch(r"/api/profile/chats/[A-Za-z0-9_-]+/messages", path))
        or bool(re.fullmatch(r"/api/support/threads/[A-Za-z0-9_-]+(?:/(?:messages|handoff))?", path))
        or path.startswith("/api/admin/communication/")
    )


def ensure_sqlite_schema(con):
    if getattr(con, "is_postgres", False):
        return
    con.executescript("""
      CREATE TABLE IF NOT EXISTS chat_conversations (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK(kind IN ('direct','object','estimate','support','community')),
        subject TEXT NOT NULL DEFAULT '',
        workspace_id TEXT NOT NULL DEFAULT '',
        project_id TEXT NOT NULL DEFAULT '',
        quote_id TEXT NOT NULL DEFAULT '',
        category TEXT NOT NULL DEFAULT '',
        community_key TEXT UNIQUE,
        direct_key TEXT UNIQUE,
        status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','waiting','closed')),
        needs_human INTEGER NOT NULL DEFAULT 0 CHECK(needs_human IN (0,1)),
        human_reason TEXT NOT NULL DEFAULT '',
        assigned_admin_id TEXT REFERENCES users(id) ON DELETE SET NULL,
        created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS chat_members (
        conversation_id TEXT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL DEFAULT 'member',
        joined_at INTEGER NOT NULL,
        last_read_at INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (conversation_id, user_id)
      );
      CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
        sender_id TEXT REFERENCES users(id) ON DELETE SET NULL,
        sender_type TEXT NOT NULL CHECK(sender_type IN ('user','assistant','admin','system')),
        body TEXT NOT NULL,
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS app_presence (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        last_seen_at INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_app_presence_seen ON app_presence(last_seen_at DESC);
      CREATE INDEX IF NOT EXISTS idx_chat_member_user ON chat_members(user_id, joined_at DESC);
      CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation ON chat_messages(conversation_id, created_at, id);
      CREATE INDEX IF NOT EXISTS idx_chat_support_queue ON chat_conversations(kind, needs_human, status, updated_at DESC);
      CREATE TABLE IF NOT EXISTS billing_subscriptions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT '',
        workspace_id TEXT NOT NULL DEFAULT '',
        product_code TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending',
        is_test INTEGER NOT NULL DEFAULT 0,
        current_period_end INTEGER NOT NULL DEFAULT 0
      );
    """)
    # The lightweight SQLite fixture predates paid workspace subscriptions.
    # Add only missing optional columns so local/dev paths fail closed, not 500.
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspaces'").fetchone():
        workspace_columns = {row["name"] for row in con.execute("PRAGMA table_info(workspaces)")}
        additions = {
            "plan": "TEXT NOT NULL DEFAULT 'free'",
            "subscription_status": "TEXT NOT NULL DEFAULT 'inactive'",
            "entitlement_until": "INTEGER NOT NULL DEFAULT 0",
            "seat_limit": "INTEGER NOT NULL DEFAULT 1",
        }
        for column, definition in additions.items():
            if column not in workspace_columns:
                con.execute(f"ALTER TABLE workspaces ADD COLUMN {column} {definition}")


def _table(con, name):
    # The PostgreSQL adapter qualifies names registered in its TABLES allow-list.
    return name


def _auth(handler, con, admin=False):
    return handler.auth(con, admin=admin)


def _text(value, limit, required=False):
    result = str(value or "").strip()
    if required and not result:
        raise ApiError(400, "Заполните обязательное поле")
    if len(result) > limit:
        raise ApiError(400, "Слишком длинный текст")
    return result


def _json(value):
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _member(con, conversation_id, user_id):
    return con.execute(
        "SELECT role,last_read_at FROM chat_members WHERE conversation_id=? AND user_id=?",
        (conversation_id, user_id),
    ).fetchone()


def _add_member(con, conversation_id, user_id, role="member"):
    con.execute(
        "INSERT INTO chat_members(conversation_id,user_id,role,joined_at,last_read_at) "
        "VALUES(?,?,?,?,0) ON CONFLICT(conversation_id,user_id) DO NOTHING",
        (conversation_id, user_id, role, now()),
    )


def _new_conversation(con, kind, subject, created_by, workspace_id="", project_id="",
                      quote_id="", category="", community_key=None, direct_key=None):
    moment = now()
    conversation_id = uid()
    con.execute(
        "INSERT INTO chat_conversations(id,kind,subject,workspace_id,project_id,quote_id,"
        "category,community_key,direct_key,status,needs_human,human_reason,"
        "assigned_admin_id,created_by,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,'open',0,'',NULL,?,?,?) ON CONFLICT DO NOTHING",
        (conversation_id, kind, subject, workspace_id, project_id, quote_id,
         category, community_key, direct_key, created_by, moment, moment),
    )
    if community_key:
        row = con.execute(
            "SELECT id FROM chat_conversations WHERE community_key=?", (community_key,)
        ).fetchone()
    elif direct_key:
        row = con.execute(
            "SELECT id FROM chat_conversations WHERE direct_key=?", (direct_key,)
        ).fetchone()
    else:
        row = con.execute(
            "SELECT id FROM chat_conversations WHERE id=?", (conversation_id,)
        ).fetchone()
    return row["id"] if row else conversation_id


def _add_message(con, conversation_id, sender_id, sender_type, body, metadata=None):
    message_id = uid()
    moment = now()
    con.execute(
        "INSERT INTO chat_messages(id,conversation_id,sender_id,sender_type,body,metadata,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (message_id, conversation_id, sender_id, sender_type, body,
         json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":")), moment),
    )
    con.execute(
        "UPDATE chat_conversations SET updated_at=? WHERE id=?",
        (moment, conversation_id),
    )
    return {"id": message_id, "sender_id": sender_id, "sender_type": sender_type,
            "body": body, "metadata": metadata or {}, "created_at": moment}


def _message_view(row):
    if not row:
        return None
    return {
        "id": row["id"], "sender_id": row["sender_id"],
        "sender_type": row["sender_type"], "body": row["body"],
        "metadata": _json(row["metadata"]), "created_at": row["created_at"],
        # Display name lets group chats label bubbles like a messenger.
        # Staff names stay private: only peer users are labelled by name.
        "sender_name": (row["sender_name"] if "sender_name" in row.keys()
                        and row["sender_type"] == "user" else None),
    }


def _conversation_view(row):
    return {
        "id": row["id"], "kind": row["kind"], "subject": row["subject"],
        "workspace_id": row["workspace_id"], "project_id": row["project_id"],
        "quote_id": row["quote_id"], "category": row["category"],
        "status": row["status"], "needs_human": bool(row["needs_human"]),
        "human_reason": row["human_reason"], "assigned_admin_id": row["assigned_admin_id"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "last_message": row["last_message"] or "",
        "last_message_at": row["last_message_at"] or row["updated_at"],
        "unread_count": int(row["unread_count"] or 0),
        "partner_name": row["partner_name"] or "",
        "partner_public_id": make_public_id(row["partner_id"]) if row["partner_id"] else "",
        "user_name": row["user_name"] or "",
        "user_email": row["user_email"] or "",
    }


def _list_conversations(con, user_id, kinds, include_user=False):
    placeholders = ",".join("?" for _ in kinds)
    rows = con.execute(
        "SELECT c.*, "
        "(SELECT m.body FROM chat_messages m WHERE m.conversation_id=c.id "
        " ORDER BY m.created_at DESC,CASE m.sender_type WHEN 'user' THEN 0 WHEN 'system' THEN 1 ELSE 2 END DESC,m.id DESC LIMIT 1) AS last_message, "
        "(SELECT m.created_at FROM chat_messages m WHERE m.conversation_id=c.id "
        " ORDER BY m.created_at DESC,CASE m.sender_type WHEN 'user' THEN 0 WHEN 'system' THEN 1 ELSE 2 END DESC,m.id DESC LIMIT 1) AS last_message_at, "
        "(SELECT COUNT(*) FROM chat_messages m JOIN chat_members mine "
        " ON mine.conversation_id=m.conversation_id AND mine.user_id=? "
        " WHERE m.conversation_id=c.id AND m.created_at>mine.last_read_at "
        " AND (m.sender_id IS NULL OR m.sender_id<>?)) AS unread_count, "
        "(SELECT u.id FROM chat_members cm JOIN users u ON u.id=cm.user_id "
        " WHERE cm.conversation_id=c.id AND cm.user_id<>? AND c.kind IN ('direct','estimate') "
        " ORDER BY cm.joined_at LIMIT 1) AS partner_id, "
        "(SELECT u.name FROM chat_members cm JOIN users u ON u.id=cm.user_id "
        " WHERE cm.conversation_id=c.id AND cm.user_id<>? AND c.kind IN ('direct','estimate') "
        " ORDER BY cm.joined_at LIMIT 1) AS partner_name, "
        "(SELECT u.name FROM users u WHERE u.id=c.created_by) AS user_name, "
        "(SELECT u.email FROM users u WHERE u.id=c.created_by) AS user_email "
        "FROM chat_conversations c JOIN chat_members mine ON mine.conversation_id=c.id "
        "WHERE mine.user_id=? AND c.kind IN (" + placeholders + ") "
        "ORDER BY c.updated_at DESC LIMIT 100",
        (user_id, user_id, user_id, user_id, user_id, *kinds),
    ).fetchall()
    return [_conversation_view(row) for row in rows]


def _messages(con, conversation_id, after=0, limit=100):
    limit = max(1, min(int(limit), 100))
    rows = con.execute(
        "SELECT m.id,m.sender_id,m.sender_type,m.body,m.metadata,m.created_at,u.name AS sender_name "
        "FROM chat_messages m LEFT JOIN users u ON u.id=m.sender_id "
        # Replies are often written in the same second as the question; keep
        # the question first so the thread reads in conversation order.
        "WHERE m.conversation_id=? AND m.created_at>? ORDER BY m.created_at,"
        "CASE m.sender_type WHEN 'user' THEN 0 WHEN 'system' THEN 1 ELSE 2 END,m.id LIMIT ?",
        (conversation_id, int(after or 0), limit),
    ).fetchall()
    return [_message_view(row) for row in rows]


def _community(con, user_id, category):
    if category not in COMMUNITIES:
        raise ApiError(404, "Категория сообщества не найдена")
    key = "community:" + category
    conversation_id = _new_conversation(
        con, "community", COMMUNITIES[category], user_id, category=category, community_key=key
    )
    _add_member(con, conversation_id, user_id, "member")
    return conversation_id


def _refresh_workspace_entitlement(con, workspace_id):
    """Read the catalog access fixed by verified payment callbacks; GET never rewrites a plan."""
    return con.execute(
        "SELECT id,owner_id,name,plan,subscription_status,entitlement_until,seat_limit "
        "FROM workspaces WHERE id=?", (workspace_id,)
    ).fetchone()


def _team_workspace(con, user_id, workspace_id):
    # Check membership before touching any workspace state, then refresh the
    # entitlement against authoritative subscription rows and re-read access.
    permitted = con.execute(
        "SELECT w.id FROM workspaces w LEFT JOIN workspace_members m "
        "ON m.workspace_id=w.id AND m.user_id=? "
        "WHERE w.id=? AND (m.user_id=? OR w.owner_id=?)",
        (user_id, workspace_id, user_id, user_id),
    ).fetchone()
    if not permitted:
        raise ApiError(404, "Рабочее пространство не найдено")
    row = _refresh_workspace_entitlement(con, workspace_id)
    active = row["subscription_status"] in ("active", "succeeded") and int(row["entitlement_until"] or 0) > now()
    team_plan = str(row["plan"] or "").lower() in (
        "team", "business", "company", "team_month", "team_year", "team_monthly", "team_annual",
        "team_company", "pro_team",
    )
    from backend.entitlements import PLAN_TIER
    team_plan = PLAN_TIER.get(str(row["plan"]), "starter") == "team"
    if not (active and team_plan):
        raise ApiError(403, "Чаты объектов доступны на тарифе TEAM / Компания")
    return row


def _support_user_context(con, user):
    """Build fresh, privacy-minimized diagnostics from this account's own records."""
    moment = now()
    plan = "PRO" if int(user["entitlement_until"] or 0) > moment else "Старт"
    quote_counts = {
        row["status"]: int(row["count"])
        for row in con.execute(
            "SELECT status,COUNT(*) AS count FROM quotes WHERE user_id=? GROUP BY status",
            (user["id"],),
        ).fetchall()
    }
    workspace_count = int(con.execute(
        "SELECT COUNT(*) FROM workspace_members WHERE user_id=?", (user["id"],)
    ).fetchone()[0] or 0)
    latest_payment = con.execute(
        "SELECT p.plan,p.amount_kopecks,p.status,p.activated_at,p.created_at,"
        "EXISTS(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded') AS refunded "
        "FROM payments p JOIN billing_intents b ON b.payment_id=p.id "
        "WHERE p.user_id=? AND b.is_test=0 ORDER BY p.created_at DESC LIMIT 1",
        (user["id"],),
    ).fetchone()
    payment = None
    if latest_payment:
        payment = {
            "plan": latest_payment["plan"],
            "amount_kopecks": int(latest_payment["amount_kopecks"] or 0),
            "status": latest_payment["status"],
            "activated": bool(latest_payment["activated_at"]),
            "refunded": bool(latest_payment["refunded"]),
            "created_at": int(latest_payment["created_at"] or 0),
        }
    active_workspaces = int(con.execute(
        "SELECT COUNT(*) FROM workspaces w LEFT JOIN workspace_members m "
        "ON m.workspace_id=w.id AND m.user_id=? "
        "WHERE (m.user_id=? OR w.owner_id=?) AND w.subscription_status IN ('active','succeeded') "
        "AND w.entitlement_until>?",
        (user["id"], user["id"], user["id"], moment),
    ).fetchone()[0] or 0)
    return {
        "account": {
            "display_name": user["name"],
            "email_verified": bool(user["email_verified_at"]),
            "plan": plan,
            "access_until": int(user["entitlement_until"] or 0) or None,
            "quote_count": sum(quote_counts.values()),
            "quote_status_counts": quote_counts,
            "workspace_memberships": workspace_count,
            "active_team_workspaces": active_workspaces,
            "last_real_payment": payment,
        },
        "runtime": {
            "api_request_reached_backend": True,
            "support_ai_provider_configured": bool(os.getenv("OPENROUTER_API_KEY", "").strip()),
            "support_ai_model": os.getenv("SUPPORT_AI_MODEL") or os.getenv("OPENROUTER_MODEL") or "openrouter/free",
            "checkout_mode": yookassa_mode(user),
            "push_provider_configured": bool(
                os.getenv("RUSTORE_PUSH_PROJECT_ID", "").strip()
                and os.getenv("RUSTORE_PUSH_SERVICE_TOKEN", "").strip()
            ),
            "redis_configured": bool(
                os.getenv("REDIS_ENABLED") == "1"
                and (os.getenv("REDIS_KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL"))
                and (os.getenv("REDIS_KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN"))
            ),
        },
    }


def send_quote_to_user(con, workspace_id, quote_id, owner_id, recipient_id, quote_title, public_url, published_version):
    """Create/update the quote-bound chat and post the published client link."""
    moment = now()
    quote = con.execute(
        "SELECT id,title,public_token,published_version,workspace_id,user_id,status "
        "FROM quotes WHERE id=? AND workspace_id=?",
        (quote_id, workspace_id),
    ).fetchone()
    if not quote or int(quote["published_version"] or 0) < 1:
        raise ApiError(409, "Смета ещё не опубликована. Обновите предложение и подтвердите отправку снова.")
    if quote["status"] in ("accepted", "completed"):
        raise ApiError(409, "Согласованную или завершённую смету нельзя отправлять как новое предложение.")
    recipient = con.execute(
        "SELECT id,name FROM users WHERE id=? AND id<>? AND deleted_at IS NULL AND blocked=0",
        (recipient_id, owner_id),
    ).fetchone()
    if not recipient:
        raise ApiError(404, "Получатель не найден или его аккаунт недоступен.")
    normalized_title = _text(quote["title"] or quote_title, 150, required=True)
    url = _text(public_url, 1000, required=True)
    direct_key = "estimate:" + quote_id + ":" + recipient_id
    existing = con.execute(
        "SELECT id FROM chat_conversations WHERE direct_key=?", (direct_key,)
    ).fetchone()
    conversation_id = _new_conversation(
        con, "estimate", "Смета: " + normalized_title, owner_id,
        workspace_id=workspace_id, quote_id=quote_id, direct_key=direct_key,
    )
    _add_member(con, conversation_id, owner_id, "owner")
    _add_member(con, conversation_id, recipient_id, "client")
    version = int(quote["published_version"] or published_version or 1)
    _add_message(
        con, conversation_id, owner_id, "user",
        "Смета «" + normalized_title + "» — версия " + str(version) + ". "
        "Откройте документ по ссылке: " + url,
        {
            "event": "estimate_shared_in_chat",
            "quote_id": quote_id,
            "quote_version": version,
            "public_url": url,
            "recipient_id": recipient_id,
            "sent_by": owner_id,
            "sent_at": moment,
        },
    )
    con.execute(
        "UPDATE chat_conversations SET subject=?,updated_at=? WHERE id=?",
        ("Смета: " + normalized_title, moment, conversation_id),
    )
    return {
        "conversation_id": conversation_id,
        "quote_id": quote_id,
        "quote_version": version,
        "recipient_id": recipient_id,
        "recipient_name": recipient["name"],
        "public_url": url,
        "reused_conversation": bool(existing),
    }


def _plan_lines():
    from backend.plan_catalog import public_catalog

    lines = []
    for item in public_catalog().values():
        month = int(item["monthly_kopecks"] or 0) // 100
        year = int(item["yearly_kopecks"] or 0) // 100
        price = "бесплатно" if not month else f"{month} ₽ в месяц" + (f" или {year} ₽ в год" if year else "")
        quotes = "до " + str(item["free_quotes"]) + " смет" if item.get("free_quotes") else "безлимитные сметы"
        lines.append(f"{item['name']}: {price}, {quotes}, мест: {item['seats']}")
    return "; ".join(lines)


SUPPORT_PRODUCT_GUIDE = (
    "Разделы кабинета (левое меню): «Сегодня» — сводка и быстрый черновик сметы по описанию; "
    "«Ассистент» — ИИ-чат, который готовит черновики и правки смет, но любые изменения применяются "
    "только после кнопки «Применить»; суммы и итоги всегда считает сервер Сметры, а не ИИ; "
    "«Сметы» — список, редактор позиций, версии, публикация клиентской ссылки, согласование клиентом "
    "без регистрации, PDF/Excel; «Проекты» — согласованные сметы в работе; «Клиенты» — контакты и история; "
    "«Объекты и замеры» — помещения, объёмы, журнал работ, закупки и допработы; «Инструменты смет» — "
    "смета на слух (голос), разбор PDF дизайн-проекта, геометрия помещения; «Полученные сметы» — "
    "предложения, присланные вам; «Лиды», «Задачи», «Календарь», «Платежи» — учёт заявок, дел и денег; "
    "«Расценки» — собственный прайс с импортом и экспортом CSV; «Калькуляторы» — бесплатный расчёт "
    "плитки, ламината, краски, штукатурки и бетона с переносом количества в новую смету; «Материалы» — "
    "облачные папки и мониторинг цен; «Файлы», «Документы», «Команда», «Чаты объектов»; "
    "«Уведомления», «Тариф и оплата», «Поддержка», «Чаты и сообщения» (центр общения: личные чаты по "
    "публичному ID вида SM-…, чаты объектов TEAM, сообщество), «Настройки» (профиль, аккаунт и вход, "
    "ассистент, тема, экспорт данных, удаление аккаунта). В редакторе сметы есть автоматическая "
    "проверка «Антисмета». Веб и Android используют один аккаунт. Вход — по почте (код или пароль) "
    "или через Яндекс ID. Оплата — разово через ЮKassa за выбранный период, без автосписаний. "
)


def _support_prompt(user, user_stats):
    return (
        "Ты — специалист поддержки сервиса «Сметра» (сметы для ремонта и отделки). "
        "Отвечай по-русски, тепло и по делу, как живой человек в мессенджере: 1–5 коротких "
        "предложений или короткий нумерованный список шагов. Без канцелярита, рекламы и эмодзи. "
        "Называй разделы и кнопки точно так, как в интерфейсе, в «кавычках». "
        + SUPPORT_PRODUCT_GUIDE
        + "Тарифы (цены от сервера, не меняй их): " + _plan_lines() + ". "
        "Если не хватает данных, задай один уточняющий вопрос. Текущий тариф, оплаты, команду и "
        "состояние интеграций бери только из live-контекста ниже; если его нет — так и скажи. "
        "Не обещай функций, которых нет в описании; не выдумывай статусы платежей, сроки, цены, "
        "контакты. Не проси пароль, коды входа, данные карты и секреты; не раскрывай внутренние "
        "переменные и чужие данные. Возврат денег, спорные списания, блокировки, ошибки, которые "
        "ты не можешь проверить, и прямые просьбы позвать человека, оператора или менеджера — "
        "эскалируй сотруднику (escalate=true) и коротко скажи, что передал вопрос и ответ придёт в "
        "этот чат. В остальных случаях решай сам, escalate=false. "
        "Ответ — только JSON-объект: {\"reply\": строка, \"escalate\": true|false, "
        "\"reason\": короткая строка}. "
        "Live-контекст аккаунта (используй только для этого обращения): "
        + json.dumps(user_stats, ensure_ascii=False)
    )


def _parse_support_reply(raw):
    """Accept strict JSON, fenced JSON or plain prose from free models."""
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        raise ValueError("empty support reply")
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    for candidate in (fenced, (re.search(r"\{.*\}", fenced, re.S) or [None])[0]):
        if not candidate:
            continue
        try:
            decoded = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(decoded, dict) and str(decoded.get("reply") or "").strip():
            return decoded
    # Prose without the JSON envelope is still a usable answer.
    if fenced.startswith("{"):
        raise ValueError("malformed support payload")
    return {"reply": fenced, "escalate": False, "reason": ""}


def _support_completion(payload, timeout):
    from backend.model_transport import FREE_ROUTER

    def call(body):
        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + os.getenv("OPENROUTER_API_KEY", "").strip(),
                "Content-Type": "application/json",
                "HTTP-Referer": ORIGIN,
                "X-Title": "Smetra Support",
            },
            method="POST",
        )
        # Support has its own bounded JSON-mode/free-router retry. Do not call
        # open_completion here: its retry would multiply support requests.
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read(500_000).decode("utf-8"))
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    try:
        return _parse_support_reply(call(payload))
    except urllib.error.HTTPError as error:
        # Authentication and account-wide provider rate limits cannot be
        # recovered by immediately making another paid/upstream request.
        if error.code in (401, 403, 429):
            raise
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
        pass
    # Retry with a free model and without strict JSON mode, which is rejected
    # by some free providers. The system prompt still requests JSON.
    retry = {**payload, "model": FREE_ROUTER}
    retry.pop("response_format", None)
    return _parse_support_reply(call(retry))


def _support_ai_reply(user, user_stats, history, message):
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    human_requested = wants_human(message)
    if human_requested:
        # Never hold a support conversation waiting for the model when the
        # user explicitly asks to speak with an employee.
        return {
            "reply": "Передал обращение сотруднику поддержки. Ответ придёт в этот чат.",
            "escalate": True, "reason": "user_requested_human",
        }
    if not api_key:
        return {
            "reply": "Не хочу гадать и вводить вас в заблуждение: автоматическая поддержка сейчас недоступна. "
                     "Я передал обращение сотруднику — ответ придёт в этот чат.",
            "escalate": True, "reason": "support_ai_unavailable",
        }
    messages = [{"role": "system", "content": _support_prompt(user, user_stats)}]
    for row in history[-12:]:
        if row["sender_type"] == "system":
            continue
        body = str(row["body"])[:4000]
        if row["sender_type"] == "admin":
            body = "Сотрудник поддержки ответил: " + body
        messages.append({"role": "user" if row["sender_type"] == "user" else "assistant", "content": body})
    messages.append({"role": "user", "content": message})
    payload = {
        "model": os.getenv("SUPPORT_AI_MODEL") or os.getenv("OPENROUTER_MODEL") or "openrouter/free",
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
    }
    try:
        timeout = max(4, min(20, int(os.getenv("SUPPORT_AI_TIMEOUT_SECONDS", "12"))))
    except ValueError:
        timeout = 12
    try:
        decoded = _support_completion(payload, timeout)
        reply = _text(decoded.get("reply"), 3000, required=True)
        escalate = decoded.get("escalate") is True
        reason = _text(decoded.get("reason"), 120) if escalate else ""
        return {"reply": reply, "escalate": escalate,
                "reason": reason or ("user_requested_human" if human_requested else "ai_handoff")}
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError, ApiError):
        return {
            "reply": "Пока не получается надёжно ответить автоматически. "
                     "Я передал ваше обращение специалисту — ответ придёт в этот чат.",
            "escalate": True, "reason": "support_ai_error",
        }


def _public_id_route(handler, method, path, query, con, user):
    if path == "/api/profile/presence" and method == "POST":
        con.execute(
            "INSERT INTO app_presence(user_id,last_seen_at) VALUES(?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_seen_at=excluded.last_seen_at",
            (user["id"], now()),
        )
        return handler.send_json(200, {"ok": True})
    if path == "/api/profile/id" and method == "GET":
        return handler.send_json(200, {
            "id": user["id"], "public_id": make_public_id(user["id"]),
            "name": user["name"], "role": user["role"],
        })
    if path == "/api/profile/directory" and method == "GET":
        handler.throttle("profile-lookup:" + user["id"], 30, 60)
        value = (query.get("q") or [""])[0]
        normalized = normalize_public_id(value)
        if not normalized:
            raise ApiError(400, "Введите публичный ID целиком, например SM-…")
        row = con.execute(
            "SELECT id,name FROM users WHERE upper(replace(id,'-',''))=? "
            "AND id<>? AND deleted_at IS NULL AND blocked=0",
            (normalized, user["id"]),
        ).fetchone()
        if not row:
            raise ApiError(404, "Пользователь с таким ID не найден")
        return handler.send_json(200, {
            "user": {"id": row["id"], "name": row["name"],
                     "public_id": make_public_id(row["id"])}
        })
    if path == "/api/profile/chats" and method == "GET":
        return handler.send_json(200, {
            "chats": _list_conversations(con, user["id"], ("direct", "object", "estimate"))
        })
    if path == "/api/profile/chats" and method == "POST":
        handler.throttle("chat-create:" + user["id"], 20, 60)
        data = handler.body()
        target_id = normalize_public_id(data.get("public_id"))
        if not target_id:
            raise ApiError(400, "Укажите публичный ID собеседника")
        target = con.execute(
            "SELECT id,name FROM users WHERE upper(replace(id,'-',''))=? "
            "AND deleted_at IS NULL AND blocked=0",
            (target_id,),
        ).fetchone()
        if not target:
            raise ApiError(404, "Пользователь не найден")
        if target["id"] == user["id"]:
            raise ApiError(400, "Нельзя открыть личный чат с самим собой")
        direct_key = ":".join(sorted((user["id"], target["id"])))
        conversation_id = _new_conversation(
            con, "direct", target["name"], user["id"], direct_key=direct_key
        )
        _add_member(con, conversation_id, user["id"], "member")
        _add_member(con, conversation_id, target["id"], "member")
        row = con.execute(
            "SELECT * FROM chat_conversations WHERE id=?", (conversation_id,)
        ).fetchone()
        return handler.send_json(200, {"chat": {
            "id": row["id"], "kind": row["kind"], "subject": row["subject"],
            "partner_name": target["name"], "partner_public_id": make_public_id(target["id"]),
        }})
    if path == "/api/profile/quote-chats" and method == "POST":
        data = handler.body()
        quote_id = _text(data.get("quote_id"), 80, required=True)
        target_public_id = normalize_public_id(data.get("public_id"))
        if not target_public_id:
            raise ApiError(400, "Укажите публичный ID клиента")
        quote = con.execute(
            "SELECT id,title,public_token FROM quotes WHERE id=? AND user_id=?",
            (quote_id, user["id"]),
        ).fetchone()
        if not quote:
            raise ApiError(404, "Смета не найдена")
        target = con.execute(
            "SELECT id,name FROM users WHERE upper(replace(id,'-',''))=? "
            "AND id<>? AND deleted_at IS NULL AND blocked=0",
            (target_public_id, user["id"]),
        ).fetchone()
        if not target:
            raise ApiError(404, "Пользователь не найден")
        estimate_key = "estimate:" + quote_id + ":" + target["id"]
        existing = con.execute(
            "SELECT id FROM chat_conversations WHERE direct_key=?", (estimate_key,)
        ).fetchone()
        conversation_id = _new_conversation(
            con, "estimate", "Смета: " + _text(quote["title"], 150),
            user["id"], quote_id=quote_id, direct_key=estimate_key
        )
        _add_member(con, conversation_id, user["id"], "owner")
        _add_member(con, conversation_id, target["id"], "client")
        if not existing:
            public_url = ORIGIN + "/app?quote=" + urllib.parse.quote(str(quote["public_token"]), safe="")
            _add_message(
                con, conversation_id, user["id"], "user",
                "Создано обсуждение сметы «" + _text(quote["title"], 150) +
                "». Клиентскую версию можно открыть по ссылке: " + public_url,
                {"event": "estimate_chat_created", "quote_id": quote_id},
            )
        return handler.send_json(200, {"chat": {
            "id": conversation_id, "kind": "estimate", "subject": "Смета: " + quote["title"],
            "quote_id": quote_id, "partner_name": target["name"],
            "partner_public_id": make_public_id(target["id"]),
        }})
    if path == "/api/profile/object-chats" and method == "GET":
        rows = con.execute(
            "SELECT w.id FROM workspaces w LEFT JOIN workspace_members m "
            "ON m.workspace_id=w.id AND m.user_id=? "
            "WHERE (m.user_id=? OR w.owner_id=?) ORDER BY w.created_at DESC LIMIT 50",
            (user["id"], user["id"], user["id"]),
        ).fetchall()
        workspaces = []
        for item in rows:
            row = _refresh_workspace_entitlement(con, item["id"])
            plan = str(row["plan"] or "").lower()
            enabled = (
                row["subscription_status"] in ("active", "succeeded")
                and int(row["entitlement_until"] or 0) > now()
                and plan in ("team", "team_month", "team_year", "team_monthly", "team_yearly")
            )
            workspaces.append({"id": row["id"], "name": row["name"],
                               "plan": row["plan"], "enabled": enabled})
        return handler.send_json(200, {
            "available": any(w["enabled"] for w in workspaces),
            "workspaces": workspaces,
            "chats": _list_conversations(con, user["id"], ("object",)),
        })
    if path == "/api/profile/object-chats" and method == "POST":
        handler.throttle("object-chat-create:" + user["id"], 10, 60)
        data = handler.body()
        workspace_id = _text(data.get("workspace_id"), 100, required=True)
        workspace = _team_workspace(con, user["id"], workspace_id)
        subject = _text(data.get("subject") or workspace["name"], 120, required=True)
        project_id = _text(data.get("project_id"), 100)
        if project_id:
            project = con.execute(
                "SELECT id FROM projects WHERE id=? AND workspace_id=?",
                (project_id, workspace_id),
            ).fetchone()
            if not project:
                raise ApiError(404, "Объект не найден в этом рабочем пространстве")
        object_key = "object:" + workspace_id + ":" + (project_id or subject.casefold())
        conversation_id = _new_conversation(
            con, "object", subject, user["id"], workspace_id=workspace_id,
            project_id=project_id, direct_key=object_key
        )
        members = con.execute(
            "SELECT user_id,role FROM workspace_members WHERE workspace_id=?",
            (workspace_id,),
        ).fetchall()
        if not members:
            _add_member(con, conversation_id, user["id"], "director")
        for member in members:
            _add_member(con, conversation_id, member["user_id"], member["role"])
        _add_member(con, conversation_id, workspace["owner_id"], "director")
        _add_message(con, conversation_id, None, "system", "Рабочий чат объекта создан.", {
            "event": "object_chat_created", "workspace_id": workspace_id,
            "project_id": project_id,
        })
        row = con.execute("SELECT * FROM chat_conversations WHERE id=?", (conversation_id,)).fetchone()
        return handler.send_json(200, {"chat": {
            "id": row["id"], "kind": row["kind"], "subject": row["subject"],
            "workspace_id": row["workspace_id"], "project_id": row["project_id"],
        }})
    if path == "/api/profile/communities" and method == "GET":
        channels = []
        for key, label in COMMUNITIES.items():
            conversation_id = _community(con, user["id"], key)
            channels.append({"id": conversation_id, "category": key, "label": label})
        return handler.send_json(200, {"channels": channels})
    match = re.fullmatch(r"/api/profile/chats/([A-Za-z0-9_-]+)/messages", path)
    if match and method in ("GET", "POST"):
        conversation_id = match.group(1)
        conversation = con.execute(
            "SELECT id,kind,status,category FROM chat_conversations WHERE id=?",
            (conversation_id,),
        ).fetchone()
        if not conversation or conversation["kind"] not in ("direct", "object", "estimate", "community"):
            raise ApiError(404, "Чат не найден")
        if not _member(con, conversation_id, user["id"]):
            if conversation["kind"] != "community":
                raise ApiError(403, "Нет доступа к этому чату")
            _add_member(con, conversation_id, user["id"], "member")
        if method == "GET":
            after = (query.get("after") or ["0"])[0]
            try:
                after = max(0, int(after))
            except ValueError:
                after = 0
            messages = _messages(con, conversation_id, after=after)
            con.execute(
                "UPDATE chat_members SET last_read_at=? WHERE conversation_id=? AND user_id=?",
                (now(), conversation_id, user["id"]),
            )
            return handler.send_json(200, {"messages": messages})
        handler.throttle("chat-message:" + user["id"], 45, 60)
        data = handler.body()
        message = _text(data.get("message"), 4000, required=True)
        if conversation["status"] == "closed":
            raise ApiError(409, "Чат закрыт")
        saved = _add_message(con, conversation_id, user["id"], "user", message)
        return handler.send_json(201, {"message": saved})
    if path == "/api/profile/communities" and method == "POST":
        # Kept as a convenient explicit join action for Android clients.
        data = handler.body()
        category = _text(data.get("category"), 40, required=True)
        if category not in COMMUNITIES:
            raise ApiError(400, "Неизвестная категория")
        conversation_id = _community(con, user["id"], category)
        return handler.send_json(200, {"chat": {"id": conversation_id,
            "kind": "community", "category": category, "subject": COMMUNITIES[category]}})
    return None


def _support_route(handler, method, path, query, con, user):
    if path == "/api/support" and method == "POST":
        data = handler.body()
        message = _text(data.get("message"), 4000, required=True)
        subject = _text(data.get("subject") or "Обращение в поддержку", 120)
        conversation_id = _new_conversation(con, "support", subject, user["id"])
        _add_member(con, conversation_id, user["id"], "customer")
        con.execute(
            "INSERT INTO support(id,user_id,message,status,created_at) VALUES(?,?,?,'open',?)",
            (conversation_id, user["id"], message, now()),
        )
        _add_message(con, conversation_id, user["id"], "user", message)
        response = _support_ai_reply(user, _support_user_context(con, user), [], message)
        if response["escalate"]:
            con.execute(
                "UPDATE chat_conversations SET needs_human=1,human_reason=?,updated_at=? WHERE id=?",
                (response["reason"], now(), conversation_id),
            )
        _add_message(con, conversation_id, None, "assistant", response["reply"], {
            "escalated": response["escalate"], "reason": response["reason"]
        })
        return handler.send_json(201, {"ok": True, "ticket_id": conversation_id,
            "reply": response["reply"], "needs_human": response["escalate"]})
    if path == "/api/support/threads" and method == "GET":
        return handler.send_json(200, {
            "threads": _list_conversations(con, user["id"], ("support",))
        })
    if path == "/api/support/threads" and method == "POST":
        data = handler.body()
        subject = _text(data.get("subject") or "Новый вопрос", 120, required=True)
        conversation_id = _new_conversation(con, "support", subject, user["id"])
        _add_member(con, conversation_id, user["id"], "customer")
        _add_message(con, conversation_id, None, "system", "Обращение создано. Опишите вопрос — ассистент поддержки ответит здесь.")
        row = con.execute("SELECT * FROM chat_conversations WHERE id=?", (conversation_id,)).fetchone()
        return handler.send_json(201, {"thread": {
            "id": row["id"], "subject": row["subject"], "status": row["status"],
            "needs_human": False, "created_at": row["created_at"],
        }})
    match = re.fullmatch(r"/api/support/threads/([A-Za-z0-9_-]+)(?:/(messages|handoff))?", path)
    if match:
        conversation_id, action = match.group(1), match.group(2) or ""
        conversation = con.execute(
            "SELECT * FROM chat_conversations WHERE id=? AND kind='support'",
            (conversation_id,),
        ).fetchone()
        if not conversation:
            raise ApiError(404, "Обращение не найдено")
        if not _member(con, conversation_id, user["id"]):
            raise ApiError(403, "Нет доступа к этому обращению")
        if action == "handoff" and method == "POST":
            reason = _text((handler.body().get("reason") or "user_requested_human"), 120)
            con.execute(
                "UPDATE chat_conversations SET needs_human=1,human_reason=?,updated_at=? WHERE id=?",
                (reason, now(), conversation_id),
            )
            _add_message(con, conversation_id, None, "system", "Пользователь попросил подключить сотрудника. Обращение добавлено в очередь поддержки.")
            return handler.send_json(200, {"ok": True, "needs_human": True})
        if action == "messages" and method == "GET":
            try:
                after = max(0, int((query.get("after") or ["0"])[0] or 0))
            except (TypeError, ValueError):
                after = 0
            messages = _messages(con, conversation_id, after=after)
            con.execute(
                "UPDATE chat_members SET last_read_at=? WHERE conversation_id=? AND user_id=?",
                (now(), conversation_id, user["id"]),
            )
            return handler.send_json(200, {"messages": messages})
        if action == "messages" and method == "POST":
            handler.throttle("support-message:" + user["id"], 30, 60)
            data = handler.body()
            message = _text(data.get("message"), 4000, required=True)
            if conversation["status"] == "closed":
                raise ApiError(409, "Обращение закрыто. Создайте новое обращение.")
            history = _messages(con, conversation_id, limit=20)
            _add_message(con, conversation_id, user["id"], "user", message)
            if conversation["needs_human"]:
                return handler.send_json(201, {"messages": [], "needs_human": True})
            user_stats = _support_user_context(con, user)
            response = _support_ai_reply(user, user_stats, history, message)
            if response["escalate"]:
                con.execute(
                    "UPDATE chat_conversations SET needs_human=1,human_reason=?,updated_at=? WHERE id=?",
                    (response["reason"], now(), conversation_id),
                )
            answer = _add_message(con, conversation_id, None, "assistant", response["reply"], {
                "escalated": response["escalate"], "reason": response["reason"]
            })
            return handler.send_json(201, {
                "messages": [answer], "needs_human": response["escalate"],
                "reply": answer["body"],
            })
    return None


def _admin_overview(con):
    def scalar(sql, parameters=()):
        return int(con.execute(sql, parameters).fetchone()[0] or 0)
    moment = now()
    users = scalar("SELECT COUNT(*) FROM users WHERE deleted_at IS NULL")
    quotes = scalar("SELECT COUNT(*) FROM quotes")
    def paid_amount(since=None):
        conditions = [
            "b.is_test=0",
            "p.status='succeeded'",
            "NOT EXISTS (SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded')",
        ]
        parameters = []
        if since is not None:
            conditions.append("COALESCE(p.activated_at,p.created_at)>=?")
            parameters.append(since)
        return scalar(
            "SELECT COALESCE(SUM(p.amount_kopecks),0) FROM payments p "
            "JOIN billing_intents b ON b.payment_id=p.id WHERE " + " AND ".join(conditions),
            tuple(parameters),
        )
    active_subs = scalar(
        "SELECT COUNT(*) FROM ("
        "SELECT user_id FROM billing_subscriptions WHERE status IN ('active','succeeded') "
        "AND current_period_end>? AND is_test=FALSE "
        "UNION SELECT u.id AS user_id FROM users u WHERE u.deleted_at IS NULL "
        "AND u.entitlement_until>? AND NOT EXISTS ("
        "SELECT 1 FROM billing_subscriptions b WHERE b.user_id=u.id AND b.is_test=TRUE "
        "AND b.status IN ('active','succeeded') AND b.current_period_end>?"
        ")) AS active_paid_users",
        (moment, moment, moment),
    )
    return {
        "as_of": moment,
        "users_total": users,
        "users_online": scalar("SELECT COUNT(*) FROM app_presence WHERE last_seen_at>=?", (moment-120,)),
        "users_dau": scalar("SELECT COUNT(DISTINCT user_id) FROM events WHERE user_id IS NOT NULL AND created_at>=?", (moment-86400,)),
        "users_mau": scalar("SELECT COUNT(DISTINCT user_id) FROM events WHERE user_id IS NOT NULL AND created_at>=?", (moment-2592000,)),
        "estimates_total": quotes,
        "estimates_30d": scalar("SELECT COUNT(*) FROM quotes WHERE created_at>=?", (moment-2592000,)),
        "estimates_sent": scalar("SELECT COUNT(*) FROM quotes WHERE status='sent'"),
        "estimates_approved": scalar("SELECT COUNT(*) FROM quotes WHERE status='accepted'"),
        "workspaces_total": scalar("SELECT COUNT(*) FROM workspaces"),
        "projects_total": scalar("SELECT COUNT(*) FROM projects"),
        "clients_total": scalar("SELECT COUNT(*) FROM clients"),
        "files_total": scalar("SELECT COUNT(*) FROM files"),
        "expenses_total": scalar("SELECT COUNT(*) FROM expenses"),
        "messages_total": scalar("SELECT COUNT(*) FROM chat_messages"),
        "chats_total": scalar("SELECT COUNT(*) FROM chat_conversations"),
        "support_open": scalar("SELECT COUNT(*) FROM chat_conversations WHERE kind='support' AND status<>'closed'"),
        "support_waiting_human": scalar("SELECT COUNT(*) FROM chat_conversations WHERE kind='support' AND status<>'closed' AND needs_human=1 AND assigned_admin_id IS NULL"),
        "paid_subscriptions": active_subs,
        "revenue_kopecks": paid_amount(),
        "revenue_today_kopecks": paid_amount(moment-86400),
        "revenue_30d_kopecks": paid_amount(moment-2592000),
        "pending_payments": scalar(
            "SELECT COUNT(*) FROM payments p JOIN billing_intents b ON b.payment_id=p.id "
            "WHERE b.is_test=0 AND p.status='pending'"
        ),
        "paid_transactions": scalar(
            "SELECT COUNT(*) FROM payments p JOIN billing_intents b ON b.payment_id=p.id "
            "WHERE b.is_test=0 AND p.status='succeeded' AND NOT EXISTS "
            "(SELECT 1 FROM refunds r WHERE r.payment_id=p.id AND r.status='succeeded')"
        ),
        "tracked_events_30d": scalar("SELECT COUNT(*) FROM events WHERE created_at>=?", (moment-2592000,)),
    }


SUPPORT_STAGES = ("new", "in_progress", "waiting_user", "resolved")


def _support_stage(row):
    """Queue status derived from stored facts; no extra column to drift."""
    if row["status"] == "closed":
        return "resolved"
    last = row["last_sender_type"]
    if row["assigned_admin_id"]:
        return "waiting_user" if last == "admin" else "in_progress"
    if last == "assistant" and not row["needs_human"]:
        return "waiting_user"
    return "new"


def _admin_route(handler, method, path, query, con):
    admin = _auth(handler, con, admin=True)
    if path == "/api/admin/communication/overview" and method == "GET":
        return handler.send_json(200, _admin_overview(con))
    if path == "/api/admin/communication/threads" and method == "GET":
        rows = con.execute(
            "SELECT c.*, "
            "(SELECT m.body FROM chat_messages m WHERE m.conversation_id=c.id ORDER BY m.created_at DESC,m.id DESC LIMIT 1) AS last_message, "
            "(SELECT m.created_at FROM chat_messages m WHERE m.conversation_id=c.id ORDER BY m.created_at DESC,m.id DESC LIMIT 1) AS last_message_at, "
            "0 AS unread_count,'' AS partner_id,'' AS partner_name,"
            "(SELECT u.name FROM users u WHERE u.id=c.created_by) AS user_name,"
            "(SELECT u.email FROM users u WHERE u.id=c.created_by) AS user_email,"
            "(SELECT m.sender_type FROM chat_messages m WHERE m.conversation_id=c.id AND m.sender_type<>'system' "
            " ORDER BY m.created_at DESC,CASE m.sender_type WHEN 'user' THEN 0 WHEN 'assistant' THEN 1 ELSE 2 END DESC,m.id DESC LIMIT 1) AS last_sender_type,"
            "(SELECT u.name FROM users u WHERE u.id=c.assigned_admin_id) AS assigned_admin_name "
            "FROM chat_conversations c WHERE c.kind='support' "
            "ORDER BY c.needs_human DESC,c.status ASC,c.updated_at DESC LIMIT 150"
        ).fetchall()
        threads = []
        for row in rows:
            view = _conversation_view(row)
            view["stage"] = _support_stage(row)
            view["assigned_admin_name"] = row["assigned_admin_name"] or ""
            view["assigned_to_me"] = row["assigned_admin_id"] == admin["id"]
            threads.append(view)
        stage = (query.get("stage") or [""])[0] if isinstance(query, dict) else ""
        if stage in SUPPORT_STAGES:
            threads = [thread for thread in threads if thread["stage"] == stage]
        return handler.send_json(200, {"threads": threads})
    if path == "/api/admin/communication/admins" and method == "GET":
        rows = con.execute(
            "SELECT id,name,email FROM users WHERE role='admin' AND deleted_at IS NULL ORDER BY name LIMIT 50"
        ).fetchall()
        return handler.send_json(200, {"admins": [
            {"id": row["id"], "name": row["name"] or row["email"], "me": row["id"] == admin["id"]} for row in rows
        ]})
    match = re.fullmatch(r"/api/admin/communication/threads/([A-Za-z0-9_-]+)(?:/(messages))?", path)
    if match:
        conversation_id, action = match.group(1), match.group(2) or ""
        conversation = con.execute(
            "SELECT * FROM chat_conversations WHERE id=? AND kind='support'", (conversation_id,)
        ).fetchone()
        if not conversation:
            raise ApiError(404, "Обращение не найдено")
        if action == "messages" and method == "GET":
            return handler.send_json(200, {"messages": _messages(con, conversation_id)})
        if action == "messages" and method == "POST":
            handler.throttle("admin-support-reply:" + admin["id"], 60, 60)
            message = _text(handler.body().get("message"), 4000, required=True)
            saved = _add_message(con, conversation_id, admin["id"], "admin", message)
            con.execute(
                "UPDATE chat_conversations SET assigned_admin_id=?,needs_human=0,human_reason='',"
                "status='open',updated_at=? WHERE id=?",
                (admin["id"], now(), conversation_id),
            )
            audit(con, admin["id"], "admin.support.reply", conversation_id)
            return handler.send_json(201, {"message": saved})
        if method == "PATCH" and not action:
            data = handler.body()
            action_name = _text(data.get("action"), 20, required=True)
            if action_name not in ("close", "reopen", "assign", "release", "transfer"):
                raise ApiError(400, "Неизвестное действие")
            if action_name == "transfer":
                target = _text(data.get("admin_id"), 80, required=True)
                if not con.execute(
                    "SELECT 1 FROM users WHERE id=? AND role='admin' AND deleted_at IS NULL", (target,)
                ).fetchone():
                    raise ApiError(400, "Сотрудник не найден")
                con.execute(
                    "UPDATE chat_conversations SET assigned_admin_id=?,needs_human=0,status='open',updated_at=? WHERE id=?",
                    (target, now(), conversation_id),
                )
                audit(con, admin["id"], "admin.support.transfer", conversation_id + ":" + target)
                return handler.send_json(200, {"ok": True})
            if action_name == "close":
                con.execute(
                    "UPDATE chat_conversations SET status='closed',needs_human=0,updated_at=? WHERE id=?",
                    (now(), conversation_id),
                )
            elif action_name == "reopen":
                con.execute(
                    "UPDATE chat_conversations SET status='open',updated_at=? WHERE id=?",
                    (now(), conversation_id),
                )
            elif action_name == "assign":
                con.execute(
                    "UPDATE chat_conversations SET assigned_admin_id=?,needs_human=0,updated_at=? WHERE id=?",
                    (admin["id"], now(), conversation_id),
                )
            else:
                con.execute(
                    "UPDATE chat_conversations SET assigned_admin_id=NULL,needs_human=1,updated_at=? WHERE id=?",
                    (now(), conversation_id),
                )
            audit(con, admin["id"], "admin.support." + action_name, conversation_id)
            return handler.send_json(200, {"ok": True})
    return None


def route(handler, method, path, query, con):
    user = None
    if path.startswith("/api/admin/communication/"):
        result = _admin_route(handler, method, path, query, con)
        if result is not None:
            return result
        raise ApiError(404, "Не найдено")
    if path.startswith("/api/profile/"):
        user = _auth(handler, con)
        result = _public_id_route(handler, method, path, query, con, user)
        if result is not None:
            return result
        raise ApiError(404, "Не найдено")
    if path == "/api/support" or path.startswith("/api/support/"):
        user = _auth(handler, con)
        result = _support_route(handler, method, path, query, con, user)
        if result is not None:
            return result
        raise ApiError(404, "Не найдено")
    return None
