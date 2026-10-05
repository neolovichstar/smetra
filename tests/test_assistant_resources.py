import base64
import concurrent.futures
import unittest

from tests import test_business, test_assistant_edits


class AssistantResourceTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account
    tool = staticmethod(test_assistant_edits.AssistantEditTests.tool)
    propose = test_assistant_edits.AssistantEditTests.propose
    quote = test_assistant_edits.AssistantEditTests.quote

    def file(self, token, body="# Документ\nСрок 30 дней.\n", name="brief.md", **refs):
        if not refs:
            refs["client_id"] = self.call("/clients", "POST", {"name": "Север"}, token)[1]["item"]["id"]
        status, result = self.call("/files", "POST", {
            "name": name, "content": base64.b64encode(body.encode()).decode(), **refs}, token)
        self.assertEqual(status, 201, result)
        return result["file"]

    def metadata(self, token, file):
        return self.call("/files/" + file["id"] + "/metadata", token=token)[1]["file"]

    def test_rename_preview_confirm_undo_repeats_and_isolation(self):
        owner, _ = self.account("resource-rename")
        stranger, _ = self.account("resource-rename-other")
        file = self.file(owner)
        path = "/files/" + file["id"]
        content = self.call(path, token=owner, raw=True)[1]
        action = self.propose(owner, "rename_file", {"id": file["id"], "name": "Сроки.md"})
        self.assertEqual(action["preview"]["rows"][0]["before"], "brief.md")
        self.assertEqual(self.metadata(owner, file)["name"], "brief.md")
        self.assertNotIn("_etag", action["arguments"])
        pending = self.call("/assistant", token=owner)[1]["actions"][0]
        self.assertFalse(any(key.startswith("_") for key in pending["arguments"]))
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, stranger)[0], 404)
        first = self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)
        self.assertEqual(first[0], 200, first)
        self.assertTrue(first[1]["undoable"])
        self.assertEqual(first, self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner))
        self.assertEqual(self.metadata(owner, file)["name"], "Сроки.md")
        self.assertEqual(self.call(path, token=owner, raw=True)[1], content)
        undo = self.call("/assistant/undo", "POST", {"id": action["id"]}, owner)
        self.assertEqual(undo[0], 200, undo)
        self.assertEqual(undo, self.call("/assistant/undo", "POST", {"id": action["id"]}, owner))
        self.assertEqual(self.metadata(owner, file)["name"], "brief.md")
        self.assertEqual(self.call(path + "/metadata", token=stranger)[0], 404)

    def test_metadata_blocks_stale_unknown_fields_paths_and_extension_changes(self):
        owner, _ = self.account("resource-metadata-validation")
        file = self.file(owner)
        metadata = self.metadata(owner, file)
        path = "/files/" + file["id"] + "/metadata"
        for name in ("../brief.md", "folder\\brief.md", "brief.html", "brief.md\n", "brief.md."):
            self.assertEqual(self.call(path, "PATCH", {"name": name, "metadata_etag": metadata["metadata_etag"]}, owner)[0], 400)
        self.assertEqual(self.call(path, "PATCH", {"name": "good.md", "public": 1,
                                                  "metadata_etag": metadata["metadata_etag"]}, owner)[0], 400)
        self.assertEqual(self.call(path, "PATCH", {"name": "good.md", "metadata_etag": metadata["metadata_etag"]}, owner)[0], 200)
        self.assertEqual(self.call(path, "PATCH", {"name": "stale.md", "metadata_etag": metadata["metadata_etag"]}, owner)[0], 409)

    def test_rename_undo_does_not_overwrite_new_manual_name(self):
        owner, _ = self.account("resource-rename-conflict")
        file = self.file(owner)
        action = self.propose(owner, "rename_file", {"id": file["id"], "name": "first.md"})
        self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)
        metadata = self.metadata(owner, file)
        self.call("/files/" + file["id"] + "/metadata", "PATCH",
                  {"name": "manual.md", "metadata_etag": metadata["metadata_etag"]}, owner)
        self.assertEqual(self.call("/assistant/undo", "POST", {"id": action["id"]}, owner)[0], 409)
        self.assertEqual(self.metadata(owner, file)["name"], "manual.md")

    def test_move_preserves_bytes_and_restores_exact_attachment(self):
        owner, _ = self.account("resource-move")
        file = self.file(owner)
        old = self.metadata(owner, file)
        project = self.call("/projects", "POST", {"name": "Новый заказ"}, owner)[1]["item"]
        action = self.propose(owner, "move_file", {"id": file["id"], "target": "projects", "target_id": project["id"]})
        self.assertEqual(action["preview"]["rows"][0]["after"], project["name"])
        applied = self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)
        self.assertEqual(applied[0], 200, applied)
        moved = self.metadata(owner, file)
        self.assertEqual(moved["project_id"], project["id"])
        self.assertIsNone(moved["client_id"])
        self.assertEqual(moved["sha256"], old["sha256"])
        self.assertEqual(self.call("/assistant/undo", "POST", {"id": action["id"]}, owner)[0], 200)
        self.assertEqual(self.metadata(owner, file), old)

    def test_move_rejects_foreign_target_and_public_file(self):
        owner, _ = self.account("resource-move-security")
        stranger, _ = self.account("resource-move-target")
        quote = self.quote(owner)
        file = self.file(owner, quote_id=quote["id"], public=1)
        meta = self.metadata(owner, file)
        project = self.call("/projects", "POST", {"name": "Заказ"}, owner)[1]["item"]
        foreign = self.call("/projects", "POST", {"name": "Чужой"}, stranger)[1]["item"]
        path = "/files/" + file["id"] + "/metadata"
        for target, expected in ((foreign, 404), (project, 409)):
            self.assertEqual(self.call(path, "PATCH", {"target": "projects", "target_id": target["id"],
                                                       "metadata_etag": meta["metadata_etag"]}, owner)[0], expected)

    def test_move_rejects_file_used_by_defect(self):
        owner, _ = self.account("resource-move-reference")
        obj = self.call("/construction/objects", "POST", {"name": "Объект"}, owner)[1]["object"]
        import io
        from PIL import Image

        image = io.BytesIO()
        Image.new("RGB", (8, 8)).save(image, "PNG")
        file = self.call("/files", "POST", {"construction_id": obj["id"], "name": "photo.png",
                         "content": base64.b64encode(image.getvalue()).decode()}, owner)[1]["file"]
        result = self.call("/construction/objects/" + obj["id"] + "/defects", "POST",
                           {"description": "Трещина", "photo_file_id": file["id"]}, owner)
        self.assertEqual(result[0], 201, result)
        client = self.call("/clients", "POST", {"name": "Другой клиент"}, owner)[1]["item"]
        meta = self.metadata(owner, file)
        self.assertEqual(self.call("/files/" + file["id"] + "/metadata", "PATCH",
                                   {"target": "clients", "target_id": client["id"],
                                    "metadata_etag": meta["metadata_etag"]}, owner)[0], 409)

    def test_markdown_deletion_undo_restores_exact_version(self):
        owner, _ = self.account("resource-md-undo")
        original = "# Документ\nСрок 30 дней.\n"
        file = self.file(owner, original)
        action = self.propose(owner, "replace_markdown_text", {"id": file["id"], "old_text": "Срок 30 дней.", "new_text": ""})
        self.assertEqual(action["preview"]["rows"][0]["after"], "")
        applied = self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)
        self.assertTrue(applied[1]["undoable"], applied)
        self.assertEqual(self.call("/assistant/undo", "POST", {"id": action["id"]}, owner)[0], 200)
        self.assertEqual(self.call("/files/" + file["id"], token=owner, raw=True)[1], original.encode())

    def test_markdown_undo_preserves_later_edit(self):
        owner, _ = self.account("resource-md-conflict")
        file = self.file(owner)
        action = self.propose(owner, "replace_markdown_text", {"id": file["id"], "old_text": "30", "new_text": "45"})
        applied = self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)
        edited = self.call("/files/" + file["id"], "PATCH",
                           {"sha256": applied[1]["result"]["file"]["sha256"],
                            "content": base64.b64encode(b"Later manual edit").decode()}, owner)
        self.assertEqual(edited[0], 200, edited)
        self.assertEqual(self.call("/assistant/undo", "POST", {"id": action["id"]}, owner)[0], 409)

    def test_document_preview_create_parallel_repeat_read_and_undo(self):
        owner, _ = self.account("resource-document")
        stranger, _ = self.account("resource-document-other")
        quote = self.quote(owner)
        action = self.propose(owner, "create_document", {"quote_id": quote["id"], "kind": "invoice", "template": "Modern"})
        self.assertEqual(self.call("/documents", token=owner)[1]["items"], [])
        preview = "/assistant/actions/" + action["id"] + "/preview.pdf"
        self.assertEqual(self.call(preview, token=stranger)[0], 404)
        result = self.call(preview, token=owner, raw=True)
        self.assertEqual(result[0], 200, result)
        self.assertTrue(result[1].startswith(b"%PDF"))
        self.assertEqual(self.call("/documents", token=owner)[1]["items"], [])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            applied = list(pool.map(lambda _: self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner), range(2)))
        self.assertEqual(applied[0][0], 200, applied)
        self.assertEqual(applied[0], applied[1])
        document = applied[0][1]["result"]["document"]
        self.assertEqual(len(self.call("/documents", token=owner)[1]["items"]), 1)
        from unittest.mock import patch
        import os

        with patch.dict(os.environ, OPENROUTER_API_KEY="test-only"), patch("backend.assistant.query_model", side_effect=[
            self.tool("get_document", {"id": document["id"]}), {"content": "Проверено", "tool_calls": []}]) as model:
            self.assertEqual(self.call("/assistant/chat", "POST", {"text": "Прочитай", "context": {"entity": "documents", "id": document["id"]}}, owner)[0], 200)
        tool_content = model.call_args.args[0][-1]["content"]
        self.assertNotIn("cost_price", tool_content)
        self.assertNotIn("internal_cost", tool_content)
        undo = self.call("/assistant/undo", "POST", {"id": action["id"]}, owner)
        self.assertEqual(undo[0], 200, undo)
        self.assertEqual(undo, self.call("/assistant/undo", "POST", {"id": action["id"]}, owner))
        self.assertEqual(self.call("/documents/" + document["id"], token=owner)[0], 404)

    def test_document_rejects_changed_quote_before_preview_and_apply(self):
        owner, _ = self.account("resource-document-stale")
        quote = self.quote(owner)
        action = self.propose(owner, "create_document", {"quote_id": quote["id"], "kind": "proposal"})
        self.call("/quotes/" + quote["id"], "PATCH", {"revision": quote["revision"], "title": "Новые условия"}, owner)
        self.assertEqual(self.call("/assistant/actions/" + action["id"] + "/preview.pdf", token=owner)[0], 409)
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)[0], 409)
        self.assertEqual(self.call("/documents", token=owner)[1]["items"], [])

    def test_stage_update_has_currency_preview_and_revision_checked_undo(self):
        owner, _ = self.account("resource-stage")
        project = self.call("/projects", "POST", {"name": "Проект", "currency": "USD"}, owner)[1]["item"]
        stage = self.call("/stages", "POST", {"project_id": project["id"], "name": "Этап", "amount_kopecks": 15000}, owner)[1]["item"]
        action = self.propose(owner, "update_stages", {"id": stage["id"], "amount_kopecks": 18000, "status": "in_progress"})
        self.assertEqual(action["preview"]["currency"], "USD")
        applied = self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)
        self.assertEqual(applied[0], 200, applied)
        self.assertTrue(applied[1]["undoable"])
        self.assertEqual(self.call("/assistant/undo", "POST", {"id": action["id"]}, owner)[0], 200)
        self.assertEqual(self.call("/stages/" + stage["id"], token=owner)[1]["item"]["amount_kopecks"], 15000)

    def test_stage_create_requires_confirmation_and_does_not_duplicate(self):
        owner, _ = self.account("resource-stage-create")
        project = self.call("/projects", "POST", {"name": "Проект"}, owner)[1]["item"]
        action = self.propose(owner, "create_stages", {"project_id": project["id"], "name": "Передача", "amount_kopecks": 20000})
        self.assertEqual(self.call("/stages?project_id=" + project["id"], token=owner)[1]["items"], [])
        result = self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)
        self.assertEqual(result[0], 200, result)
        self.assertEqual(result, self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner))
        self.assertEqual(len(self.call("/stages?project_id=" + project["id"], token=owner)[1]["items"]), 1)

    def test_viewer_cannot_change_metadata_or_confirm_owners_actions(self):
        owner, _ = self.account("resource-owner-role")
        viewer, _ = self.account("resource-viewer-role")
        file = self.file(owner)
        workspace = self.call("/workspace", token=owner)[1]["workspace"]["id"]
        invited = self.call("/workspace/members", "POST", {"email": "resource-viewer-role@test.invalid", "role": "viewer"}, owner)
        self.assertEqual(invited[0], 200, invited)
        meta = self.call("/files/" + file["id"] + "/metadata", token=viewer, workspace=workspace)
        self.assertEqual(meta[0], 200, meta)
        self.assertEqual(self.call("/files/" + file["id"] + "/metadata", "PATCH",
                                   {"name": "forbidden.md", "metadata_etag": meta[1]["file"]["metadata_etag"]},
                                   viewer, workspace=workspace)[0], 403)
        action = self.propose(owner, "rename_file", {"id": file["id"], "name": "allowed.md"})
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, viewer, workspace=workspace)[0], 403)
