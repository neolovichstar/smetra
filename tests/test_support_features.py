"""Support screenshots and suggestion routing: authorization and bounded handling."""
import base64
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import backend.app as app
import backend.community as community
from backend.support_features import prepare_images, is_suggestion


class SupportFeaturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old_db_path = app.DB_PATH
        app.DB_PATH = Path(cls.tmp.name) / "support-features.sqlite3"
        app.migrate()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.server.server_address[1])
        cls.tokens = {}
        for role in ("admin", "alice", "bob"):
            user_id, token = app.uid(), app.secrets.token_urlsafe(32)
            cls.tokens[role] = token
            with app.db() as con:
                con.execute(
                    "INSERT INTO users(id,email,password_hash,name,role,created_at,email_verified_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (user_id, role+"-suggestions@example.test", app.hash_password("safe long test password"),
                     role, "admin" if role == "admin" else "user", app.now(), app.now()),
                )
                con.execute(
                    "INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)",
                    (app.uid(), user_id, app.hashlib.sha256(token.encode()).hexdigest(), app.now()+3600),
                )
                app.business.ensure_workspace(con, {"id": user_id, "name": role})

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        app.DB_PATH = cls.old_db_path
        cls.tmp.cleanup()

    def call(self, path, method="GET", body=None, who="alice", binary=False):
        raw = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json", "Authorization": "Bearer "+self.tokens[who]}
        req = urllib.request.Request(self.base+path, data=raw, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data=response.read()
                return response.status, data if binary else json.loads(data)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    @staticmethod
    def screenshot():
        buffer=io.BytesIO()
        Image.new("RGB",(120,80),(30,30,30)).save(buffer,format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()

    def test_screenshot_private_to_author_and_staff(self):
        with patch("backend.support_features.extract_screenshot_text", return_value=("Ошибка 500", True)), \
             patch.object(community, "_support_ai_reply", return_value={"reply":"Попробуйте обновить страницу","escalate":False,"reason":"","suggestion":False}):
            status, created=self.call("/api/support","POST",{"message":"Приложил снимок ошибки","images":[{"name":"screen.png","content":self.screenshot()}]})
        self.assertEqual(status,201,created)
        thread=created["ticket_id"]
        _, messages=self.call("/api/support/threads/"+thread+"/messages")
        mine=[m for m in messages["messages"] if m["sender_type"]=="user"]
        self.assertEqual(len(mine),1)
        image_id=mine[0]["metadata"]["images"][0]["id"]
        self.assertRegex(image_id,r"^[0-9a-f]{32}$")
        self.assertEqual(self.call("/api/support/images/"+image_id,binary=True)[0],200)
        self.assertEqual(self.call("/api/support/images/"+image_id,who="bob")[0],404)
        self.assertEqual(self.call("/api/admin/communication/images/"+image_id,who="admin",binary=True)[0],200)
        self.assertIn(self.call("/api/admin/communication/images/"+image_id,who="bob")[0],(401,403))

    def test_suggestion_pipeline_and_admin_triage(self):
        with patch.object(community, "_support_ai_reply", return_value={"reply":"Спасибо за идею","escalate":False,"reason":"","suggestion":True}):
            status, first=self.call("/api/support","POST",{"message":"Хочу быстрый поиск материалов в профиле"})
        self.assertEqual(status,201,first)
        status, denied=self.call("/api/admin/communication/suggestions",who="bob")
        self.assertIn(status,(401,403),denied)
        status, result=self.call("/api/admin/communication/suggestions",who="admin")
        self.assertEqual(status,200,result)
        found=[s for s in result["suggestions"] if s["conversation_id"]==first["ticket_id"]]
        self.assertEqual(len(found),1)
        idea_id=found[0]["id"]
        self.assertEqual(self.call("/api/admin/communication/suggestions/"+idea_id,"PATCH",{"status":"planned"},who="admin")[0],200)
        self.assertEqual(self.call("/api/admin/communication/suggestions?status=planned",who="admin")[1]["suggestions"][0]["id"],idea_id)
        self.assertEqual(self.call("/api/admin/communication/suggestions/"+idea_id,"PATCH",{"status":"done"},who="bob")[0],403)

    def test_invalid_image_rejected_without_ticket(self):
        self.assertEqual(self.call("/api/support","POST",{"message":"Проверьте файл","images":[{"name":"x.png","content":base64.b64encode(b"<html>").decode()}]})[0],400)
        self.assertEqual(self.call("/api/support","POST",{"message":"Проверьте файл","images":[{"name":"x.png","content":"x"*120_000}]})[0],400)
        with self.assertRaises(ValueError):
            prepare_images([{"name":"x.png","content":"x"*2_900_000}])

    def test_no_false_idea_from_regular_support(self):
        self.assertFalse(is_suggestion("При входе ошибка 500. Что делать?"))
        self.assertTrue(is_suggestion("Предлагаю добавить кнопку сравнения смет"))
        with self.assertRaises(ValueError):
            prepare_images([{"content":"abc"}])
