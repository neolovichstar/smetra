"""Opt-in public cards and scrubbed avatars; private assistant profiles stay private."""

import base64
import binascii
import hashlib
import os
import re
import sqlite3
import subprocess
import sys
import unicodedata
from pathlib import Path

from backend.business import DomainError as ApiError, transaction, stamp

HANDLE = re.compile(r"[a-z][a-z0-9_]{2,31}")
PUBLIC_ID = re.compile(r"SM-([A-Fa-f0-9]{32})", re.I)
AVATAR_PATH = re.compile(
    r"/api/public/avatars/(SM-[A-Fa-f0-9]{32})/([a-f0-9]{64})\.webp"
)
RESERVED = frozenset(
    "admin administrator support smetra settings profile profiles public api help team official moderator deleted me".split()
)
FIELDS = frozenset(
    (
        "handle",
        "display_name",
        "headline",
        "bio",
        "city",
        "published",
        "allow_messages",
        "allow_quotes",
        "revision",
    )
)


def ensure_schema(con):
    con.executescript(
        (
            Path(__file__).parent / "migrations/034_public_profiles_avatars.sql"
        ).read_text()
    )


def public_id(user_id):
    return "SM-" + str(user_id).replace("-", "").upper()


def id_from_public(value):
    match = PUBLIC_ID.fullmatch(str(value or "").strip())
    if not match:
        return None
    value = match[1].lower()
    return "-".join((value[:8], value[8:12], value[12:16], value[16:20], value[20:]))


def clean_text(value, label, maximum, required=False):
    if (
        not isinstance(value, str)
        or len(value.strip()) > maximum
        or (required and not value.strip())
    ):
        raise ApiError(400, "Проверьте поле «" + label + "»")
    value = unicodedata.normalize("NFC", value.strip())
    if any(unicodedata.category(c).startswith("C") and c not in "\n\t" for c in value):
        raise ApiError(400, "Недопустимые символы в поле «" + label + "»")
    if label != "О себе" and ("\n" in value or "\t" in value):
        raise ApiError(400, "Поле «" + label + "» должно быть в одну строку")
    return value


def avatar_url_for(user_id, provider_id="", content_hash=None):
    if content_hash is not None:
        return (
            "/api/public/avatars/" + public_id(user_id) + "/" + content_hash + ".webp"
            if content_hash
            else ""
        )
    return (
        "https://avatars.yandex.net/get-yapic/" + provider_id + "/islands-200"
        if provider_id and re.fullmatch(r"[A-Za-z0-9_/-]{1,150}", provider_id)
        else ""
    )


def avatar_url(con, user):
    row = con.execute(
        "SELECT content_hash FROM profile_avatars WHERE user_id=?", (user["id"],)
    ).fetchone()
    provider_id = user["avatar_id"] if "avatar_id" in user.keys() else ""
    return avatar_url_for(
        user["id"], provider_id, row["content_hash"] if row is not None else None
    )


def profile_view(row):
    return {
        "public_id": public_id(row["user_id"]),
        "handle": row["handle"] or "",
        "name": row["display_name"],
        "headline": row["headline"],
        "bio": row["bio"],
        "city": row["city"],
        "avatar_url": avatar_url_for(
            row["user_id"], row["avatar_id"], row["avatar_hash"]
        ),
        "url": "/u/" + (row["handle"] or public_id(row["user_id"])),
        "allow_messages": bool(row["allow_messages"]),
        "allow_quotes": bool(row["allow_quotes"]),
    }


def own_profile(con, user):
    row = con.execute(
        "SELECT * FROM public_profiles WHERE user_id=?", (user["id"],)
    ).fetchone()
    values = (
        dict(row)
        if row
        else dict(
            handle="",
            display_name=user["name"],
            headline="",
            bio="",
            city="",
            published=0,
            allow_messages=1,
            allow_quotes=1,
            revision=0,
        )
    )
    return {
        key: (
            bool(values[key])
            if key in ("published", "allow_messages", "allow_quotes")
            else values[key] or ""
            if key == "handle"
            else values[key]
        )
        for key in FIELDS
    } | {
        "public_id": public_id(user["id"]),
        "avatar_url": avatar_url(con, user),
        "url": "/u/" + (values["handle"] or public_id(user["id"])),
    }


def assert_active(con, user):
    if not con.execute(
        "SELECT 1 FROM users WHERE id=? AND deleted_at IS NULL AND blocked=0",
        (user["id"],),
    ).fetchone():
        raise ApiError(403, "Аккаунт недоступен")


def save_profile(con, user, data):
    if (
        set(data) - FIELDS
        or type(data.get("revision")) is not int
        or data["revision"] < 0
    ):
        raise ApiError(400, "Обновите форму публичного профиля")
    if data.get("published") is True and user["email_verified_at"] is None:
        raise ApiError(403, "Подтвердите почту перед публикацией профиля")
    for field in ("published", "allow_messages", "allow_quotes"):
        if field in data and type(data[field]) is not bool:
            raise ApiError(400, "Некорректная настройка профиля")
    with transaction(
        con,
        lock_scopes=("user:" + user["id"], "public-profile:" + user["id"]),
    ):
        assert_active(con, user)
        old = own_profile(con, user)
        if data["revision"] != old["revision"]:
            raise ApiError(409, "Профиль изменился в другой вкладке. Обновите страницу")
        values = old | data
        handle = clean_text(values["handle"], "Короткий адрес", 32).lstrip("@").lower()
        if handle and (not HANDLE.fullmatch(handle) or handle in RESERVED):
            raise ApiError(
                400, "Для адреса: от 3 до 32 латинских букв, цифр и _. Начните с буквы"
            )
        name = clean_text(values["display_name"], "Имя", 80, True)
        headline = clean_text(values["headline"], "Специализация", 120)
        bio = clean_text(values["bio"], "О себе", 800)
        city = clean_text(values["city"], "Город", 80)
        if (
            handle
            and con.execute(
                "SELECT 1 FROM public_profiles WHERE handle=? AND user_id<>?",
                (handle, user["id"]),
            ).fetchone()
        ):
            raise ApiError(409, "Этот короткий адрес уже занят")
        con.execute(
            "INSERT INTO public_profiles(user_id,handle,display_name,headline,bio,city,published,allow_messages,allow_quotes,revision,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET handle=excluded.handle,display_name=excluded.display_name,"
            "headline=excluded.headline,bio=excluded.bio,city=excluded.city,published=excluded.published,"
            "allow_messages=excluded.allow_messages,allow_quotes=excluded.allow_quotes,revision=excluded.revision,updated_at=excluded.updated_at",
            (
                user["id"],
                handle or None,
                name,
                headline,
                bio,
                city,
                int(values["published"]),
                int(values["allow_messages"]),
                int(values["allow_quotes"]),
                old["revision"] + 1,
                stamp(),
            ),
        )
        con.execute("DELETE FROM profile_search_terms WHERE user_id=?", (user["id"],))
        if values["published"]:
            terms = {name.casefold(), handle} | set(
                re.findall(r"[^\W_]+", name.casefold(), re.UNICODE)
            )
            for term in sorted(terms - {""})[:24]:
                con.execute(
                    "INSERT INTO profile_search_terms(user_id,term) VALUES(?,?)",
                    (user["id"], term),
                )
    return own_profile(con, user)


SELECT_PUBLIC = (
    "SELECT p.*,u.avatar_id,a.content_hash AS avatar_hash FROM public_profiles p JOIN users u ON u.id=p.user_id "
    "LEFT JOIN profile_avatars a ON a.user_id=p.user_id "
    "WHERE p.published=1 AND u.deleted_at IS NULL AND u.blocked=0 "
)


def get_public(con, value):
    value = str(value or "").strip().lstrip("@")
    user_id = id_from_public(value)
    if user_id:
        row = con.execute(SELECT_PUBLIC + "AND p.user_id=?", (user_id,)).fetchone()
    elif HANDLE.fullmatch(value.lower()):
        row = con.execute(SELECT_PUBLIC + "AND p.handle=?", (value.lower(),)).fetchone()
    else:
        row = None
    if not row:
        raise ApiError(404, "Профиль не опубликован или не найден")
    return profile_view(row)


def search(con, value):
    value = clean_text(value, "Поиск", 80).strip().lstrip("@").casefold()
    if not value:
        rows = con.execute(
            SELECT_PUBLIC + "ORDER BY p.updated_at DESC,p.user_id LIMIT 20"
        ).fetchall()
    elif id_from_public(value):
        try:
            return [get_public(con, value)]
        except ApiError:
            return []
    elif len(value) < 2:
        raise ApiError(400, "Введите хотя бы два символа имени или адреса")
    else:
        # Prefix matching stays bounded and uses an indexed set of public terms.
        prefix = (
            value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        )
        rows = con.execute(
            SELECT_PUBLIC
            + "AND p.user_id IN (SELECT t.user_id FROM profile_search_terms t "
            "WHERE t.term LIKE ? ESCAPE '\\' ORDER BY t.term,t.user_id LIMIT 100) "
            "ORDER BY p.display_name,p.user_id LIMIT 20",
            (prefix,),
        ).fetchall()
    return [profile_view(row) for row in rows]


def require_contact(con, user_id, kind):
    row = con.execute(
        "SELECT allow_messages,allow_quotes FROM public_profiles WHERE user_id=?",
        (user_id,),
    ).fetchone()
    if row and not row["allow_quotes" if kind == "quote" else "allow_messages"]:
        raise ApiError(
            403,
            "Пользователь отключил получение смет"
            if kind == "quote"
            else "Пользователь отключил новые сообщения",
        )


def store_avatar(con, user, raw):
    try:
        content = (
            base64.b64decode(raw, validate=True)
            if isinstance(raw, str) and len(raw) <= 1_398_104
            else b""
        )
    except (ValueError, binascii.Error):
        content = b""
    if not content or len(content) > 1_048_576:
        raise ApiError(400, "Выберите фото JPEG, PNG или WebP")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(Path(__file__).with_name("avatar_processor.py")),
            ],
            input=content,
            capture_output=True,
            timeout=6,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
            cwd="/tmp",
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        raise ApiError(
            400, "Не удалось обработать фото. Выберите другое изображение"
        ) from None
    content = result.stdout
    if (
        result.returncode
        or not 20 <= len(content) <= 160_000
        or content[:4] != b"RIFF"
        or content[8:12] != b"WEBP"
    ):
        raise ApiError(
            400, "Не удалось обработать фото. Используйте JPEG, PNG или WebP"
        )
    digest = hashlib.sha256(content).hexdigest()
    with transaction(
        con,
        lock_scopes=("user:" + user["id"], "public-profile:" + user["id"]),
    ):
        assert_active(con, user)
        con.execute(
            "INSERT INTO profile_avatars(user_id,content_hash,content,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET content_hash=excluded.content_hash,content=excluded.content,updated_at=excluded.updated_at",
            (user["id"], digest, content, stamp()),
        )
    return avatar_url(con, user)


def delete_avatar(con, user):
    # A tombstone keeps a later Yandex login from restoring a photo the user removed.
    with transaction(
        con,
        lock_scopes=("user:" + user["id"], "public-profile:" + user["id"]),
    ):
        assert_active(con, user)
        con.execute(
            "INSERT INTO profile_avatars(user_id,content_hash,content,updated_at) VALUES(?,'',NULL,?) "
            "ON CONFLICT(user_id) DO UPDATE SET content_hash='',content=NULL,updated_at=excluded.updated_at",
            (user["id"], stamp()),
        )


def handles(path):
    return (
        path
        in (
            "/api/profile/public",
            "/api/profile/avatar",
            "/api/profile/shareable-quotes",
            "/api/public/profiles",
        )
        or path.startswith("/api/public/profiles/")
        or path.startswith("/api/public/avatars/")
    )


def route(handler, con, method, path, query):
    if path.startswith("/api/public/"):
        if method != "GET":
            raise ApiError(405, "Только чтение")
        handler.throttle("public-profiles:" + handler.client_address[0], 120, 60)
        if path.startswith("/api/public/avatars/"):
            match = AVATAR_PATH.fullmatch(path)
            row = (
                con.execute(
                    "SELECT a.content FROM profile_avatars a JOIN users u ON u.id=a.user_id "
                    "WHERE a.user_id=? AND a.content_hash=? AND u.deleted_at IS NULL AND u.blocked=0",
                    (id_from_public(match[1]), match[2]),
                ).fetchone()
                if match
                else None
            )
            if not row or not row["content"]:
                raise ApiError(404, "Фото не найдено")
            content = bytes(row["content"])
            handler.send_response(200)
            for key, value in (
                ("Content-Type", "image/webp"),
                ("Content-Length", str(len(content))),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
                ("Referrer-Policy", "no-referrer"),
                ("Content-Security-Policy", "default-src 'none'"),
            ):
                handler.send_header(key, value)
            handler.end_headers()
            handler.wfile.write(content)
            return True
        if path == "/api/public/profiles":
            return handler.send_json(
                200, {"profiles": search(con, (query.get("q") or [""])[0])}
            )
        slug = path.removeprefix("/api/public/profiles/")
        return handler.send_json(200, {"profile": get_public(con, slug)})
    user = handler.auth(con)
    if path == "/api/profile/public":
        if method == "GET":
            return handler.send_json(200, {"profile": own_profile(con, user)})
        if method == "PATCH":
            handler.throttle("public-profile-edit:" + user["id"], 30, 3600)
            try:
                profile = save_profile(con, user, handler.body())
            except sqlite3.IntegrityError:
                raise ApiError(409, "Этот короткий адрес уже занят") from None
            return handler.send_json(200, {"profile": profile})
    if path == "/api/profile/avatar":
        if method == "POST":
            handler.throttle("avatar-upload:" + user["id"], 12, 3600)
            data = handler.body()
            if set(data) != {"content_base64"}:
                raise ApiError(400, "Выберите фото")
            url = store_avatar(con, user, data["content_base64"])
            return handler.send_json(200, {"avatar_url": url})
        if method == "DELETE":
            handler.throttle("avatar-upload:" + user["id"], 12, 3600)
            delete_avatar(con, user)
            return handler.send_json(200, {"avatar_url": ""})
    if path == "/api/profile/shareable-quotes" and method == "GET":
        rows = con.execute(
            "SELECT id,title,published_version,amount_kopecks,currency FROM quotes WHERE user_id=? "
            "AND published_version>0 AND approval_state IN ('sent','viewed','changes_requested') "
            "AND (expires_at IS NULL OR expires_at=0 OR expires_at>?) ORDER BY updated_at DESC LIMIT 100",
            (user["id"], stamp()),
        ).fetchall()
        return handler.send_json(200, {"quotes": [dict(row) for row in rows]})
    raise ApiError(405, "Метод не поддерживается")
