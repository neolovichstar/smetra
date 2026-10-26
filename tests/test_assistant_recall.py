"""Full-history assistant recall and private workspace-vault regression tests."""
import base64
import hashlib
import io
import os
import uuid
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from backend.business import DomainError, Service
from backend.assistant_recall import (
    automatic_history_context,
    inspect_storage_image,
    list_chat_conversations,
    read_chat_history,
    search_chat_history,
    search_workspace_storage,
)
from tests import test_business


class AssistantRecallTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    account = test_business.BusinessFlows.account
    call = test_business.BusinessFlows.call

    def service(self, token):
        # Workspaces are provisioned lazily at the first authenticated request.
        code, data = self.call("/workspace", token=token)
        self.assertEqual(code, 200, data)
        con = self.enterContext(self.mod.db())
        user = con.execute(
            "SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=?",
            (hashlib.sha256(token.encode()).hexdigest(),),
        ).fetchone()
        workspace = con.execute(
            "SELECT workspace_id FROM workspace_members WHERE user_id=? ORDER BY workspace_id LIMIT 1",
            (user["id"],),
        ).fetchone()[0]
        item = Service(SimpleNamespace(), con, "http://localhost")
        item.user, item.wid = user, workspace
        return item

    def conversation(self, token, title="Предыдущий диалог"):
        status, result = self.call("/assistant/conversations", "POST", {"title": title}, token)
        self.assertEqual(status, 201, result)
        return result["conversation"]["id"]

    def message(self, service, conversation_id, content, moment, role="user"):
        mid = str(uuid.uuid4())
        service.con.execute(
            "INSERT INTO assistant_messages(id,workspace_id,user_id,role,content,created_at,conversation_id) "
            "VALUES(?,?,?,?,?,?,?)",
            (mid, service.wid, service.user["id"], role, content, moment, conversation_id),
        )
        return mid

    def test_retrieves_old_messages_from_every_owned_chat_without_cross_user_leaks(self):
        owner, _ = self.account("recall-owner")
        stranger, _ = self.account("recall-stranger")
        conv = self.conversation(owner)
        other = self.conversation(stranger)
        mine = self.service(owner)
        other_service = self.service(stranger)
        self.message(mine, conv, "В проекте использовали термокраску серебристую", 110)
        for i in range(70):
            self.message(mine, conv, f"Старое сообщение с номером {i}", 200+i)
        self.message(other_service, other, "Термокраску смешивали с частными данными", 115)
        results = search_chat_history(mine, "термокраску")
        self.assertEqual(len(results["items"]), 1)
        self.assertIn("серебристую", results["items"][0]["excerpt"])
        self.assertEqual(results["items"][0]["conversation_id"], conv)
        self.assertEqual(search_chat_history(other_service, "серебристую")["items"], [])
        with self.assertRaises(DomainError) as error:
            read_chat_history(other_service, conv)
        self.assertEqual(error.exception.status, 404)

        cursor = ""
        seen = set()
        pages = 0
        while True:
            page = read_chat_history(mine, conv, cursor, 17)
            pages += 1
            for message in page["messages"]:
                self.assertNotIn(message["message_id"], seen)
                seen.add(message["message_id"])
            if not page["has_more"]:
                break
            cursor = page["next_before_id"]
        self.assertEqual(len(seen), 71)
        self.assertGreater(pages, 4)
        self.assertTrue(any(item["id"] == conv for item in list_chat_conversations(mine)["conversations"]))
        self.assertFalse(any(item["id"] == other for item in list_chat_conversations(mine)["conversations"]))

    def test_automatic_recall_obeys_memory_toggle_and_chat_deletion(self):
        owner, _ = self.account("recall-toggle")
        conv = self.conversation(owner, "Старые договоренности")
        service = self.service(owner)
        self.message(service, conv, "Для согласования выбрали термокраску серебристую", 100)
        context = automatic_history_context(service, "Напомни про термокраску", set())
        self.assertIn("серебристую", context)
        # Disabling memories stops implicit historical retrieval; explicit
        # history tools can still read the user's own stored conversations.
        service.con.execute(
            "INSERT INTO user_profiles(user_id,first_name,last_name,profession,company,about,response_style,memory_enabled,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET memory_enabled=0",
            (service.user["id"], "Тест", "", "", "", "", "concise", 0, 100),
        )
        self.assertEqual(automatic_history_context(service, "Напомни про термокраску", set()), "")
        self.assertEqual(len(search_chat_history(service, "термокраску")["items"]), 1)
        self.assertEqual(self.call("/assistant/conversations/" + conv, "DELETE", token=owner)[0], 200)
        self.assertEqual(search_chat_history(service, "термокраску")["items"], [])

    def test_model_receives_only_attributed_relevant_excerpt(self):
        owner, _ = self.account("recall-provider")
        other_id = self.conversation(owner, "Отделочные материалы")
        service = self.service(owner)
        self.message(service, other_id, "Уточнили, что термокраску серебристую заказал клиент", 120)
        with patch.dict(os.environ, OPENROUTER_API_KEY="fake-test-key"), patch(
            "backend.assistant.query_model", return_value={"content": "Нашёл упоминание в прошлом диалоге."}
        ) as provider:
            status, reply = self.call("/assistant/chat", "POST", {"text":"Мы раньше обсуждали термокраску?"}, owner)
        self.assertEqual(status, 200, reply)
        sent_messages = provider.call_args.args[0]
        self.assertTrue(any("серебристую" in str(item["content"]) for item in sent_messages))
        self.assertLess(sum(len(str(item["content"])) for item in sent_messages), 25000)

    def test_storage_tools_keep_archived_and_foreign_files_private(self):
        owner, _ = self.account("vault-tools")
        stranger, _ = self.account("vault-tools-other")
        payload = io.BytesIO()
        Image.new("RGB", (32,24), (40,50,60)).save(payload, format="PNG")
        raw = payload.getvalue()
        status, file = self.call("/files", "POST", {
            "name": "угол-комнаты.png", "assistant_upload": True,
            "content": base64.b64encode(raw).decode(),
        }, owner)
        self.assertEqual(status, 201, file)
        fid = file["file"]["id"]
        me = self.service(owner)
        other = self.service(stranger)
        matches = search_workspace_storage(me, "угол-комнаты", "images")
        self.assertEqual(matches["files"][0]["id"], fid)
        meta, url = inspect_storage_image(me, fid)
        self.assertEqual(meta["file_id"], fid)
        self.assertTrue(url.startswith("data:image/png;base64,"))
        with self.assertRaises(DomainError) as error:
            inspect_storage_image(other, fid)
        self.assertEqual(error.exception.status, 404)
        self.assertEqual(self.call("/files/"+fid+"/archive", "PATCH", {"archived": 1}, owner)[0],200)
        self.assertEqual(search_workspace_storage(me, "угол-комнаты", "images")["files"], [])
        with self.assertRaises(DomainError) as error:
            inspect_storage_image(me, fid)
        self.assertEqual(error.exception.status, 404)

    def test_tool_contracts_allow_read_only_history_and_storage(self):
        from backend.assistant import tools, read_tool, prepare
        names = {item["function"]["name"] for item in tools()}
        for name in ("search_chat_history","read_chat_history","list_chat_conversations",
                     "search_workspace_storage","inspect_storage_image"):
            self.assertIn(name, names)
        owner, _ = self.account("recall-contract")
        service = self.service(owner)
        self.assertEqual(read_tool(service,"list_chat_conversations",{})["conversations"][0]["id"],"general")
        self.assertEqual(read_tool(service,"search_workspace_storage",{})["files"],[])
        with self.assertRaises(DomainError):
            prepare(service,"search_chat_history",{"query":"секрет"})
