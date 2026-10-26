"""Partner console access through Smetra accounts.

A person signs in to the console with the same account as on smetra.online
(email or Yandex ID). smetra.online, which holds the account session cookie,
issues a one-time code; the console exchanges it for a one-hour console
session bound to that user and one partner. The role is read from
partner_members on every request, so removing someone takes effect at once.

Roles:
- owner   — everything, including the team and other owners;
- admin   — everything, team except owners;
- analyst — read-only: statistics, catalog, commissions;
- catalog — catalog, domain and store events; no money or statistics.
Server API keys keep working for SDKs and act with full rights, except the
team, which needs a person.
"""
import hashlib
import re
import secrets
import time
import uuid

from backend.partner_platform import PartnerError

ROLES = ("owner", "admin", "analyst", "catalog")
ROLE_LABELS = {"owner": "Владелец", "admin": "Администратор", "analyst": "Аналитик", "catalog": "Каталог"}
EVERYONE = frozenset(ROLES) | {"key"}
PERMISSIONS = {
    "profile": EVERYONE,
    "summary": frozenset({"owner", "admin", "analyst", "key"}),
    "analytics": frozenset({"owner", "admin", "analyst", "key"}),
    "commissions": frozenset({"owner", "admin", "analyst", "key"}),
    "products": EVERYONE,
    "catalog_write": frozenset({"owner", "admin", "catalog", "key"}),
    "domain": EVERYONE,
    "domain_write": frozenset({"owner", "admin", "catalog", "key"}),
    "events": frozenset({"owner", "admin", "catalog", "key"}),
    "team": frozenset({"owner", "admin"}),
}
SSO_TTL = 120
INVITE_TTL = 14 * 86400
SESSION_TTL = 3600
EMAIL_RE = re.compile(r"[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}\Z")


def _now():
    return int(time.time())


def _sha(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _email(value):
    if not isinstance(value, str) or not EMAIL_RE.fullmatch(value.strip()):
        raise PartnerError(400, "Некорректная почта")
    return value.strip().lower()


def _role(value, allow_owner=True):
    if value not in ROLES or (value == "owner" and not allow_owner):
        raise PartnerError(400, "Некорректная роль")
    return value


def require(role, action):
    if role not in PERMISSIONS[action]:
        raise PartnerError(403, "Недостаточно прав для этого раздела")


# --- Sign in -----------------------------------------------------------------

def begin_sso(con, user):
    """Called on smetra.online with the account session. Returns a one-time code."""
    if user["blocked"] or user["deleted_at"] is not None:
        raise PartnerError(403, "Аккаунт недоступен")
    code = secrets.token_urlsafe(32)
    moment = _now()
    con.execute("DELETE FROM partner_sso_codes WHERE expires_at<?", (moment - 3600,))
    con.execute("INSERT INTO partner_sso_codes(code_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)",
                (_sha(code), user["id"], moment, moment + SSO_TTL))
    return code


def accept_invites(con, user):
    """Pending invitations to this user's confirmed email become memberships."""
    if not user["email_verified_at"]:
        return 0
    moment = _now()
    email = str(user["email"] or "").lower()
    rows = con.execute(
        "SELECT i.id,i.partner_id,i.role,i.created_by FROM partner_invites i "
        "JOIN partner_accounts p ON p.id=i.partner_id "
        "WHERE i.email=? AND i.accepted_at IS NULL AND i.revoked_at IS NULL AND i.expires_at>? AND p.active=1",
        (email, moment),
    ).fetchall()
    for row in rows:
        con.execute(
            "INSERT INTO partner_members(partner_id,user_id,role,invited_by,created_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(partner_id,user_id) DO NOTHING",
            (row["partner_id"], user["id"], row["role"], row["created_by"], moment),
        )
        con.execute("UPDATE partner_invites SET accepted_at=?,accepted_by=? WHERE id=?", (moment, user["id"], row["id"]))
    return len(rows)


def memberships(con, user_id):
    rows = con.execute(
        "SELECT p.id,p.code,p.name,p.allowed_host,m.role FROM partner_members m "
        "JOIN partner_accounts p ON p.id=m.partner_id WHERE m.user_id=? AND p.active=1 ORDER BY p.name",
        (user_id,),
    ).fetchall()
    return [{"id": r["id"], "code": r["code"], "name": r["name"], "domain": r["allowed_host"],
             "role": r["role"], "role_label": ROLE_LABELS[r["role"]]} for r in rows]


def exchange_sso(con, code, partner_id=None):
    """Console side. With several partners the code is kept until one is chosen."""
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{40,60}", code):
        raise PartnerError(401, "Ссылка входа недействительна. Войдите снова")
    moment = _now()
    row = con.execute(
        "SELECT c.user_id,u.* FROM partner_sso_codes c JOIN users u ON u.id=c.user_id "
        "WHERE c.code_hash=? AND c.used_at IS NULL AND c.expires_at>?",
        (_sha(code), moment),
    ).fetchone()
    if not row or row["blocked"] or row["deleted_at"] is not None:
        raise PartnerError(401, "Ссылка входа устарела. Войдите снова")
    accept_invites(con, row)
    options = memberships(con, row["user_id"])
    if not options:
        con.execute("UPDATE partner_sso_codes SET used_at=? WHERE code_hash=?", (moment, _sha(code)))
        raise PartnerError(403, "У этого аккаунта нет доступа к кабинету партнёра. Попросите владельца пригласить вашу почту")
    if partner_id is None and len(options) > 1:
        return {"choose": options, "user": {"name": row["name"], "email": row["email"]}}
    chosen = options[0] if partner_id is None else next((o for o in options if o["id"] == partner_id), None)
    if not chosen:
        raise PartnerError(403, "Нет доступа к этому партнёру")
    used = con.execute("UPDATE partner_sso_codes SET used_at=? WHERE code_hash=? AND used_at IS NULL",
                       (moment, _sha(code))).rowcount
    if not used:
        raise PartnerError(401, "Ссылка входа уже использована. Войдите снова")
    token = "smp_session_" + secrets.token_urlsafe(36)
    con.execute(
        "INSERT INTO partner_console_sessions(id,partner_id,user_id,session_hash,created_at,expires_at) VALUES(?,?,?,?,?,?)",
        (str(uuid.uuid4()), chosen["id"], row["user_id"], _sha(token), moment, moment + SESSION_TTL),
    )
    return {"session_token": token, "expires_in": SESSION_TTL, "partner": chosen}


def console_access(con, header):
    """Account, role and user for a console request; the role is re-read every time."""
    from backend import partner_platform as partner

    if isinstance(header, str) and header.startswith("Partner smp_live_"):
        return partner.auth_partner(con, header), "key", None
    if not isinstance(header, str) or not re.fullmatch(r"PartnerSession smp_session_[A-Za-z0-9_-]{35,100}\Z", header):
        raise PartnerError(401, "Войдите в кабинет партнёра")
    row = con.execute(
        "SELECT p.*,s.user_id AS session_user,m.role AS member_role FROM partner_console_sessions s "
        "JOIN partner_accounts p ON p.id=s.partner_id "
        "LEFT JOIN partner_members m ON m.partner_id=s.partner_id AND m.user_id=s.user_id "
        "LEFT JOIN users u ON u.id=s.user_id "
        "WHERE s.session_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND p.active=1 "
        "AND (s.user_id IS NULL OR (m.role IS NOT NULL AND u.blocked=0 AND u.deleted_at IS NULL))",
        (_sha(header[len("PartnerSession "):]), _now()),
    ).fetchone()
    if not row:
        raise PartnerError(401, "Сессия истекла")
    account = con.execute("SELECT * FROM partner_accounts WHERE id=?", (row["id"],)).fetchone()
    # A session opened with an API key keeps the key's full rights.
    return account, row["member_role"] or "key", row["session_user"]


def me(con, account, role, user_id):
    person = con.execute("SELECT name,email FROM users WHERE id=?", (user_id,)).fetchone() if user_id else None
    return {
        "role": role,
        "role_label": ROLE_LABELS.get(role, "Ключ API"),
        "permissions": sorted(action for action, roles in PERMISSIONS.items() if role in roles),
        "user": {"name": person["name"], "email": person["email"]} if person else None,
        "partners": memberships(con, user_id) if user_id else [],
    }


# --- Team ----------------------------------------------------------------------

def team(con, account):
    members = con.execute(
        "SELECT m.user_id,m.role,m.created_at,u.name,u.email FROM partner_members m JOIN users u ON u.id=m.user_id "
        "WHERE m.partner_id=? ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,u.name",
        (account["id"],),
    ).fetchall()
    invites = con.execute(
        "SELECT id,email,role,created_at,expires_at FROM partner_invites "
        "WHERE partner_id=? AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at>? ORDER BY created_at DESC",
        (account["id"], _now()),
    ).fetchall()
    return {
        "members": [{"user_id": m["user_id"], "name": m["name"], "email": m["email"], "role": m["role"],
                     "role_label": ROLE_LABELS[m["role"]], "since": m["created_at"]} for m in members],
        "invites": [{**dict(i), "role_label": ROLE_LABELS[i["role"]]} for i in invites],
        "roles": [{"id": r, "label": ROLE_LABELS[r]} for r in ROLES],
    }


def _owners(con, partner_id):
    return con.execute("SELECT count(*) FROM partner_members WHERE partner_id=? AND role='owner'", (partner_id,)).fetchone()[0]


def invite(con, account, actor_role, actor_id, data):
    if not isinstance(data, dict) or set(data) != {"email", "role"}:
        raise PartnerError(400, "Укажите почту и роль")
    email = _email(data["email"])
    role = _role(data["role"], allow_owner=actor_role == "owner")
    existing = con.execute(
        "SELECT 1 FROM partner_members m JOIN users u ON u.id=m.user_id WHERE m.partner_id=? AND lower(u.email)=?",
        (account["id"], email),
    ).fetchone()
    if existing:
        raise PartnerError(409, "Этот человек уже в команде")
    pending = con.execute(
        "SELECT count(*) FROM partner_invites WHERE partner_id=? AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at>?",
        (account["id"], _now()),
    ).fetchone()[0]
    if pending >= 50:
        raise PartnerError(429, "Слишком много неподтверждённых приглашений")
    moment = _now()
    con.execute("UPDATE partner_invites SET revoked_at=? WHERE partner_id=? AND email=? AND accepted_at IS NULL AND revoked_at IS NULL",
                (moment, account["id"], email))
    invite_id = str(uuid.uuid4())
    con.execute(
        "INSERT INTO partner_invites(id,partner_id,email,role,created_by,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
        (invite_id, account["id"], email, role, actor_id, moment, moment + INVITE_TTL),
    )
    return {"id": invite_id, "email": email, "role": role, "expires_at": moment + INVITE_TTL}


def revoke_invite(con, account, invite_id):
    changed = con.execute(
        "UPDATE partner_invites SET revoked_at=? WHERE id=? AND partner_id=? AND accepted_at IS NULL AND revoked_at IS NULL",
        (_now(), invite_id, account["id"]),
    ).rowcount
    if not changed:
        raise PartnerError(404, "Приглашение не найдено")
    return {"ok": True}


def _member(con, account, user_id):
    row = con.execute("SELECT role FROM partner_members WHERE partner_id=? AND user_id=?", (account["id"], user_id)).fetchone()
    if not row:
        raise PartnerError(404, "Участник не найден")
    return row["role"]


def change_role(con, account, actor_role, actor_id, user_id, data):
    if not isinstance(data, dict) or set(data) != {"role"}:
        raise PartnerError(400, "Укажите роль")
    current = _member(con, account, user_id)
    role = _role(data["role"], allow_owner=actor_role == "owner")
    if current == "owner" and actor_role != "owner":
        raise PartnerError(403, "Менять владельца может только владелец")
    if current == "owner" and role != "owner" and _owners(con, account["id"]) <= 1:
        raise PartnerError(409, "Нужен хотя бы один владелец")
    con.execute("UPDATE partner_members SET role=? WHERE partner_id=? AND user_id=?", (role, account["id"], user_id))
    return {"user_id": user_id, "role": role}


def remove_member(con, account, actor_role, actor_id, user_id):
    current = _member(con, account, user_id)
    if current == "owner" and actor_role != "owner":
        raise PartnerError(403, "Удалить владельца может только владелец")
    if current == "owner" and _owners(con, account["id"]) <= 1:
        raise PartnerError(409, "Нельзя удалить последнего владельца")
    con.execute("DELETE FROM partner_members WHERE partner_id=? AND user_id=?", (account["id"], user_id))
    con.execute("UPDATE partner_console_sessions SET revoked_at=? WHERE partner_id=? AND user_id=? AND revoked_at IS NULL",
                (_now(), account["id"], user_id))
    return {"ok": True, "self": user_id == actor_id}


# --- Administrator -------------------------------------------------------------

def admin_invite_owner(con, partner_id, email):
    """Smetra administrator gives a partner its first owner by email."""
    account = con.execute("SELECT * FROM partner_accounts WHERE id=?", (partner_id,)).fetchone()
    if not account:
        raise PartnerError(404, "Партнёр не найден")
    return invite(con, account, "owner", None, {"email": email, "role": "owner"})
