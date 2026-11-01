"""«Что нового»: product updates in Markdown with views and reactions.

Posts are global (not tied to a workspace). Everyone signed in reads them, records one view
and at most one reaction per post; only administrators publish, edit and remove posts.
All queries run on the server connection: the runtime role has no access to these tables.
"""
import re

from backend.app import audit, now, uid
from backend.business import DomainError as ApiError

REACTIONS = ("up", "love", "fire", "down")
POST = re.compile(r"/api/changelog/([A-Za-z0-9_-]{8,64})(?:/(view|reaction))?")


def handles(path):
    return path in ("/api/changelog", "/api/changelog/unread") or bool(POST.fullmatch(path))


def _text(value, label, limit, required=True):
    text = str(value or "").strip()
    if required and not text:
        raise ApiError(400, f"Заполните поле «{label}»")
    if len(text) > limit:
        raise ApiError(400, f"Поле «{label}» слишком длинное")
    return text


def _post(con, post_id):
    row = con.execute("SELECT * FROM changelog_posts WHERE id=? AND deleted_at IS NULL", (post_id,)).fetchone()
    if not row:
        raise ApiError(404, "Публикация не найдена")
    return row


def posts(con, user_id, limit=30):
    rows = con.execute(
        "SELECT id,title,body,tag,published_at,updated_at FROM changelog_posts WHERE deleted_at IS NULL "
        "ORDER BY published_at DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    ids = [row["id"] for row in rows]
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    views = {r["post_id"]: r["n"] for r in con.execute(
        f"SELECT post_id, count(*) AS n FROM changelog_views WHERE post_id IN ({marks}) GROUP BY post_id", ids)}
    seen = {r["post_id"] for r in con.execute(
        f"SELECT post_id FROM changelog_views WHERE user_id=? AND post_id IN ({marks})", [user_id, *ids])}
    reactions = {}
    for r in con.execute(
            f"SELECT post_id, reaction, count(*) AS n FROM changelog_reactions WHERE post_id IN ({marks}) GROUP BY post_id, reaction", ids):
        reactions.setdefault(r["post_id"], {})[r["reaction"]] = r["n"]
    mine = {r["post_id"]: r["reaction"] for r in con.execute(
        f"SELECT post_id, reaction FROM changelog_reactions WHERE user_id=? AND post_id IN ({marks})", [user_id, *ids])}
    return [{**dict(row), "views": views.get(row["id"], 0), "seen": row["id"] in seen,
             "reactions": {key: reactions.get(row["id"], {}).get(key, 0) for key in REACTIONS},
             "my_reaction": mine.get(row["id"])} for row in rows]


def unread(con, user_id):
    return con.execute(
        "SELECT count(*) FROM changelog_posts p WHERE p.deleted_at IS NULL AND NOT EXISTS "
        "(SELECT 1 FROM changelog_views v WHERE v.post_id=p.id AND v.user_id=?)", (user_id,)
    ).fetchone()[0]


def route(handler, method, path, query, con):
    user = handler.auth(con)
    admin = user["role"] == "admin"
    if path == "/api/changelog/unread" and method == "GET":
        return handler.send_json(200, {"unread": unread(con, user["id"])})
    if path == "/api/changelog":
        if method == "GET":
            return handler.send_json(200, {"items": posts(con, user["id"]), "can_publish": admin, "reactions": list(REACTIONS)})
        if method == "POST":
            if not admin:
                raise ApiError(403, "Публиковать обновления могут только администраторы")
            data = handler.body()
            post_id, moment = uid(), now()
            values = (post_id, _text(data.get("title"), "Заголовок", 140), _text(data.get("body"), "Текст", 20000),
                      _text(data.get("tag"), "Метка", 40, False), user["id"], moment, moment)
            con.execute("INSERT INTO changelog_posts(id,title,body,tag,author_id,published_at,updated_at) VALUES(?,?,?,?,?,?,?)", values)
            audit(con, user["id"], "changelog.published", post_id, values[1])
            return handler.send_json(201, {"id": post_id})
        raise ApiError(405, "Метод не поддерживается")
    match = POST.fullmatch(path)
    post_id, action = match[1], match[2]
    post = _post(con, post_id)
    if action == "view" and method == "POST":
        handler.throttle("changelog-view:" + user["id"], 120, 60)
        con.execute("INSERT INTO changelog_views(post_id,user_id,viewed_at) VALUES(?,?,?) ON CONFLICT(post_id,user_id) DO NOTHING",
                    (post["id"], user["id"], now()))
        return handler.send_json(200, {"ok": True})
    if action == "reaction" and method == "POST":
        handler.throttle("changelog-reaction:" + user["id"], 60, 60)
        reaction = handler.body().get("reaction")
        if reaction is None:
            con.execute("DELETE FROM changelog_reactions WHERE post_id=? AND user_id=?", (post["id"], user["id"]))
        elif reaction in REACTIONS:
            con.execute("INSERT INTO changelog_reactions(post_id,user_id,reaction,created_at) VALUES(?,?,?,?) "
                        "ON CONFLICT(post_id,user_id) DO UPDATE SET reaction=excluded.reaction, created_at=excluded.created_at",
                        (post["id"], user["id"], reaction, now()))
        else:
            raise ApiError(400, "Неизвестная реакция")
        item = next(p for p in posts(con, user["id"], 200) if p["id"] == post["id"])
        return handler.send_json(200, {"reactions": item["reactions"], "my_reaction": item["my_reaction"]})
    if action is None and method in ("PATCH", "DELETE"):
        if not admin:
            raise ApiError(403, "Изменять обновления могут только администраторы")
        if method == "DELETE":
            con.execute("UPDATE changelog_posts SET deleted_at=? WHERE id=?", (now(), post["id"]))
            audit(con, user["id"], "changelog.removed", post["id"], post["title"])
            return handler.send_json(200, {"ok": True})
        data = handler.body()
        con.execute("UPDATE changelog_posts SET title=?, body=?, tag=?, updated_at=? WHERE id=?",
                    (_text(data.get("title"), "Заголовок", 140), _text(data.get("body"), "Текст", 20000),
                     _text(data.get("tag"), "Метка", 40, False), now(), post["id"]))
        audit(con, user["id"], "changelog.edited", post["id"], post["title"])
        return handler.send_json(200, {"ok": True})
    raise ApiError(405, "Метод не поддерживается")
