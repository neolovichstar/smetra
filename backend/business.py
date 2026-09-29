"""Workspace-scoped business operations. Money is stored in minor units."""

import datetime as dt
import json
import re
import secrets
import time
import uuid
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


class DomainError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def stamp():
    return int(time.time())


def identity():
    return str(uuid.uuid4())


def packed(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


@contextmanager
def transaction(con):
    con.execute("BEGIN IMMEDIATE")
    try:
        yield
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def string(value, label, maximum=3000, required=False):
    if (
        not isinstance(value, str)
        or len(value.strip()) > maximum
        or (required and not value.strip())
    ):
        raise DomainError(400, f"Проверьте поле «{label}» (до {maximum} символов)")
    return value.strip()


def integer(value, label, low=0, high=10_000_000_000):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not low <= value <= high
    ):
        raise DomainError(400, f"Некорректное поле «{label}»")
    return value


def decimal(value, label, low="0", high="100", places=4):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise DomainError(400, f"Некорректное поле «{label}»")
    try:
        number = Decimal(str(value))
        if (
            not number.is_finite()
            or not Decimal(low) <= number <= Decimal(high)
            or number.as_tuple().exponent < -places
        ):
            raise InvalidOperation
        return number
    except InvalidOperation:
        raise DomainError(400, f"Некорректное поле «{label}»") from None


def date_value(value, label="Дата"):
    if value == "":
        return ""
    try:
        return dt.date.fromisoformat(string(value, label, 10)).isoformat()
    except ValueError:
        raise DomainError(400, f"Некорректная дата: {label}") from None


def choice(value, options, label):
    if not isinstance(value, str) or value not in options:
        raise DomainError(400, f"Некорректное поле «{label}»")
    return value


def calculate(items):
    if not isinstance(items, list) or not 1 <= len(items) <= 200:
        raise DomainError(400, "Добавьте от 1 до 200 позиций")
    result, total, cost = [], 0, 0
    for item in items:
        if not isinstance(item, dict):
            raise DomainError(400, "Некорректная позиция")
        quantity = decimal(item.get("quantity", "1"), "Количество", "0.0001", "1000000")
        price = integer(item.get("unit_price", 0), "Цена")
        internal = integer(item.get("cost_price", 0), "Себестоимость")
        markup = decimal(item.get("markup", "0"), "Наценка", high="10000")
        discount = decimal(item.get("discount", "0"), "Скидка")
        tax = decimal(item.get("tax", "0"), "Налог")
        optional = item.get("optional", False)
        included = item.get("included", True)
        if not isinstance(optional, bool) or not isinstance(included, bool):
            raise DomainError(400, "Некорректный выбор позиции")
        if not optional:
            included = True
        base = (quantity * price * (1 + markup / 100) * (1 - discount / 100)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        tax_amount = (base * tax / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        subtotal = integer(int(base + tax_amount), "Сумма позиции")
        cost_total = integer(
            int((quantity * internal).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "Себестоимость позиции",
        )
        row = dict(
            name=string(item.get("name", ""), "Позиция", 200, True),
            description=string(item.get("description", ""), "Описание"),
            category=string(item.get("category", ""), "Категория", 100),
            unit=string(item.get("unit", "шт."), "Единица", 30, True),
            quantity=str(quantity),
            unit_price=price,
            cost_price=internal,
            markup=str(markup),
            discount=str(discount),
            tax=str(tax),
            optional=optional,
            included=included,
            subtotal=subtotal,
            tax_amount=int(tax_amount),
            internal_cost=cost_total,
        )
        result.append(row)
        if included:
            total += subtotal
            cost += cost_total
    integer(total, "Итоговая стоимость", 1)
    integer(cost, "Общая себестоимость")
    return result, total, cost


def ensure_workspace(con, user):
    wid = str(uuid.uuid5(uuid.NAMESPACE_URL, "smetra-workspace:" + user["id"]))
    con.execute(
        "INSERT OR IGNORE INTO workspaces(id,owner_id,name,created_at) VALUES(?,?,?,?)",
        (wid, user["id"], user["name"], stamp()),
    )
    con.execute(
        "INSERT OR IGNORE INTO workspace_members(workspace_id,user_id,role) VALUES(?,?,'owner')",
        (wid, user["id"]),
    )
    return wid


def migrate(con):
    con.execute(
        "CREATE TABLE IF NOT EXISTS rate_limits(key TEXT PRIMARY KEY,count INTEGER NOT NULL,started INTEGER NOT NULL)"
    )
    con.executescript(
        (Path(__file__).parent / "migrations" / "004_identity_assistant.sql").read_text(
            encoding="utf-8"
        )
    )
    con.executescript(
        (Path(__file__).parent / "migrations" / "003_files_ai.sql").read_text(
            encoding="utf-8"
        )
    )
    con.executescript(
        (Path(__file__).parent / "migrations" / "002_business.sql").read_text(
            encoding="utf-8"
        )
    )
    columns = {
        "workspace_id": "TEXT REFERENCES workspaces(id)",
        "client_id": "TEXT REFERENCES clients(id) ON DELETE SET NULL",
        "currency": "TEXT NOT NULL DEFAULT 'RUB'",
        "revision": "INTEGER NOT NULL DEFAULT 1",
        "published_version": "INTEGER NOT NULL DEFAULT 0",
        "approval_state": "TEXT NOT NULL DEFAULT 'draft'",
        "terms": "TEXT NOT NULL DEFAULT ''",
        "due_date": "TEXT NOT NULL DEFAULT ''",
        "expires_at": "INTEGER",
        "internal_cost": "INTEGER NOT NULL DEFAULT 0",
        "view_count": "INTEGER NOT NULL DEFAULT 0",
        "first_viewed_at": "INTEGER",
        "sent_at": "INTEGER",
        "approved_at": "INTEGER",
        "approved_by": "TEXT NOT NULL DEFAULT ''",
        "custom_fields": "TEXT NOT NULL DEFAULT '{}'",
        "itemized": "INTEGER NOT NULL DEFAULT 0",
    }
    existing = {r["name"] for r in con.execute("PRAGMA table_info(quotes)")}
    with transaction(con):
        for key, definition in columns.items():
            if key not in existing:
                con.execute(f"ALTER TABLE quotes ADD COLUMN {key} {definition}")
        for user in con.execute(
            "SELECT * FROM users WHERE deleted_at IS NULL"
        ).fetchall():
            wid = ensure_workspace(con, user)
            con.execute(
                "UPDATE quotes SET workspace_id=? WHERE user_id=? AND workspace_id IS NULL",
                (wid, user["id"]),
            )
        for row in con.execute(
            "SELECT * FROM quotes WHERE status!='draft' AND published_version=0"
        ).fetchall():
            state = {
                "sent": "sent",
                "accepted": "approved",
                "completed": "approved",
                "declined": "rejected",
            }[row["status"]]
            snapshot = {
                k: row[k]
                for k in (
                    "id",
                    "title",
                    "client",
                    "description",
                    "amount_kopecks",
                    "currency",
                    "terms",
                    "due_date",
                    "internal_cost",
                )
            }
            snapshot.update(items=[], version=1)
            con.execute(
                "INSERT OR IGNORE INTO quote_versions VALUES(?,?,?,?,?,?)",
                (
                    row["id"],
                    1,
                    packed(snapshot),
                    row["user_id"],
                    "Перенесено из предыдущей версии",
                    stamp(),
                ),
            )
            con.execute(
                "UPDATE quotes SET published_version=1,approval_state=? WHERE id=?",
                (state, row["id"]),
            )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_quotes_workspace ON quotes(workspace_id,updated_at DESC)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,applied_at INTEGER NOT NULL)"
        )
        con.execute("INSERT OR IGNORE INTO schema_migrations VALUES(2,?)", (stamp(),))
        con.execute("INSERT OR IGNORE INTO schema_migrations VALUES(3,?)", (stamp(),))


ENTITIES = {
    "clients": {
        "strings": {
            "name": 120,
            "company": 200,
            "email": 254,
            "phone": 50,
            "telegram": 100,
            "notes": 5000,
        },
        "choices": {"type": ("person", "company")},
        "refs": {},
    },
    "catalog": {
        "table": "catalog_items",
        "strings": {"name": 200, "description": 3000, "unit": 30, "category": 100},
        "money": ("price", "cost_price"),
        "refs": {},
    },
    "projects": {
        "strings": {"name": 200, "description": 5000},
        "money": ("amount_kopecks", "internal_cost"),
        "refs": {"client_id": "clients"},
    },
    "stages": {
        "table": "project_stages",
        "strings": {"name": 200, "description": 3000},
        "money": ("amount_kopecks",),
        "refs": {"project_id": "projects"},
    },
    "tasks": {
        "strings": {"name": 200, "description": 3000},
        "choices": {
            "status": ("todo", "in_progress", "done"),
            "priority": ("low", "normal", "high"),
        },
        "refs": {"project_id": "projects", "client_id": "clients"},
    },
    "leads": {
        "strings": {"name": 200, "description": 3000},
        "money": ("amount_kopecks",),
        "refs": {"client_id": "clients"},
    },
}
DEFAULT_PIPELINE = [
    "Новый",
    "Связались",
    "Обсуждение",
    "Смета",
    "Ожидает решения",
    "Выигран",
    "Проигран",
]
PROJECT_STATUSES = ["planned", "in_progress", "waiting", "completed", "cancelled"]


class Service:
    def __init__(self, handler, con, origin):
        self.h, self.con, self.origin = handler, con, origin
        self.user = None
        self.wid = None
        self.role = None

    def emit(self, kind, entity, action, detail="", notify=False):
        actor = self.user["id"] if self.user else None
        self.con.execute(
            "INSERT INTO activity(id,workspace_id,actor_id,entity_type,entity_id,action,detail,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (identity(), self.wid, actor, kind, entity, action, detail[:1000], stamp()),
        )
        if notify:
            self.con.execute(
                "INSERT INTO notifications VALUES(?,?,?,?,?)",
                (identity(), self.wid, action, entity, stamp()),
            )

    def write_access(self, managerial=False):
        if self.role not in (
            ("owner", "admin", "manager")
            if managerial
            else ("owner", "admin", "manager", "member")
        ):
            raise DomainError(403, "Недостаточно прав в рабочем пространстве")

    def get(self, table, record_id):
        if not isinstance(record_id, str) or not 1 <= len(record_id) <= 100:
            raise DomainError(400, "Некорректный идентификатор записи")
        row = self.con.execute(
            f"SELECT * FROM {table} WHERE id=? AND workspace_id=?",
            (record_id, self.wid),
        ).fetchone()
        if not row:
            raise DomainError(404, "Запись не найдена")
        return row

    def page(self, query):
        try:
            return max(0, min(int(query.get("offset", ["0"])[0]), 100000))
        except ValueError:
            raise DomainError(400, "Неверная страница") from None

    def custom(self, entity, value):
        if not isinstance(value, dict) or len(value) > 50:
            raise DomainError(400, "Некорректные дополнительные поля")
        definitions = {
            r["id"]: r
            for r in self.con.execute(
                "SELECT * FROM custom_field_definitions WHERE workspace_id=? AND entity_type=?",
                (self.wid, entity),
            )
        }
        result = {}
        for key, val in value.items():
            if key not in definitions:
                raise DomainError(400, "Дополнительное поле не существует")
            row = definitions[key]
            typ = row["type"]
            if typ == "number":
                val = str(decimal(val, row["name"], "-10000000000", "10000000000"))
            elif typ == "checkbox":
                if not isinstance(val, bool):
                    raise DomainError(400, "Ожидается логическое значение")
            elif typ == "date":
                val = date_value(val)
            elif typ == "select":
                choice(val, json.loads(row["options"]), row["name"])
            elif typ == "multi_select":
                if (
                    not isinstance(val, list)
                    or len(val) > 50
                    or any(v not in json.loads(row["options"]) for v in val)
                ):
                    raise DomainError(400, "Некорректный выбор")
            else:
                val = string(val, row["name"], 2000)
                if typ == "url" and val and not re.match(r"^https?://[^\s]+$", val):
                    raise DomainError(
                        400, "Ссылка должна начинаться с https:// или http://"
                    )
            result[key] = val
        return packed(result)

    def quote_view(self, row, public=False, prefetched_items=None):
        if public:
            version = self.con.execute(
                "SELECT snapshot FROM quote_versions WHERE quote_id=? AND version=?",
                (row["id"], row["published_version"]),
            ).fetchone()
            if not version:
                raise DomainError(404, "Предложение ещё не отправлено")
            result = json.loads(version["snapshot"])
            for key in ("id", "client_id", "internal_cost", "custom_fields", "revision", "created_at", "updated_at", "itemized", "view_count", "first_viewed_at", "sent_at", "approved_at", "approved_by"):
                result.pop(key, None)
            for item in result.get("items", []):
                for key in ("cost_price", "internal_cost", "markup"):
                    item.pop(key, None)
        else:
            keys = (
                "id",
                "title",
                "client",
                "client_id",
                "description",
                "amount_kopecks",
                "currency",
                "terms",
                "due_date",
                "expires_at",
                "internal_cost",
                "revision",
                "created_at",
                "updated_at",
                "itemized",
                "view_count",
                "first_viewed_at",
                "sent_at",
                "approved_at",
                "approved_by",
            )
            result = {k: row[k] for k in keys}
            result["custom_fields"] = json.loads(row["custom_fields"])
            result["items"] = (
                prefetched_items
                if prefetched_items is not None
                else [
                    json.loads(r["data"])
                    for r in self.con.execute(
                        "SELECT data FROM quote_items WHERE quote_id=? ORDER BY position",
                        (row["id"],),
                    )
                ]
            )
            result["public_url"] = self.origin + "/?quote=" + row["public_token"]
            result["profit"] = row["amount_kopecks"] - row["internal_cost"]
        state = row["approval_state"]
        if (
            row["expires_at"]
            and row["expires_at"] < stamp()
            and state in ("sent", "viewed", "changes_requested")
        ):
            state = "expired"
        result.update(
            status=row["status"],
            approval_state=state,
            published_version=row["published_version"],
        )
        return result

    def quote_data(self, data, old=None):
        result = {}
        for key, limit, required in (
            ("title", 120, True),
            ("client", 120, True),
            ("description", 5000, False),
            ("terms", 5000, False),
        ):
            result[key] = string(
                data.get(key, old[key] if old else ""), key, limit, required
            )
        result["currency"] = choice(
            data.get("currency", old["currency"] if old else "RUB"),
            ("RUB", "USD", "EUR", "KZT", "BYN", "GBP"),
            "Валюта",
        )
        result["due_date"] = date_value(
            data.get("due_date", old["due_date"] if old else "")
        )
        result["expires_at"] = data.get(
            "expires_at", old["expires_at"] if old else None
        )
        if result["expires_at"] is not None:
            integer(result["expires_at"], "Срок ссылки", 1, 4102444800)
        client_id = data.get("client_id", old["client_id"] if old else None) or None
        if client_id:
            self.get("clients", client_id)
        result["client_id"] = client_id
        result["custom_fields"] = self.custom(
            "estimates",
            data.get("custom_fields", json.loads(old["custom_fields"]) if old else {}),
        )
        if "items" in data:
            items, total, cost = calculate(data["items"])
            result.update(amount_kopecks=total, internal_cost=cost, itemized=1)
        elif old and old["itemized"]:
            items = None
            result.update(
                amount_kopecks=old["amount_kopecks"],
                internal_cost=old["internal_cost"],
                itemized=1,
            )
        else:
            items = None
            result.update(
                amount_kopecks=integer(
                    data.get("amount", old["amount_kopecks"] if old else 0), "Сумма", 1
                ),
                internal_cost=0,
                itemized=0,
            )
        return result, items

    def save_items(self, qid, items):
        if items is None:
            return
        self.con.execute("DELETE FROM quote_items WHERE quote_id=?", (qid,))
        self.con.executemany(
            "INSERT INTO quote_items VALUES(?,?,?,?)",
            [(identity(), qid, i, packed(item)) for i, item in enumerate(items)],
        )

    def insert(self, table, values):
        keys = list(values)
        self.con.execute(
            f"INSERT INTO {table}({','.join(keys)}) VALUES({','.join('?' for _ in keys)})",
            tuple(values[k] for k in keys),
        )

    def update(self, table, record_id, values):
        self.con.execute(
            f"UPDATE {table} SET {','.join(k + '=?' for k in values)} WHERE id=? AND workspace_id=?",
            (*values.values(), record_id, self.wid),
        )

    def check_revision(self, row, data):
        if (
            type(data.get("revision")) is not int
            or data.get("revision") != row["revision"]
        ):
            raise DomainError(
                409, "Запись изменена. Обновите страницу перед сохранением"
            )

    def create_quote(self, data):
        owner = self.con.execute(
            "SELECT u.* FROM users u JOIN workspaces w ON w.owner_id=u.id WHERE w.id=?",
            (self.wid,),
        ).fetchone()
        count = self.con.execute(
            "SELECT count(*) FROM events WHERE user_id=? AND name='quote_created'",
            (owner["id"],),
        ).fetchone()[0]
        if count >= (10 if (owner["entitlement_until"] or 0) <= stamp() else 10000):
            raise DomainError(402, "Достигнут лимит смет текущего тарифа")
        values, items = self.quote_data(data)
        qid = identity()
        values.update(
            id=qid,
            user_id=owner["id"],
            workspace_id=self.wid,
            public_token=secrets.token_urlsafe(32),
            created_at=stamp(),
            updated_at=stamp(),
        )
        self.insert("quotes", values)
        self.save_items(qid, items)
        self.con.execute(
            "INSERT INTO events VALUES(?,?,?,?)",
            (identity(), owner["id"], "quote_created", stamp()),
        )
        self.emit("quote", qid, "Смета создана")
        return self.quote_view(self.get("quotes", qid))

    def publish(self, row, data):
        if row["status"] in ("accepted", "completed"):
            raise DomainError(
                409, "Согласованную смету нельзя отправить повторно: создайте копию"
            )
        if row["itemized"]:
            self.check_revision(row, data)
        if row["approval_state"] in ("sent", "viewed"):
            raise DomainError(409, "Эта версия уже отправлена")
        snapshot = self.quote_view(row)
        version = row["published_version"] + 1
        for key in (
            "public_url",
            "profit",
            "approval_state",
            "status",
            "published_version",
        ):
            snapshot.pop(key, None)
        snapshot["version"] = version
        self.con.execute(
            "INSERT INTO quote_versions VALUES(?,?,?,?,?,?)",
            (
                row["id"],
                version,
                packed(snapshot),
                self.user["id"],
                string(data.get("comment", ""), "Комментарий", 1000),
                stamp(),
            ),
        )
        self.update(
            "quotes",
            row["id"],
            dict(
                published_version=version,
                status="sent",
                approval_state="sent",
                sent_at=stamp(),
                updated_at=stamp(),
                revision=row["revision"] + 1,
            ),
        )
        self.emit("quote", row["id"], "Смета отправлена", f"v{version}")

    def public(self, method, path, query):
        data = self.h.body() if method == "POST" else {}
        token = data.get("token", query.get("token", [""])[0])
        token = string(token, "Ссылка", 100, True)
        self.h.throttle("public:" + self.h.client_address[0], 180, 60)
        with transaction(self.con):
            row = self.con.execute(
                "SELECT q.*,u.name AS author FROM quotes q JOIN users u ON u.id=q.user_id WHERE q.public_token=? AND u.blocked=0 AND u.deleted_at IS NULL",
                (token,),
            ).fetchone()
            if not row or not row["published_version"]:
                raise DomainError(404, "Предложение не найдено")
            self.wid = row["workspace_id"]
            public_quote = self.quote_view(row, True)
            if method == "GET" and path in ("/api/public/file", "/api/public/document"):
                if public_quote["approval_state"] == "expired":
                    raise DomainError(410, "Срок ссылки истёк")
                file_id = string(query.get("id", [""])[0], "Файл", 50, True)
                if path == "/api/public/file":
                    file = self.con.execute(
                        "SELECT * FROM files WHERE id=? AND quote_id=? AND workspace_id=? AND public=1",
                        (file_id, row["id"], self.wid),
                    ).fetchone()
                    if not file:
                        raise DomainError(404, "Файл не найден")
                    try:
                        from backend.attachments import download
                    except ModuleNotFoundError:
                        from attachments import download
                    return 200, download(file, self.con)
                document = self.con.execute(
                    "SELECT * FROM documents WHERE id=? AND quote_id=? AND workspace_id=?",
                    (file_id, row["id"], self.wid),
                ).fetchone()
                if not document:
                    raise DomainError(404, "Документ не найден")
                try:
                    from backend.documents import Download, pdf
                except ModuleNotFoundError:
                    from documents import Download, pdf
                return 200, Download(
                    pdf(document), "application/pdf", "smetra-document.pdf"
                )
            if method == "GET" and path == "/api/public/quote":
                state = (
                    "viewed"
                    if row["approval_state"] == "sent"
                    else row["approval_state"]
                )
                self.update(
                    "quotes",
                    row["id"],
                    dict(
                        view_count=row["view_count"] + 1,
                        first_viewed_at=row["first_viewed_at"] or stamp(),
                        approval_state=state,
                    ),
                )
                if row["view_count"] == 0:
                    self.emit("quote", row["id"], "Клиент открыл смету", notify=True)
                public_quote["approval_state"] = (
                    "viewed"
                    if public_quote["approval_state"] == "sent"
                    else public_quote["approval_state"]
                )
                project = self.con.execute(
                    "SELECT id,name,status,amount_kopecks,currency,due_date FROM projects WHERE quote_id=?",
                    (row["id"],),
                ).fetchone()
                result = dict(
                    quote=public_quote,
                    author=row["author"],
                    project={key: project[key] for key in ("name", "status", "amount_kopecks", "currency", "due_date")} if project else None,
                )
                result["comments"] = [
                    dict(r)
                    for r in self.con.execute(
                        "SELECT author,message,created_at FROM comments WHERE quote_id=? AND public=1 ORDER BY created_at DESC LIMIT 100",
                        (row["id"],),
                    )
                ]
                result["files"] = [
                    dict(f)
                    for f in self.con.execute(
                        "SELECT id,name,size FROM files WHERE quote_id=? AND public=1 ORDER BY created_at",
                        (row["id"],),
                    )
                ]
                result["documents"] = [
                    dict(d)
                    for d in self.con.execute(
                        "SELECT id,name,number FROM documents WHERE quote_id=? ORDER BY created_at DESC LIMIT 50",
                        (row["id"],),
                    )
                ]
                result["versions"] = [
                    dict(
                        version=v["version"],
                        comment=v["comment"],
                        created_at=v["created_at"],
                        amount_kopecks=json.loads(v["snapshot"])["amount_kopecks"],
                    )
                    for v in self.con.execute(
                        "SELECT * FROM quote_versions WHERE quote_id=? ORDER BY version DESC LIMIT 50",
                        (row["id"],),
                    )
                ]
                if project:
                    result["stages"] = [
                        {key: r[key] for key in ("name", "description", "due_date", "amount_kopecks", "status")}
                        for r in self.con.execute(
                            "SELECT id,name,description,due_date,amount_kopecks,status FROM project_stages WHERE project_id=? ORDER BY created_at",
                            (project["id"],),
                        )
                    ]
                    result["payments"] = [
                        dict(r)
                        for r in self.con.execute(
                            "SELECT amount_kopecks,payment_date,method FROM project_payments WHERE project_id=? ORDER BY created_at",
                            (project["id"],),
                        )
                    ]
                return 200, result
            if method != "POST" or path not in (
                "/api/public/accept",
                "/api/public/respond",
                "/api/public/comment",
            ):
                raise DomainError(404, "Не найдено")
            if public_quote["approval_state"] == "expired":
                raise DomainError(
                    410, "Срок предложения истёк. Запросите новую версию у исполнителя"
                )
            author = string(data.get("name", "Клиент"), "Ваше имя", 120, True)
            message = string(data.get("comment", ""), "Комментарий", 3000)
            if path == "/api/public/comment":
                if not message:
                    raise DomainError(400, "Напишите комментарий")
            else:
                if row["approval_state"] not in ("sent", "viewed", "changes_requested"):
                    raise DomainError(409, "Предложение уже обработано")
                if row["itemized"] and data.get("version") != row["published_version"]:
                    raise DomainError(
                        409,
                        "Появилась новая версия. Обновите предложение перед ответом",
                    )
                state = choice(
                    data.get("action", "approved"),
                    ("approved", "rejected", "changes_requested"),
                    "Ответ",
                )
                if state == "changes_requested" and not message:
                    raise DomainError(400, "Опишите необходимые изменения")
                self.update(
                    "quotes",
                    row["id"],
                    dict(
                        approval_state=state,
                        status={
                            "approved": "accepted",
                            "rejected": "declined",
                            "changes_requested": "sent",
                        }[state],
                        approved_at=stamp() if state == "approved" else None,
                        approved_by=author if state == "approved" else "",
                        updated_at=stamp(),
                        revision=row["revision"] + 1,
                    ),
                )
                self.emit(
                    "quote",
                    row["id"],
                    {
                        "approved": "Смета согласована",
                        "rejected": "Смета отклонена",
                        "changes_requested": "Запрошены изменения",
                    }[state],
                    f"{author}: {message}",
                    True,
                )
            if message:
                self.con.execute(
                    "INSERT INTO comments VALUES(?,?,?,?,?,?,?)",
                    (identity(), self.wid, row["id"], author, message, 1, stamp()),
                )
                self.emit("quote", row["id"], "Комментарий клиента", message, True)
            return 200, {"ok": True}

    def quotes(self, method, parts, query, data):
        if not parts:
            if method == "POST":
                return 201, {"quote": self.create_quote(data)}
            search = (
                "%"
                + query.get("q", [""])[0][:100]
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
                + "%"
            )
            rows = self.con.execute(
                "SELECT * FROM quotes WHERE workspace_id=? AND (title LIKE ? ESCAPE '\\' OR client LIKE ? ESCAPE '\\') ORDER BY updated_at DESC,id LIMIT 30 OFFSET ?",
                (self.wid, search, search, self.page(query)),
            ).fetchall()
            items_by_quote = {row["id"]: [] for row in rows}
            if rows:
                placeholders = ",".join("?" for _ in rows)
                for item in self.con.execute(
                    f"SELECT quote_id,data FROM quote_items WHERE quote_id IN ({placeholders}) ORDER BY quote_id,position",
                    tuple(items_by_quote),
                ):
                    items_by_quote[item["quote_id"]].append(json.loads(item["data"]))
            return 200, {
                "quotes": [
                    self.quote_view(row, prefetched_items=items_by_quote[row["id"]])
                    for row in rows
                ]
            }
        row = self.get("quotes", parts[0])
        action = parts[1] if len(parts) > 1 else ""
        if method == "GET":
            if action == "versions":
                return 200, {
                    "versions": [
                        dict(r, snapshot=json.loads(r["snapshot"]))
                        for r in self.con.execute(
                            "SELECT * FROM quote_versions WHERE quote_id=? ORDER BY version DESC",
                            (row["id"],),
                        )
                    ]
                }
            return 200, {
                "quote": self.quote_view(row),
                "activity": [
                    dict(r)
                    for r in self.con.execute(
                        "SELECT * FROM activity WHERE workspace_id=? AND entity_id=? ORDER BY created_at DESC LIMIT 100",
                        (self.wid, row["id"]),
                    )
                ],
            }
        if method == "DELETE":
            self.write_access(True)
            if self.con.execute(
                "SELECT 1 FROM projects WHERE quote_id=?", (row["id"],)
            ).fetchone():
                raise DomainError(409, "У сметы есть заказ. Сохраните её для истории")
            self.con.execute("DELETE FROM quotes WHERE id=?", (row["id"],))
            self.emit("quote", row["id"], "Смета удалена")
            return 200, {"ok": True}
        if method == "POST" and action == "copy":
            snapshot = self.quote_view(row)
            snapshot["title"] = snapshot["title"][:110] + " — копия"
            snapshot["amount"] = snapshot["amount_kopecks"]
            if not snapshot["items"]:
                snapshot.pop("items")
            return 201, {"quote": self.create_quote(snapshot)}
        if method == "POST" and action == "template":
            name = string(data.get("name", row["title"]), "Название", 120, True)
            tid = identity()
            self.con.execute(
                "INSERT INTO estimate_templates VALUES(?,?,?,?,?)",
                (tid, self.wid, name, packed(self.quote_view(row)), stamp()),
            )
            return 201, {"id": tid}
        if method == "POST" and action == "project":
            if row["approval_state"] != "approved":
                raise DomainError(409, "Сначала согласуйте смету")
            previous = self.con.execute(
                "SELECT * FROM projects WHERE quote_id=?", (row["id"],)
            ).fetchone()
            if previous:
                return 200, {"project": dict(previous)}
            pid = identity()
            self.insert(
                "projects",
                dict(
                    id=pid,
                    workspace_id=self.wid,
                    quote_id=row["id"],
                    quote_version=row["published_version"],
                    client_id=row["client_id"],
                    name=row["title"],
                    description=row["description"],
                    amount_kopecks=row["amount_kopecks"],
                    internal_cost=row["internal_cost"],
                    currency=row["currency"],
                    due_date=row["due_date"],
                    created_at=stamp(),
                    updated_at=stamp(),
                ),
            )
            self.emit("project", pid, "Заказ создан из сметы", row["id"])
            return 201, {"project": dict(self.get("projects", pid))}
        if method not in ("POST", "PATCH"):
            raise DomainError(405, "Метод не поддерживается")
        if data.get("status") == "sent" or action == "publish":
            self.publish(row, data)
        elif data.get("status") in ("declined", "completed"):
            status = data["status"]
            if (row["status"], status) not in (
                ("sent", "declined"),
                ("accepted", "completed"),
            ):
                raise DomainError(409, "Этот переход статуса недоступен")
            self.update(
                "quotes",
                row["id"],
                dict(
                    status=status,
                    approval_state="rejected" if status == "declined" else "approved",
                    revision=row["revision"] + 1,
                    updated_at=stamp(),
                ),
            )
            self.emit("quote", row["id"], "Статус изменён", status)
        elif method == "PATCH" and not action:
            self.check_revision(row, data)
            if row["approval_state"] == "approved":
                raise DomainError(
                    409, "Согласованная версия защищена от изменений. Создайте копию"
                )
            values, items = self.quote_data(data, row)
            values.update(
                revision=row["revision"] + 1,
                updated_at=stamp(),
                approval_state="draft",
                status="draft",
            )
            self.update("quotes", row["id"], values)
            self.save_items(row["id"], items)
            self.emit("quote", row["id"], "Черновик сметы изменён")
        else:
            raise DomainError(400, "Неизвестное действие")
        return 200, {"quote": self.quote_view(self.get("quotes", row["id"]))}

    def entity(self, kind, method, parts, query, data):
        config = ENTITIES[kind]
        table = config.get("table", kind)
        if method == "GET":
            if parts:
                result = dict(self.get(table, parts[0]))
                if kind == "projects":
                    result["stages"] = [
                        dict(r)
                        for r in self.con.execute(
                            "SELECT * FROM project_stages WHERE project_id=? AND workspace_id=? ORDER BY created_at",
                            (parts[0], self.wid),
                        )
                    ]
                    result["payments"] = [
                        dict(r)
                        for r in self.con.execute(
                            "SELECT * FROM project_payments WHERE project_id=? AND workspace_id=? ORDER BY created_at DESC",
                            (parts[0], self.wid),
                        )
                    ]
                    result["expenses"] = [
                        dict(r)
                        for r in self.con.execute(
                            "SELECT * FROM expenses WHERE project_id=? AND workspace_id=? ORDER BY created_at DESC",
                            (parts[0], self.wid),
                        )
                    ]
                    result["paid"] = sum(
                        p["amount_kopecks"] for p in result["payments"]
                    )
                    result["actual_cost"] = sum(
                        p["amount_kopecks"] for p in result["expenses"]
                    )
                if kind == "clients":
                    result["quotes"] = [
                        self.quote_view(r)
                        for r in self.con.execute(
                            "SELECT * FROM quotes WHERE client_id=? AND workspace_id=? ORDER BY updated_at DESC LIMIT 50",
                            (parts[0], self.wid),
                        )
                    ]
                    result["projects"] = [
                        dict(r)
                        for r in self.con.execute(
                            "SELECT * FROM projects WHERE client_id=? AND workspace_id=? ORDER BY updated_at DESC LIMIT 50",
                            (parts[0], self.wid),
                        )
                    ]
                return 200, {"item": result}
            conditions, params = ["workspace_id=?"], [self.wid]
            if query.get("q"):
                conditions.append("instr(lower(name),lower(?))>0")
                params.append(query["q"][0][:100])
            for key in ("project_id", "client_id", "status"):
                if query.get(key) and (
                    key in config.get("refs", {})
                    or key == "status"
                    and kind in ("projects", "stages", "tasks", "leads")
                ):
                    conditions.append(key + "=?")
                    params.append(query[key][0])
            rows = self.con.execute(
                f"SELECT * FROM {table} WHERE {' AND '.join(conditions)} ORDER BY updated_at DESC,id LIMIT 50 OFFSET ?",
                (*params, self.page(query)),
            )
            return 200, {"items": [dict(r) for r in rows]}
        if method == "DELETE":
            self.write_access(True)
            self.get(table, parts[0])
            if kind == "projects":
                raise DomainError(
                    409, "Заказ хранит финансовую историю. Используйте статус «Отменён»"
                )
            self.con.execute(
                f"DELETE FROM {table} WHERE id=? AND workspace_id=?",
                (parts[0], self.wid),
            )
            self.emit(kind, parts[0], "Запись удалена")
            return 200, {"ok": True}
        if method not in ("POST", "PATCH") or (method == "PATCH" and not parts):
            raise DomainError(405, "Метод не поддерживается")
        old = self.get(table, parts[0]) if parts else None
        if old:
            self.check_revision(old, data)
        values = {}
        for key, maximum in config["strings"].items():
            values[key] = string(
                data.get(key, old[key] if old else ("шт." if key == "unit" else "")),
                key,
                maximum,
                key in ("name", "unit"),
            )
        for key in config.get("money", ()):
            values[key] = integer(data.get(key, old[key] if old else 0), key)
        for key, options in config.get("choices", {}).items():
            values[key] = choice(
                data.get(key, old[key] if old else options[0]), options, key
            )
        for key, target in config["refs"].items():
            value = data.get(key, old[key] if old else None) or None
            if value:
                self.get(target, value)
            if kind == "stages" and key == "project_id" and not value:
                raise DomainError(400, "Выберите заказ")
            if old and kind == "stages" and value != old[key]:
                raise DomainError(409, "Этап нельзя переносить в другой заказ")
            values[key] = value
        if kind in ("projects", "stages", "tasks"):
            values["due_date"] = date_value(
                data.get("due_date", old["due_date"] if old else "")
            )
        if kind in ("projects", "stages", "leads"):
            settings = json.loads(
                self.con.execute(
                    "SELECT settings FROM workspaces WHERE id=?", (self.wid,)
                ).fetchone()[0]
            )
            options = (
                settings.get("pipeline", DEFAULT_PIPELINE)
                if kind == "leads"
                else settings.get("project_statuses", PROJECT_STATUSES)
            )
            values["status"] = choice(
                data.get("status", old["status"] if old else options[0]),
                options,
                "Статус",
            )
        if kind in ("stages", "tasks"):
            assignee = data.get("assignee", old["assignee"] if old else None) or None
            if (
                assignee
                and not self.con.execute(
                    "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?",
                    (self.wid, assignee),
                ).fetchone()
            ):
                raise DomainError(400, "Исполнитель не состоит в команде")
            values["assignee"] = assignee
        if kind == "projects":
            values["currency"] = choice(
                data.get("currency", old["currency"] if old else "RUB"),
                ("RUB", "USD", "EUR", "KZT", "BYN", "GBP"),
                "Валюта",
            )
            if (
                old
                and old["quote_id"]
                and any(
                    values[k] != old[k]
                    for k in (
                        "amount_kopecks",
                        "currency",
                        "internal_cost",
                        "client_id",
                    )
                )
            ):
                raise DomainError(
                    409, "Финансовые условия заказа зафиксированы согласованной сметой"
                )
        if kind in ("clients", "projects"):
            values["custom_fields"] = self.custom(
                kind,
                data.get(
                    "custom_fields", json.loads(old["custom_fields"]) if old else {}
                ),
            )
        if kind == "clients":
            tags = data.get("tags", json.loads(old["tags"]) if old else [])
            if not isinstance(tags, list) or len(tags) > 30:
                raise DomainError(400, "Некорректные теги")
            values["tags"] = packed([string(v, "Тег", 50, True) for v in tags])
        if kind == "catalog":
            values["tax"] = str(
                decimal(data.get("tax", old["tax"] if old else "0"), "Налог")
            )
            values["active"] = integer(
                data.get("active", old["active"] if old else 1), "Активность", 0, 1
            )
        values["updated_at"] = stamp()
        rid = old["id"] if old else identity()
        if old:
            values["revision"] = old["revision"] + 1
            self.update(table, rid, values)
        else:
            values.update(id=rid, workspace_id=self.wid, created_at=stamp())
            self.insert(table, values)
        self.emit(
            kind, rid, "Запись изменена" if old else "Запись создана", values["name"]
        )
        return (200 if old else 201), {"item": dict(self.get(table, rid))}

    def money(self, kind, method, query, data):
        table = "project_payments" if kind == "receipts" else "expenses"
        if method == "GET":
            return 200, {
                "items": [
                    dict(r)
                    for r in self.con.execute(
                        f"SELECT x.*,p.name,p.currency FROM {table} x JOIN projects p ON p.id=x.project_id WHERE x.workspace_id=? ORDER BY x.created_at DESC LIMIT 50 OFFSET ?",
                        (self.wid, self.page(query)),
                    )
                ]
            }
        if method != "POST":
            raise DomainError(405, "Финансовые записи не изменяются")
        self.write_access(True)
        project = self.get(
            "projects", string(data.get("project_id", ""), "Заказ", 50, True)
        )
        key = string(
            self.h.headers.get("Idempotency-Key", ""), "Ключ операции", 100, True
        )
        if len(key) < 16:
            raise DomainError(400, "Ключ операции слишком короткий")
        amount = integer(data.get("amount_kopecks"), "Сумма", 1)
        previous = self.con.execute(
            f"SELECT * FROM {table} WHERE workspace_id=? AND idempotency_key=?",
            (self.wid, key),
        ).fetchone()
        if previous:
            if (
                previous["project_id"] != project["id"]
                or previous["amount_kopecks"] != amount
            ):
                raise DomainError(409, "Ключ уже использован для другой операции")
            for key in (
                "stage_id",
                "method",
                "comment",
                "payment_date",
                "category",
                "expense_date",
            ):
                if (
                    key in data
                    and key in previous.keys()
                    and data[key] != previous[key]
                ):
                    raise DomainError(409, "Ключ уже использован для другой операции")
            return 200, {"item": dict(previous)}
        values = dict(
            id=identity(),
            workspace_id=self.wid,
            project_id=project["id"],
            amount_kopecks=amount,
            comment=string(data.get("comment", ""), "Комментарий"),
            idempotency_key=key,
            created_at=stamp(),
        )
        if kind == "receipts":
            paid = self.con.execute(
                "SELECT coalesce(sum(amount_kopecks),0) FROM project_payments WHERE project_id=?",
                (project["id"],),
            ).fetchone()[0]
            if amount + paid > project["amount_kopecks"]:
                raise DomainError(409, "Сумма превышает остаток по заказу")
            stage = data.get("stage_id") or None
            if stage:
                stage_row = self.get("project_stages", stage)
                if stage_row["project_id"] != project["id"]:
                    raise DomainError(400, "Этап относится к другому заказу")
                stage_paid = self.con.execute(
                    "SELECT coalesce(sum(amount_kopecks),0) FROM project_payments WHERE stage_id=?",
                    (stage,),
                ).fetchone()[0]
                if stage_paid + amount > stage_row["amount_kopecks"]:
                    raise DomainError(409, "Сумма превышает стоимость этапа")
            values.update(
                stage_id=stage,
                payment_date=date_value(
                    data.get("payment_date", dt.date.today().isoformat())
                ),
                method=choice(
                    data.get("method", "bank_transfer"),
                    ("bank_transfer", "cash", "external"),
                    "Способ оплаты",
                ),
            )
        else:
            values.update(
                category=string(data.get("category", ""), "Категория", 100, True),
                expense_date=date_value(
                    data.get("expense_date", dt.date.today().isoformat())
                ),
            )
        self.insert(table, values)
        self.emit(
            "project",
            project["id"],
            "Полученная оплата записана" if kind == "receipts" else "Расход записан",
            str(amount),
            True,
        )
        return 201, {"item": values}

    def overview(self, limit=30):
        project_totals = self.con.execute(
            "SELECT currency,sum(amount_kopecks) AS revenue,sum(internal_cost) AS planned_cost,count(*) AS projects FROM projects WHERE workspace_id=? AND status!=? GROUP BY currency",
            (self.wid, "cancelled"),
        ).fetchall()
        paid_by_currency = {}
        costs_by_currency = {}
        if project_totals:
            paid_by_currency = {
                row["currency"]: row["amount"]
                for row in self.con.execute(
                    "SELECT p.currency,coalesce(sum(x.amount_kopecks),0) AS amount FROM project_payments x JOIN projects p ON x.project_id=p.id WHERE x.workspace_id=? AND p.workspace_id=? GROUP BY p.currency",
                    (self.wid, self.wid),
                )
            }
            costs_by_currency = {
                row["currency"]: row["amount"]
                for row in self.con.execute(
                    "SELECT p.currency,coalesce(sum(x.amount_kopecks),0) AS amount FROM expenses x JOIN projects p ON x.project_id=p.id WHERE x.workspace_id=? AND p.workspace_id=? GROUP BY p.currency",
                    (self.wid, self.wid),
                )
            }
        currencies = []
        for row in project_totals:
            currency = row["currency"]
            paid = paid_by_currency.get(currency, 0)
            costs = costs_by_currency.get(currency, 0)
            currencies.append(
                dict(
                    row,
                    paid=paid,
                    actual_cost=costs,
                    cash_profit=paid - costs,
                    planned_profit=row["revenue"] - row["planned_cost"],
                    unpaid=max(0, row["revenue"] - paid),
                )
            )
        quotes = dict(
            self.con.execute(
                "SELECT count(*) AS total,sum(CASE WHEN approval_state IN ('sent','viewed','changes_requested') THEN 1 ELSE 0 END) AS waiting,sum(CASE WHEN approval_state='approved' THEN 1 ELSE 0 END) AS approved FROM quotes WHERE workspace_id=?",
                (self.wid,),
            ).fetchone()
        )
        deadlines = [
            dict(r)
            for r in self.con.execute(
                "SELECT id,name,due_date,status,'project' AS kind FROM projects WHERE workspace_id=? AND due_date!='' AND status NOT IN ('completed','cancelled') UNION ALL SELECT id,name,due_date,status,'task' FROM tasks WHERE workspace_id=? AND due_date!='' AND status!='done' ORDER BY due_date LIMIT ?",
                (self.wid, self.wid, limit),
            )
        ]
        return 200, dict(
            currencies=currencies,
            quotes=quotes,
            deadlines=deadlines,
            activity=[
                dict(r)
                for r in self.con.execute(
                    "SELECT a.*,u.name AS actor FROM activity a LEFT JOIN users u ON u.id=a.actor_id WHERE a.workspace_id=? ORDER BY a.created_at DESC,a.rowid DESC LIMIT ?",
                    (self.wid, limit),
                )
            ],
        )

    def workspace(self, method, parts, data):
        if parts and parts[0] == "members":
            if method == "GET":
                return 200, {
                    "items": [
                        dict(r)
                        for r in self.con.execute(
                            "SELECT m.user_id,m.role,u.name,u.email FROM workspace_members m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=?",
                            (self.wid,),
                        )
                    ]
                }
            if self.role not in ("owner", "admin"):
                raise DomainError(
                    403, "Только владелец или администратор может управлять командой"
                )
            if method == "POST":
                email = string(data.get("email", ""), "Почта", 254, True).lower()
                member = self.con.execute(
                    "SELECT id FROM users WHERE email=? AND deleted_at IS NULL AND blocked=0",
                    (email,),
                ).fetchone()
                if not member:
                    raise DomainError(
                        404, "Пользователь должен сначала зарегистрироваться в Сметре"
                    )
                role = choice(
                    data.get("role"), ("admin", "manager", "member", "viewer"), "Роль"
                )
                existing = self.con.execute(
                    "SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                    (self.wid, member["id"]),
                ).fetchone()
                if (
                    existing
                    and existing["role"] == "owner"
                    or self.role == "admin"
                    and (role == "admin" or existing and existing["role"] == "admin")
                ):
                    raise DomainError(403, "Эта роль доступна только владельцу")
                self.con.execute(
                    "INSERT INTO workspace_members VALUES(?,?,?) ON CONFLICT(workspace_id,user_id) DO UPDATE SET role=excluded.role",
                    (self.wid, member["id"], role),
                )
                self.emit("workspace", self.wid, "Роль участника изменена", role)
                return 200, {"ok": True}
            if method == "DELETE" and len(parts) == 2:
                target = self.con.execute(
                    "SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                    (self.wid, parts[1]),
                ).fetchone()
                if target and (
                    target["role"] == "owner"
                    or self.role == "admin"
                    and target["role"] == "admin"
                ):
                    raise DomainError(403, "Нельзя удалить этого участника")
                self.con.execute(
                    "DELETE FROM workspace_members WHERE workspace_id=? AND user_id=?",
                    (self.wid, parts[1]),
                )
                self.emit("workspace", self.wid, "Участник удалён")
                return 200, {"ok": True}
        row = self.con.execute(
            "SELECT * FROM workspaces WHERE id=?", (self.wid,)
        ).fetchone()
        if method == "PATCH":
            if self.role not in ("owner", "admin"):
                raise DomainError(403, "Недостаточно прав")
            settings = json.loads(row["settings"])
            if "settings" in data:
                if not isinstance(data["settings"], dict):
                    raise DomainError(400, "Некорректные настройки")
                for key in ("pipeline", "project_statuses"):
                    if key in data["settings"]:
                        values = data["settings"][key]
                        if not isinstance(values, list) or not 2 <= len(values) <= 20:
                            raise DomainError(400, "Добавьте от 2 до 20 статусов")
                        settings[key] = list(
                            dict.fromkeys(string(v, "Статус", 60, True) for v in values)
                        )
                        if key == "project_statuses" and not set(
                            PROJECT_STATUSES
                        ).issubset(settings[key]):
                            raise DomainError(400, "Сохраните базовые статусы проектов")
                for key in ("company_details", "document_footer"):
                    if key in data["settings"]:
                        settings[key] = string(data["settings"][key], key, 3000)
            self.con.execute(
                "UPDATE workspaces SET name=?,currency=?,settings=? WHERE id=?",
                (
                    string(data.get("name", row["name"]), "Название", 120, True),
                    choice(
                        data.get("currency", row["currency"]),
                        ("RUB", "USD", "EUR", "KZT", "BYN", "GBP"),
                        "Валюта",
                    ),
                    packed(settings),
                    self.wid,
                ),
            )
            self.emit("workspace", self.wid, "Настройки изменены")
            row = self.con.execute(
                "SELECT * FROM workspaces WHERE id=?", (self.wid,)
            ).fetchone()
        return 200, {
            "workspace": dict(
                row, settings=json.loads(row["settings"]), role=self.role
            ),
            "workspaces": [
                dict(r)
                for r in self.con.execute(
                    "SELECT w.id,w.name,m.role FROM workspaces w JOIN workspace_members m ON m.workspace_id=w.id WHERE m.user_id=?",
                    (self.user["id"],),
                )
            ],
        }

    def handle(self, method, path, query):
        if path.startswith("/api/public/"):
            return self.public(method, path, query)
        self.user = self.h.auth(self.con)
        default = ensure_workspace(self.con, self.user)
        self.wid = self.h.headers.get("X-Workspace-Id", default)
        member = self.con.execute(
            "SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
            (self.wid, self.user["id"]),
        ).fetchone()
        if not member:
            raise DomainError(404, "Рабочее пространство не найдено")
        self.role = member["role"]
        parts = path.removeprefix("/api/").strip("/").split("/")
        kind, rest = parts[0], parts[1:]
        data = self.h.body() if method in ("POST", "PATCH") else {}
        if method != "GET":
            self.write_access()
            if kind == "assistant":
                from backend.assistant import route

                return route(self, method, rest, data)
            if kind == "ai" and method == "POST":
                try:
                    from backend.ai import draft
                except ModuleNotFoundError:
                    from ai import draft
                return draft(self, data)
            self.h.throttle("write:" + self.user["id"], 120, 60)
            with transaction(self.con):
                return self.route(method, kind, rest, query, data)
        return self.route(method, kind, rest, query, data)

    def route(self, method, kind, parts, query, data):
        if kind == "dashboard" and method == "GET":
            _, context = self.workspace("GET", [], {})
            _, overview = self.overview(limit=4)
            _, capabilities = self.route("GET", "capabilities", [], {}, {})
            rows = self.con.execute(
                "SELECT id,title,client,amount_kopecks,currency,approval_state,published_version,expires_at FROM quotes WHERE workspace_id=? ORDER BY updated_at DESC,id LIMIT 5",
                (self.wid,),
            ).fetchall()
            recent = []
            for row in rows:
                quote = dict(row)
                if quote["expires_at"] and quote["expires_at"] < stamp() and quote["approval_state"] in ("sent", "viewed", "changes_requested"):
                    quote["approval_state"] = "expired"
                recent.append(quote)
            return 200, {**context, "overview": overview, "capabilities": capabilities, "quotes": recent}
        if kind == "assistant":
            from backend.assistant import route

            return route(self, method, parts, data)
        if kind == "capabilities" and method == "GET":
            try:
                from backend.ai import available
            except ModuleNotFoundError:
                from ai import available
            return 200, {
                "ai_drafting": available(),
                "online_client_payments": False,
                "uploads": ["png", "jpg", "pdf", "txt"],
            }
        if kind == "files":
            try:
                from backend.attachments import route
            except ModuleNotFoundError:
                from attachments import route
            return route(self, method, parts, query, data)
        if kind in ("documents", "transfer"):
            try:
                from backend import documents
            except ModuleNotFoundError:
                import documents
            fn = documents.documents if kind == "documents" else documents.transfer
            return fn(self, method, parts, query, data)
        if kind == "workspace":
            return self.workspace(method, parts, data)
        if kind == "quotes":
            return self.quotes(method, parts, query, data)
        if kind in ENTITIES:
            return self.entity(kind, method, parts, query, data)
        if kind in ("receipts", "expenses"):
            return self.money(kind, method, query, data)
        if kind == "overview" and method == "GET":
            return self.overview()
        if kind == "search" and method == "GET":
            term = string(query.get("q", [""])[0], "Поиск", 100)
            results = []
            if len(term) >= 2:
                for table, name, typ in (
                    ("clients", "name", "clients"),
                    ("quotes", "title", "quotes"),
                    ("projects", "name", "projects"),
                    ("catalog_items", "name", "catalog"),
                    ("documents", "name", "documents"),
                ):
                    results.extend(
                        dict(r, kind=typ)
                        for r in self.con.execute(
                            f"SELECT id,{name} AS name FROM {table} WHERE workspace_id=? AND instr(lower({name}),lower(?))>0 LIMIT 10",
                            (self.wid, term),
                        )
                    )
            return 200, {"items": results}
        if kind == "activity" and method == "GET":
            return 200, {
                "items": [
                    dict(r)
                    for r in self.con.execute(
                        "SELECT * FROM activity WHERE workspace_id=? ORDER BY created_at DESC,rowid DESC LIMIT 50 OFFSET ?",
                        (self.wid, self.page(query)),
                    )
                ]
            }
        if kind == "notifications":
            if method == "POST":
                self.con.execute(
                    "INSERT OR IGNORE INTO notification_reads SELECT id,? FROM notifications WHERE workspace_id=?",
                    (self.user["id"], self.wid),
                )
                return 200, {"ok": True}
            return 200, {
                "items": [
                    dict(r)
                    for r in self.con.execute(
                        "SELECT n.*,r.user_id IS NOT NULL AS is_read FROM notifications n LEFT JOIN notification_reads r ON r.notification_id=n.id AND r.user_id=? WHERE n.workspace_id=? ORDER BY n.created_at DESC LIMIT 50",
                        (self.user["id"], self.wid),
                    )
                ]
            }
        if kind == "custom-fields":
            if method == "GET":
                return 200, {
                    "items": [
                        dict(r)
                        for r in self.con.execute(
                            "SELECT * FROM custom_field_definitions WHERE workspace_id=?",
                            (self.wid,),
                        )
                    ]
                }
            if method == "POST":
                self.write_access(True)
                typ = choice(
                    data.get("type"),
                    (
                        "text",
                        "number",
                        "date",
                        "select",
                        "multi_select",
                        "checkbox",
                        "url",
                    ),
                    "Тип",
                )
                entity = choice(
                    data.get("entity_type"),
                    ("clients", "estimates", "projects"),
                    "Сущность",
                )
                options = data.get("options", [])
                if not isinstance(options, list) or len(options) > 50:
                    raise DomainError(400, "Некорректные варианты")
                options = [string(v, "Вариант", 120, True) for v in options]
                if typ in ("select", "multi_select") and not options:
                    raise DomainError(400, "Укажите варианты выбора")
                fid = identity()
                self.con.execute(
                    "INSERT INTO custom_field_definitions VALUES(?,?,?,?,?,?,?)",
                    (
                        fid,
                        self.wid,
                        entity,
                        string(data.get("name", ""), "Название", 120, True),
                        typ,
                        packed(options),
                        stamp(),
                    ),
                )
                return 201, {"id": fid}
        if kind == "templates":
            if method == "GET":
                return 200, {
                    "items": [
                        dict(r)
                        for r in self.con.execute(
                            "SELECT id,name,created_at FROM estimate_templates WHERE workspace_id=? ORDER BY created_at DESC LIMIT 50",
                            (self.wid,),
                        )
                    ]
                }
            if method == "POST" and parts:
                row = self.get("estimate_templates", parts[0])
                snapshot = json.loads(row["snapshot"])
                snapshot.update(data)
                snapshot["amount"] = snapshot["amount_kopecks"]
                if not snapshot.get("items"):
                    snapshot.pop("items", None)
                return 201, {"quote": self.create_quote(snapshot)}
        if kind == "comments":
            row = self.get(
                "quotes", data.get("quote_id", query.get("quote_id", [""])[0])
            )
            if method == "GET":
                return 200, {
                    "items": [
                        dict(r)
                        for r in self.con.execute(
                            "SELECT * FROM comments WHERE quote_id=? ORDER BY created_at DESC LIMIT 100",
                            (row["id"],),
                        )
                    ]
                }
            if method == "POST":
                message = string(data.get("message", ""), "Комментарий", 3000, True)
                cid = identity()
                self.con.execute(
                    "INSERT INTO comments VALUES(?,?,?,?,?,?,?)",
                    (
                        cid,
                        self.wid,
                        row["id"],
                        self.user["name"],
                        message,
                        integer(data.get("public", 1), "Видимость", 0, 1),
                        stamp(),
                    ),
                )
                self.emit("quote", row["id"], "Комментарий исполнителя", message)
                return 201, {"id": cid}
        raise DomainError(404, "Не найдено")


ROUTES = set(ENTITIES) | {
    "dashboard",
    "assistant",
    "workspace",
    "quotes",
    "public",
    "overview",
    "receipts",
    "expenses",
    "search",
    "activity",
    "notifications",
    "custom-fields",
    "templates",
    "comments",
    "documents",
    "transfer",
    "files",
    "ai",
    "capabilities",
}
