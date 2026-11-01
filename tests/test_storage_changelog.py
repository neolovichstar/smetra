"""Workspace storage (images, files, archive, thumbnails) and «Что нового» updates."""
import base64
import io
import unittest

from tests import test_business


class StorageAndChangelog(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def photo(self):
        from PIL import Image
        image = io.BytesIO()
        Image.new("RGB", (900, 600), (40, 90, 160)).save(image, format="PNG")
        return base64.b64encode(image.getvalue()).decode()

    def test_chat_photos_are_kept_and_storage_has_sections_and_an_archive(self):
        token, _ = self.account("storage-owner")
        other, _ = self.account("storage-other")
        status, chat = self.call("/files", "POST", {"assistant_upload": True, "source": "chat", "name": "Фото из чата.png", "content": self.photo()}, token)
        self.assertEqual(status, 201, chat)
        # Photos without the chat source are still refused for the assistant upload path.
        self.assertEqual(self.call("/files", "POST", {"assistant_upload": True, "name": "x.png", "content": self.photo()}, token)[0], 400)
        status, note = self.call("/files", "POST", {"assistant_upload": True, "name": "Заметка.md", "content": base64.b64encode(b"# Hi").decode()}, token)
        self.assertEqual(status, 201, note)

        self.assertEqual(self.call("/files", "POST", {"name": "x.txt", "content": base64.b64encode(b"x").decode()}, token)[0], 400)
        status, plain = self.call("/files", "POST", {"source": "storage", "name": "Список.txt", "content": base64.b64encode("Купить грунт".encode()).decode()}, token)
        self.assertEqual(status, 201, plain)
        self.assertEqual(self.call("/files/" + plain["file"]["id"], "DELETE", token=token)[0], 200)
        images = self.call("/files?kind=images", token=token)[1]["items"]
        files = self.call("/files?kind=files", token=token)[1]["items"]
        self.assertEqual([(f["name"], f["source"]) for f in images], [("Фото из чата.png", "chat")])
        self.assertEqual([f["name"] for f in files], ["Заметка.md"])

        status, thumb = self.call("/files/" + chat["file"]["id"] + "/thumb", token=token, raw=True)
        self.assertEqual(status, 200)
        from PIL import Image
        with Image.open(io.BytesIO(thumb)) as small:
            self.assertEqual(small.format, "JPEG")
            self.assertLessEqual(max(small.size), 360)
        self.assertEqual(self.call("/files/" + note["file"]["id"] + "/thumb", token=token)[0], 422)
        self.assertEqual(self.call("/files/" + chat["file"]["id"] + "/thumb", token=other)[0], 404)

        self.assertEqual(self.call("/files/" + chat["file"]["id"] + "/archive", "POST", {"archived": True}, token)[0], 200)
        self.assertEqual(self.call("/files?kind=images", token=token)[1]["items"], [])
        archived = self.call("/files?archived=1", token=token)[1]["items"]
        self.assertEqual([f["id"] for f in archived], [chat["file"]["id"]])
        summary = self.call("/files/storage", token=token)[1]["storage"]
        self.assertEqual((summary["images"]["count"], summary["files"]["count"], summary["archived"]["count"]), (0, 1, 1))
        self.assertGreater(summary["used_bytes"], 0)
        self.assertGreater(summary["limit_bytes"], summary["used_bytes"])
        self.assertEqual(self.call("/files/" + chat["file"]["id"] + "/archive", "POST", {"archived": True}, other)[0], 404)

        self.assertEqual(self.call("/files/" + chat["file"]["id"] + "/archive", "POST", {"archived": False}, token)[0], 200)
        self.assertEqual(len(self.call("/files?kind=images", token=token)[1]["items"]), 1)
        self.assertEqual(self.call("/files/" + chat["file"]["id"], "DELETE", token=token)[0], 200)
        self.assertEqual(self.call("/files/storage", token=token)[1]["storage"]["images"]["count"], 0)

    def test_updates_have_views_reactions_and_only_admins_publish(self):
        admin, admin_id = self.account("changelog-admin")
        reader, _ = self.account("changelog-reader")
        with self.mod.db() as con:
            con.execute("UPDATE users SET role='admin' WHERE id=?", (admin_id,))
        self.assertEqual(self.call("/changelog", "POST", {"title": "x", "body": "y"}, reader)[0], 403)
        status, created = self.call("/changelog", "POST", {"title": "Хранилище файлов", "body": "## Что нового\n- Галерея", "tag": "Новое"}, admin)
        self.assertEqual(status, 201, created)
        post = created["id"]

        self.assertEqual(self.call("/changelog/unread", token=reader)[1]["unread"], 1)
        listing = self.call("/changelog", token=reader)[1]
        self.assertFalse(listing["can_publish"])
        self.assertEqual((listing["items"][0]["title"], listing["items"][0]["seen"]), ("Хранилище файлов", False))
        for _ in range(3):
            self.assertEqual(self.call(f"/changelog/{post}/view", "POST", {}, reader)[0], 200)
        self.assertEqual(self.call(f"/changelog/{post}/view", "POST", {}, admin)[0], 200)
        item = self.call("/changelog", token=reader)[1]["items"][0]
        self.assertEqual((item["views"], item["seen"]), (2, True))
        self.assertEqual(self.call("/changelog/unread", token=reader)[1]["unread"], 0)

        status, reacted = self.call(f"/changelog/{post}/reaction", "POST", {"reaction": "fire"}, reader)
        self.assertEqual((status, reacted["my_reaction"], reacted["reactions"]["fire"]), (200, "fire", 1))
        status, reacted = self.call(f"/changelog/{post}/reaction", "POST", {"reaction": "up"}, reader)
        self.assertEqual((reacted["reactions"]["fire"], reacted["reactions"]["up"]), (0, 1))
        status, reacted = self.call(f"/changelog/{post}/reaction", "POST", {"reaction": None}, reader)
        self.assertEqual((reacted["my_reaction"], reacted["reactions"]["up"]), (None, 0))
        self.assertEqual(self.call(f"/changelog/{post}/reaction", "POST", {"reaction": "angry"}, reader)[0], 400)

        self.assertEqual(self.call(f"/changelog/{post}", "DELETE", token=reader)[0], 403)
        self.assertEqual(self.call(f"/changelog/{post}", "PATCH", {"title": "Хранилище", "body": "Текст"}, admin)[0], 200)
        self.assertEqual(self.call("/changelog", token=reader)[1]["items"][0]["title"], "Хранилище")
        self.assertEqual(self.call(f"/changelog/{post}", "DELETE", token=admin)[0], 200)
        self.assertEqual(self.call("/changelog", token=reader)[1]["items"], [])
        self.assertEqual(self.call(f"/changelog/{post}/view", "POST", {}, reader)[0], 404)


if __name__ == "__main__":
    unittest.main()
