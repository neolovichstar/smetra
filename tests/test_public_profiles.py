"""Public-profile privacy, real image decoding and cross-account chat flows."""

import base64
import io
import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path
import unittest
import urllib.request
import urllib.parse
import uuid

from PIL import Image
from tests.test_business import BusinessFlows as Flows


class PublicProfilesTests(unittest.TestCase):
    setUpClass = classmethod(Flows.setUpClass.__func__)
    tearDownClass = classmethod(Flows.tearDownClass.__func__)
    setUp = Flows.setUp
    call = Flows.call
    account = Flows.account
    quote = Flows.quote
    publish = Flows.publish

    def person(self, label="person", verified=True):
        token, user_id = self.account("profile-" + label + "-" + uuid.uuid4().hex[:8])
        with self.mod.db() as con:
            con.execute(
                "UPDATE users SET email_verified_at=? WHERE id=?",
                (self.mod.now() if verified else None, user_id),
            )
        return token, user_id

    def public(self, token, **changes):
        old = self.call("/profile/public", token=token)[1]["profile"]
        code, result = self.call(
            "/profile/public",
            "PATCH",
            {
                "revision": old["revision"],
                "display_name": "Анна Иванова",
                "published": True,
                **changes,
            },
            token,
        )
        self.assertEqual(code, 200, result)
        return result["profile"]

    def test_opt_in_allowlist_search_and_immediate_unpublish(self):
        token, uid = self.person()
        public_id = "SM-" + uid.replace("-", "").upper()
        self.assertEqual(self.call("/public/profiles/" + public_id)[0], 404)
        draft = self.call("/profile/public", token=token)[1]["profile"]
        self.assertFalse(draft["published"])
        profile = self.public(
            token,
            handle="anna_" + uuid.uuid4().hex[:8],
            headline="Отделка",
            city="Казань",
            bio="Работаю аккуратно",
        )
        code, visible = self.call("/public/profiles/" + profile["handle"])
        self.assertEqual(code, 200, visible)
        self.assertEqual(
            set(visible["profile"]),
            {
                "public_id",
                "handle",
                "name",
                "headline",
                "bio",
                "city",
                "avatar_url",
                "url",
                "allow_messages",
                "allow_quotes",
            },
        )
        self.assertNotIn(uid, json.dumps(visible))
        for query in ("Анн", "иван", "@" + profile["handle"], public_id):
            code, found = self.call("/public/profiles?q=" + urllib.parse.quote(query))
            self.assertEqual(code, 200, found)
            self.assertIn(public_id, [p["public_id"] for p in found["profiles"]])
        self.assertFalse(self.call("/public/profiles?q=%25")[1].get("profiles"))
        self.assertEqual(
            self.call(
                "/profile/public", "PATCH", {"revision": 0, "published": False}, token
            )[0],
            409,
        )
        hidden = self.public(token, published=False)
        self.assertFalse(hidden["published"])
        self.assertEqual(self.call("/public/profiles/" + profile["handle"])[0], 404)
        self.assertNotIn(
            public_id,
            [
                p["public_id"]
                for p in self.call("/public/profiles?q=" + urllib.parse.quote("Иван"))[
                    1
                ]["profiles"]
            ],
        )

    def test_validation_ownership_and_handle_uniqueness(self):
        first, uid = self.person()
        second, _ = self.person()
        handle = "builder_" + uuid.uuid4().hex[:8]
        self.public(first, handle=handle)
        revision = self.call("/profile/public", token=second)[1]["profile"]["revision"]
        for change in (
            {"handle": "admin"},
            {"handle": "a"},
            {"handle": "x<script>"},
            {"published": "true"},
            {"allow_messages": 1},
            {"display_name": "a\u202eb"},
            {"user_id": uid},
        ):
            self.assertEqual(
                self.call(
                    "/profile/public", "PATCH", {"revision": revision, **change}, second
                )[0],
                400,
                change,
            )
        self.assertEqual(
            self.call(
                "/profile/public",
                "PATCH",
                {"revision": revision, "handle": handle.upper()},
                second,
            )[0],
            409,
        )
        self.assertEqual(self.call("/profile/public")[0], 401)
        self.assertEqual(self.call("/public/profiles/x", "PATCH", {})[0], 405)
        unverified, _ = self.person(verified=False)
        self.assertEqual(
            self.call(
                "/profile/public",
                "PATCH",
                {"revision": 0, "published": True},
                unverified,
            )[0],
            403,
        )

    def upload(self, token, raw):
        return self.call(
            "/profile/avatar",
            "POST",
            {"content_base64": base64.b64encode(raw).decode()},
            token,
        )

    def test_avatar_reencode_delete_and_provider_does_not_restore(self):
        token, uid = self.person()
        with self.mod.db() as con:
            con.execute("UPDATE users SET avatar_id='test/provider' WHERE id=?", (uid,))
        photo = Image.new("RGB", (120, 80), "#63aa8a")
        exif = Image.Exif()
        exif[270] = "PRIVATE-PHOTO-METADATA"
        output = io.BytesIO()
        photo.save(output, "JPEG", exif=exif)
        code, result = self.upload(
            token, output.getvalue() + b"<script>private</script>"
        )
        self.assertEqual(code, 200, result)
        url = result["avatar_url"]
        with urllib.request.urlopen(self.base + url) as response:
            data = response.read()
            self.assertEqual(response.headers["Content-Type"], "image/webp")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertNotIn(b"PRIVATE-PHOTO", data)
        self.assertNotIn(b"<script", data)
        with Image.open(io.BytesIO(data)) as decoded:
            self.assertEqual(decoded.size, (384, 384))
            self.assertFalse(decoded.getexif())
        self.assertEqual(self.call("/me", token=token)[1]["user"]["avatar_url"], url)
        with self.mod.db() as con:
            con.execute(
                "UPDATE users SET avatar_id='another/provider' WHERE id=?", (uid,)
            )
        self.assertEqual(self.call("/me", token=token)[1]["user"]["avatar_url"], url)
        self.assertEqual(self.call("/profile/avatar", "DELETE", token=token)[0], 200)
        self.assertEqual(self.call("/me", token=token)[1]["user"]["avatar_url"], "")
        self.assertEqual(self.call(url.removeprefix("/api"))[0], 404)

    def test_avatar_rejects_bad_images_and_cannot_write_someone_else(self):
        first, _ = self.person()
        second, other = self.person()
        self.assertEqual(
            self.upload(first, b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')[0],
            400,
        )
        self.assertEqual(
            self.call("/profile/avatar", "POST", {"content_base64": "!!"}, first)[0],
            400,
        )
        self.assertEqual(
            self.call(
                "/profile/avatar",
                "POST",
                {"content_base64": "abc", "user_id": other},
                first,
            )[0],
            400,
        )
        for size in ((8, 8), (6000, 3000)):
            image = Image.new("RGB", size)
            output = io.BytesIO()
            image.save(output, "PNG")
            self.assertEqual(self.upload(first, output.getvalue())[0], 400, size)
        image = Image.new("RGB", (30, 30))
        output = io.BytesIO()
        image.save(output, "PNG")
        self.assertEqual(self.upload(first, output.getvalue())[0], 200)
        self.assertFalse(self.call("/me", token=second)[1]["user"]["avatar_url"])
        self.assertEqual(
            self.call(
                "/profile/avatar", "POST", {"content_base64": "a" * 1_450_000}, first
            )[0],
            413,
        )

    def test_find_message_and_send_only_published_owned_quote(self):
        sender, _ = self.person("sender")
        recipient, rid = self.person("recipient")
        outsider, _ = self.person("outsider")
        p = self.public(recipient, handle="customer_" + uuid.uuid4().hex[:8])
        code, found = self.call("/profile/directory?q=" + p["handle"], token=sender)
        self.assertEqual(code, 200, found)
        self.assertEqual(found["users"][0]["public_id"], p["public_id"])
        code, chat = self.call(
            "/profile/chats", "POST", {"public_id": p["public_id"]}, sender
        )
        self.assertEqual(code, 200, chat)
        conversation = chat["chat"]["id"]
        self.assertEqual(
            self.call(
                "/profile/chats/" + conversation + "/messages",
                "POST",
                {"message": "Здравствуйте"},
                sender,
            )[0],
            201,
        )
        self.assertEqual(
            self.call("/profile/chats/" + conversation + "/messages", token=outsider)[
                0
            ],
            403,
        )
        self.assertIn(
            "Здравствуйте",
            json.dumps(
                self.call(
                    "/profile/chats/" + conversation + "/messages", token=recipient
                )[1],
                ensure_ascii=False,
            ),
        )
        draft = self.quote(sender)
        payload = {"quote_id": draft["id"], "public_id": p["public_id"]}
        self.assertEqual(
            self.call("/profile/quote-chats", "POST", payload, sender)[0], 409
        )
        published = self.publish(sender, draft)
        self.assertIn(
            draft["id"],
            [
                q["id"]
                for q in self.call("/profile/shareable-quotes", token=sender)[1][
                    "quotes"
                ]
            ],
        )
        self.assertFalse(
            self.call("/profile/shareable-quotes", token=recipient)[1]["quotes"]
        )
        self.assertEqual(
            self.call("/profile/quote-chats", "POST", payload, outsider)[0], 404
        )
        self.assertEqual(
            self.call(
                "/profile/quote-chats", "POST", payload | {"version": 999}, sender
            )[0],
            409,
        )
        code, sent = self.call(
            "/profile/quote-chats",
            "POST",
            payload | {"version": published["published_version"]},
            sender,
        )
        self.assertEqual(code, 200, sent)
        messages = self.call(
            "/profile/chats/" + sent["chat"]["id"] + "/messages", token=recipient
        )[1]
        self.assertIn("/app?quote=", json.dumps(messages))
        self.assertNotIn("cost_price", json.dumps(messages))
        self.public(recipient, allow_messages=False, allow_quotes=False)
        self.assertEqual(
            self.call(
                "/profile/chats", "POST", {"public_id": p["public_id"]}, outsider
            )[0],
            403,
        )
        self.assertEqual(
            self.call("/profile/quote-chats", "POST", payload, sender)[0], 403
        )
        # Existing conversations remain usable when new-contact requests are disabled.
        self.assertEqual(
            self.call(
                "/profile/chats/" + conversation + "/messages",
                "POST",
                {"message": "Продолжим"},
                sender,
            )[0],
            201,
        )
        with self.mod.db() as con:
            con.execute("UPDATE users SET blocked=1 WHERE id=?", (rid,))
        self.assertEqual(self.call("/public/profiles/" + p["public_id"])[0], 404)

    def test_account_deletion_erases_public_card_avatar_and_rejects_inflight_edits(
        self,
    ):
        from backend.public_profiles import save_profile, store_avatar
        from backend.business import DomainError

        token, uid = self.person("delete")
        profile = self.public(token, handle="delete_" + uuid.uuid4().hex[:8])
        image = Image.new("RGB", (32, 32), "gray")
        output = io.BytesIO()
        image.save(output, "PNG")
        raw = base64.b64encode(output.getvalue()).decode()
        self.assertEqual(self.upload(token, output.getvalue())[0], 200)
        with self.mod.db() as con:
            stale_user = dict(
                con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            )
        self.assertEqual(self.call("/me", "DELETE", token=token)[0], 200)
        self.assertEqual(self.call("/public/profiles/" + profile["handle"])[0], 404)
        with self.mod.db() as con:
            for table in ("public_profiles", "profile_search_terms", "profile_avatars"):
                self.assertEqual(
                    con.execute(
                        "SELECT count(*) FROM " + table + " WHERE user_id=?", (uid,)
                    ).fetchone()[0],
                    0,
                )
            with self.assertRaises(DomainError):
                save_profile(con, stale_user, {"revision": 0, "published": True})
            with self.assertRaises(DomainError):
                store_avatar(con, stale_user, raw)


    def test_avatar_processor_works_with_vendored_serverless_dependencies(self):
        import PIL

        output = io.BytesIO()
        Image.new("RGB", (40, 60), "gray").save(output, "PNG")
        package_root = str(Path(PIL.__file__).resolve().parents[1])
        repo_root = str(Path(__file__).resolve().parents[1])
        bootstrap = (
            "import sys;sys.path[:0]=" + repr([repo_root, package_root]) + "\n"
            "import sqlite3\n"
            "from backend.public_profiles import ensure_schema,store_avatar\n"
            "con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row\n"
            'con.execute("CREATE TABLE users(id TEXT PRIMARY KEY,blocked INTEGER DEFAULT 0,deleted_at INTEGER)")\n'
            "user={'id':'11111111-2222-3333-4444-555555555555','avatar_id':''}\n"
            "con.execute('INSERT INTO users(id) VALUES(?)',(user['id'],));con.commit();ensure_schema(con)\n"
            "print(store_avatar(con,user,sys.stdin.read()))\n"
        )
        # The child interpreter has no installed packages; the parent receives
        # the vendored dependency path, as it does on Vercel.
        with tempfile.TemporaryDirectory() as folder:
            venv.EnvBuilder(with_pip=False, symlinks=True).create(folder)
            executable = str(Path(folder) / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
            result = subprocess.run(
                [executable, "-S", "-c", bootstrap],
                input=base64.b64encode(output.getvalue()).decode(),
                capture_output=True, text=True, timeout=15,
                env={"PATH": os.defpath, "LANG": "C.UTF-8"},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/api/public/avatars/SM-", result.stdout)


del Flows
