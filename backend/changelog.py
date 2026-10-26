"""Authenticated product release notes with per-user, idempotent views/reactions."""
from backend.business import DomainError, identity, integer, stamp, string

def _admin(service):
    if service.user["role"] != "admin":
        raise DomainError(403, "Публикация обновлений доступна только администратору")

def _row(service, update_id, include_draft=False):
    row = service.con.execute(
        "SELECT * FROM product_updates WHERE id=?",
        (update_id,),
    ).fetchone()
    if not row or (not row["published"] and not (include_draft and service.user["role"] == "admin")):
        raise DomainError(404, "Обновление не найдено")
    return row

def route(service, method, parts, query, data):
    if method == "GET" and not parts:
        admin = service.user["role"] == "admin"
        rows = service.con.execute(
            "SELECT u.id,u.title,u.version,u.body,u.published,u.published_at,u.updated_at,"
            "u.view_count,u.likes,u.dislikes,"
            "(SELECT r.reaction FROM product_update_reactions r "
            " WHERE r.update_id=u.id AND r.user_id=?) AS my_reaction "
            "FROM product_updates u "
            + ("" if admin else "WHERE u.published=1 ")
            + "ORDER BY u.published_at DESC,u.id DESC LIMIT 80",
            (service.user["id"],),
        ).fetchall()
        return 200, {"items":[dict(r) for r in rows], "can_publish":admin}
    if method == "POST" and not parts:
        _admin(service)
        title = string(data.get("title"), "Заголовок", 160, True)
        version = string(data.get("version", ""), "Версия", 32)
        body = string(data.get("body"), "Markdown", 30000, True)
        published = integer(data.get("published", 1), "Опубликовано", 0, 1)
        now = stamp()
        update_id = identity()
        service.con.execute(
            "INSERT INTO product_updates(id,title,version,body,published,published_at,updated_at,created_by)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (update_id,title,version,body,published,now,now,service.user["id"]),
        )
        return 201, {"id":update_id}
    if len(parts) != 1 and not (len(parts) == 2 and parts[1] in ("view","reaction")):
        raise DomainError(404, "Не найдено")
    row = _row(service, parts[0], True)
    if len(parts) == 1 and method == "PATCH":
        _admin(service)
        title = string(data.get("title",row["title"]), "Заголовок", 160, True)
        version = string(data.get("version",row["version"]), "Версия", 32)
        body = string(data.get("body",row["body"]), "Markdown", 30000, True)
        published = integer(data.get("published",row["published"]), "Опубликовано", 0, 1)
        service.con.execute(
            "UPDATE product_updates SET title=?,version=?,body=?,published=?,updated_at=? WHERE id=?",
            (title,version,body,published,stamp(),row["id"]),
        )
        return 200, {"ok":True}
    if len(parts) != 2 or method != "POST":
        raise DomainError(405, "Метод не поддерживается")
    if not row["published"]:
        raise DomainError(404, "Обновление не найдено")
    uid = service.user["id"]
    if parts[1] == "view":
        created = service.con.execute(
            "INSERT INTO product_update_views(update_id,user_id,created_at)"
            " VALUES(?,?,?) ON CONFLICT(update_id,user_id) DO NOTHING RETURNING update_id",
            (row["id"],uid,stamp()),
        ).fetchone()
        if created:
            service.con.execute("UPDATE product_updates SET view_count=view_count+1 WHERE id=?",(row["id"],))
        return 200, {"viewed":True}
    reaction = data.get("reaction")
    if reaction not in ("like","dislike","none"):
        raise DomainError(400, "Неверная реакция")
    previous = service.con.execute(
        "SELECT reaction FROM product_update_reactions WHERE update_id=? AND user_id=?",
        (row["id"],uid),
    ).fetchone()
    old = previous["reaction"] if previous else "none"
    if old == reaction:
        return 200, {"reaction":reaction}
    if reaction == "none":
        service.con.execute(
            "DELETE FROM product_update_reactions WHERE update_id=? AND user_id=?",
            (row["id"],uid),
        )
    else:
        service.con.execute(
            "INSERT INTO product_update_reactions(update_id,user_id,reaction,updated_at) "
            "VALUES(?,?,?,?) ON CONFLICT(update_id,user_id) DO UPDATE SET "
            "reaction=excluded.reaction,updated_at=excluded.updated_at",
            (row["id"],uid,reaction,stamp()),
        )
    service.con.execute(
        "UPDATE product_updates SET likes=likes+?,dislikes=dislikes+? WHERE id=?",
        ((1 if reaction=="like" else 0)-(1 if old=="like" else 0),
         (1 if reaction=="dislike" else 0)-(1 if old=="dislike" else 0),
         row["id"]),
    )
    return 200, {"reaction":reaction}
