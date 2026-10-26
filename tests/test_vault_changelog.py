"""Regression checks: persistent attachment library, tenant isolation, news metrics, image vision."""
import base64
import io
import os
import unittest
from unittest.mock import patch

from PIL import Image
from tests import test_business


class VaultChangelogTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    @staticmethod
    def picture():
        output=io.BytesIO()
        Image.new("RGB",(32,20),(120,121,122)).save(output,format="PNG")
        return output.getvalue()

    def upload(self,token,name="photo.png"):
        return self.call("/files","POST",{
            "assistant_upload":True,"name":name,
            "content":base64.b64encode(self.picture()).decode("ascii")
        },token)

    def test_image_upload_gallery_thumbnail_archive_restore_and_delete(self):
        owner,_=self.account("vault-owner")
        stranger,_=self.account("vault-other")
        status,result=self.upload(owner)
        self.assertEqual(status,201,result)
        file_id=result["file"]["id"]
        active=self.call("/files?type=images",token=owner)[1]
        self.assertEqual([f["id"] for f in active["items"]],[file_id])
        self.assertEqual(active["total"],1)
        self.assertGreaterEqual(active["quota_bytes"],100_000_000)
        self.assertGreater(active["used_bytes"],0)
        self.assertNotIn("storage_name",str(active))
        self.assertEqual(self.call("/files?type=documents",token=owner)[1]["items"],[])
        self.assertEqual(self.call("/files/"+file_id,token=stranger)[0],404)
        self.assertEqual(self.call("/files/"+file_id+"/thumbnail",token=stranger)[0],404)
        thumbnail_status,thumbnail=self.call("/files/"+file_id+"/thumbnail",token=owner,raw=True)
        self.assertEqual(thumbnail_status,200)
        self.assertTrue(thumbnail.startswith(b"\xff\xd8"))
        self.assertEqual(self.call("/files/"+file_id+"/archive","PATCH",{"archived":1},stranger)[0],404)
        self.assertEqual(self.call("/files/"+file_id+"/archive","PATCH",{"archived":1},owner)[0],200)
        self.assertEqual(self.call("/files?type=images",token=owner)[1]["items"],[])
        archived=self.call("/files?archived=1",token=owner)[1]
        self.assertEqual(archived["items"][0]["id"],file_id)
        self.assertEqual(archived["used_bytes"],active["used_bytes"])
        self.assertEqual(self.call("/files/"+file_id+"/archive","PATCH",{"archived":0},owner)[0],200)
        self.assertEqual(self.call("/files?type=images",token=owner)[1]["items"][0]["id"],file_id)
        self.assertEqual(self.call("/files/"+file_id,"DELETE",token=owner)[0],200)
        self.assertEqual(self.call("/files/"+file_id,token=owner)[0],404)
        self.assertEqual(self.call("/files?type=images",token=owner)[1]["used_bytes"],0)

    def test_image_context_to_vision_model_without_persisting_image_bytes_in_chat(self):
        owner,_=self.account("vault-vision")
        result=self.upload(owner)[1]
        file_id=result["file"]["id"]
        with patch.dict(os.environ,OPENROUTER_API_KEY="not-a-real-token"),patch(
            "backend.assistant.query_model",return_value={"content":"На изображении серый прямоугольник."}
        ) as provider:
            code,reply=self.call("/assistant/chat","POST",{
                "text":"Что здесь?","context":{"entity":"files","id":file_id}
            },owner)
        self.assertEqual(code,200,reply)
        messages=provider.call_args.args[0]
        last=messages[-1]["content"]
        self.assertIsInstance(last,list)
        self.assertEqual(last[0]["type"],"text")
        self.assertTrue(last[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        stored=self.call("/assistant",token=owner)[1]["messages"]
        self.assertNotIn("data:image/",str(stored))
        self.assertIn("Что здесь?",str(stored))

    def test_changelog_admin_publish_unique_views_and_reaction_switch(self):
        author,author_id=self.account("news-admin")
        reader,reader_id=self.account("news-reader")
        other,_=self.account("news-third")
        self.assertEqual(self.call("/changelog","POST",{"title":"Несанкционированно","body":"X"},reader)[0],403)
        with self.mod.db() as con:
            con.execute("UPDATE users SET role='admin' WHERE id=?",(author_id,))
        code,created=self.call("/changelog","POST",{
            "title":"Новая галерея","version":"2.1.0","body":"## Заголовок\n**Жирный текст**",
            "published":1
        },author)
        self.assertEqual(code,201,created)
        id=created["id"]
        self.assertEqual(self.call("/changelog",token=reader)[1]["items"][0]["title"],"Новая галерея")
        for _ in range(2):
            self.assertEqual(self.call("/changelog/"+id+"/view","POST",{},reader)[0],200)
        self.assertEqual(self.call("/changelog/"+id+"/view","POST",{},other)[0],200)
        feed=self.call("/changelog",token=reader)[1]
        self.assertEqual(feed["items"][0]["view_count"],2)
        self.assertFalse(feed["can_publish"])
        self.assertEqual(self.call("/changelog/"+id+"/reaction","POST",{"reaction":"like"},reader)[0],200)
        self.assertEqual(self.call("/changelog/"+id+"/reaction","POST",{"reaction":"like"},reader)[0],200)
        self.assertEqual(self.call("/changelog",token=reader)[1]["items"][0]["likes"],1)
        self.assertEqual(self.call("/changelog/"+id+"/reaction","POST",{"reaction":"dislike"},reader)[0],200)
        record=self.call("/changelog",token=reader)[1]["items"][0]
        self.assertEqual((record["likes"],record["dislikes"],record["my_reaction"]),(0,1,"dislike"))
        self.assertEqual(self.call("/changelog/"+id+"/reaction","POST",{"reaction":"none"},reader)[0],200)
        record=self.call("/changelog",token=reader)[1]["items"][0]
        self.assertEqual((record["likes"],record["dislikes"]),(0,0))
        self.assertEqual(self.call("/changelog/"+id,"PATCH",{"title":"Взлом","body":"X"},reader)[0],403)
        self.assertEqual(self.call("/changelog/"+id,"PATCH",{"published":0},author)[0],200)
        self.assertEqual(self.call("/changelog",token=reader)[1]["items"],[])
        self.assertEqual(self.call("/changelog/"+id+"/view","POST",{},reader)[0],404)
        self.assertEqual(len(self.call("/changelog",token=author)[1]["items"]),1)

    def test_release_badge_counts_only_unread_published_posts_per_user(self):
        author,author_id=self.account("release-badge-author")
        alice,_=self.account("release-badge-alice")
        bob,_=self.account("release-badge-bob")
        with self.mod.db() as con:
            con.execute("UPDATE users SET role='admin' WHERE id=?",(author_id,))
        self.assertEqual(self.call("/changelog/unread",token=alice)[1]["unread_count"],0)
        draft=self.call("/changelog","POST",{"title":"Скрытый черновик","body":"Текст","published":0},author)[1]["id"]
        first=self.call("/changelog","POST",{"title":"Выпуск 1","body":"Новые файлы"},author)[1]["id"]
        second=self.call("/changelog","POST",{"title":"Выпуск 2","body":"Новая память"},author)[1]["id"]
        self.assertEqual(self.call("/changelog/unread",token=alice)[1]["unread_count"],2)
        self.assertEqual(self.call("/changelog",token=alice)[1]["unread_count"],2)
        self.assertEqual(self.call("/changelog/unread",token=bob)[1]["unread_count"],2)
        self.assertEqual(self.call("/changelog/"+first+"/view","POST",{},alice)[0],200)
        self.assertEqual(self.call("/changelog/"+first+"/view","POST",{},alice)[0],200)
        self.assertEqual(self.call("/changelog/unread",token=alice)[1]["unread_count"],1)
        self.assertEqual(self.call("/changelog/unread",token=bob)[1]["unread_count"],2)
        alice_rows=self.call("/changelog",token=alice)[1]["items"]
        self.assertTrue(next(x for x in alice_rows if x["id"]==first)["has_viewed"])
        self.assertFalse(next(x for x in alice_rows if x["id"]==second)["has_viewed"])
        self.assertEqual(self.call("/changelog/"+draft,"PATCH",{"published":1},author)[0],200)
        self.assertEqual(self.call("/changelog/unread",token=alice)[1]["unread_count"],2)
        self.assertEqual(self.call("/changelog/"+second,"PATCH",{"published":0},author)[0],200)
        self.assertEqual(self.call("/changelog/unread",token=alice)[1]["unread_count"],1)
        self.assertEqual(self.call("/changelog/"+draft+"/view","POST",{},bob)[0],200)
        self.assertEqual(self.call("/changelog/unread",token=bob)[1]["unread_count"],1)

    def test_viewer_can_rate_news_but_cannot_edit_workspace(self):
        author,author_id=self.account("news-owner")
        viewer,viewer_id=self.account("news-viewer")
        with self.mod.db() as con:
            con.execute("UPDATE users SET role='admin' WHERE id=?",(author_id,))
        wid=self.call("/workspace",token=author)[1]["workspace"]["id"]
        with self.mod.db() as con:
            con.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(?,?,?)",
                        (wid,viewer_id,"viewer"))
        note_id=self.call("/changelog","POST",{"title":"Релиз","body":"Текст"},author)[1]["id"]
        code,result=self.call("/changelog/"+note_id+"/reaction","POST",{"reaction":"like"},viewer,workspace=wid)
        self.assertEqual(code,200,result)
        self.assertEqual(self.call("/files","POST",{"assistant_upload":True,"name":"test.txt","content":"YQ=="},viewer,workspace=wid)[0],403)
