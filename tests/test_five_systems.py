"""Five backend systems: privacy, measured quantities and immutable quotes."""
import base64
import io
import json
import os
import unittest
from unittest.mock import Mock, patch

from tests.test_business import BusinessFlows


class FiveSystemsTests(unittest.TestCase):
    setUpClass=classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass=classmethod(BusinessFlows.tearDownClass.__func__)
    setUp=BusinessFlows.setUp
    call=BusinessFlows.call
    account=BusinessFlows.account

    def test_voice_audio_sniffing_and_private_draft_path(self):
        from backend.voice_estimates import decode_audio
        audio=base64.b64encode(b"RIFF"+b"0"*4+b"WAVE"+b"0"*80).decode()
        kind,encoded=decode_audio({"format":"wav","audio":audio})
        self.assertEqual(kind,"wav")
        with self.assertRaises(Exception):
            decode_audio({"format":"wav","audio":base64.b64encode(b"fLaC"+b"0"*90).decode()})
        token,_=self.account("five-voice")
        with patch("backend.voice_estimates.transcribe",return_value="Два метра плитки"),patch(
            "backend.ai.draft",return_value=(200,{"draft":{"title":"Плитка","items":[]},"requires_review":True})
        ):
            status,result=self.call("/voice/draft","POST",{"audio":audio,"format":"wav"},token)
        self.assertEqual(status,200,result)
        self.assertTrue(result["requires_review"])
        self.assertFalse(result["audio_retained"])
        self.assertEqual(result["transcript"],"Два метра плитки")

    def test_openrouter_whisper_json_request_is_limited_and_does_not_store_audio(self):
        from backend.voice_estimates import transcribe
        audio=base64.b64encode(b"RIFF"+b"0"*4+b"WAVE"+b"0"*88).decode()
        response=Mock()
        response.read.return_value=json.dumps({"text":"Плитки 3 квадратных метра"}).encode()
        context=Mock()
        context.__enter__=Mock(return_value=response)
        context.__exit__=Mock(return_value=False)
        with patch.dict(os.environ,{
            "OPENROUTER_API_KEY":"test-only",
            "OPENROUTER_STT_MODEL":"openai/whisper-large-v3",
        }), patch("backend.voice_estimates.urllib.request.urlopen",return_value=context) as request:
            result=transcribe({"format":"wav","audio":audio})
        self.assertEqual(result,"Плитки 3 квадратных метра")
        url=request.call_args.args[0]
        self.assertEqual(url.full_url,"https://openrouter.ai/api/v1/audio/transcriptions")
        body=json.loads(url.data)
        self.assertEqual(body["model"],"openai/whisper-large-v3")
        self.assertEqual(body["language"],"ru")
        self.assertEqual(body["input_audio"]["data"],audio)

    def test_pdf_design_project_is_preview_only_and_validates_type(self):
        token,_=self.account("five-pdf")
        self.assertEqual(self.call("/design-projects/draft","POST",{"file":{"mime":"text/plain"}},token)[0],400)
        with patch("backend.ai.draft",return_value=(200,{"draft":{"items":[{"name":"Обои"}]},"requires_review":True})):
            code,data=self.call("/design-projects/draft","POST",{"file":{"mime":"application/pdf"}},token)
        self.assertEqual(code,200,data)
        self.assertFalse(data["published"])
        self.assertEqual(data["source"],"design_pdf")

    def test_ar_area_net_walls_and_bag_rounding_and_import(self):
        from backend.room_scans import preview
        room={"name":"Ванная","length":"4","width":"3","height":"2.5",
              "openings_m2":"2","mix_kg_per_m2":"1.2","bag_kg":"25","waste_percent":"10"}
        v=preview({"rooms":[room]})[0]
        self.assertEqual(v["floor_m2"],"12")
        self.assertEqual(v["gross_walls_m2"],"35.0")
        self.assertEqual(v["net_walls_m2"],"33.0")
        self.assertEqual(v["bags"],2)
        token,_=self.account("five-AR")
        code,obj=self.call("/construction/objects","POST",{"name":"Дом"},token)
        self.assertEqual(code,201,obj)
        oid=obj["object"]["id"]
        uri="/construction/objects/"+oid+"/scan/"
        self.assertEqual(self.call(uri+"import","POST",{"rooms":[room]},token)[0],400)
        code,out=self.call(uri+"preview","POST",{"rooms":[room]},token)
        self.assertEqual(code,200,out)
        code,out=self.call(uri+"import","POST",{"rooms":[room],"review_confirmed":True},token)
        self.assertEqual(code,201,out)
        self.assertEqual(out["zones"][0]["length_m"],"4")
        self.assertEqual(out["calculations"][0]["bags"],2)

    def test_shares_are_email_bound_require_verified_login_and_no_price_mutation(self):
        owner,_=self.account("five-sender")
        recipient,recipient_id=self.account("five-recipient")
        outsider,_=self.account("five-outsider")
        item=lambda name,cost,optional:{"name":name,"quantity":"1","unit":"шт.","unit_price":cost,
                                       "optional":optional}
        code,res=self.call("/quotes","POST",{
            "title":"Ремонт ванной","client":"Клиент","items":[
                item("Основание",10000,False),item("Тёплый пол",5000,True)]
        },owner)
        self.assertEqual(code,201,res)
        quote=res["quote"];qid=quote["id"]
        published=self.call("/quotes/"+qid+"/publish","POST",{
            "review_confirmed":True,"revision":quote["revision"]
        },owner)
        self.assertEqual(published[0],200,published)
        code,share=self.call("/shares","POST",{
            "quote_id":qid,"email":"five-recipient@test.invalid",
        },owner)
        self.assertEqual(code,201,share)
        self.assertNotIn("delivery",share)
        sid=share["id"]
        self.assertEqual(self.call("/shared-inbox",token=outsider)[1]["inbox"],[])
        self.assertEqual(self.call("/shared-inbox/"+sid,token=outsider)[0],404)
        with self.mod.db() as con:
            con.execute("UPDATE users SET email_verified_at=NULL WHERE id=?",(recipient_id,))
        self.assertEqual(self.call("/shared-inbox/"+sid,token=recipient)[0],403)
        with self.mod.db() as con:
            con.execute("UPDATE users SET email_verified_at=? WHERE id=?",
                        (self.mod.now(),recipient_id))

        code,response=self.call("/shared-inbox/"+sid,token=recipient)
        self.assertEqual(code,200,response)
        self.assertEqual(response["selected_total_kopecks"],15000)
        self.assertNotIn("internal_cost",response["quote"])
        self.assertNotIn("cost_price",response["quote"]["items"][0])
        code,chosen=self.call("/shared-inbox/"+sid+"/selection","POST",
            {"included_optional":[],"revision":0},recipient)
        self.assertEqual(code,200,chosen)
        self.assertEqual(chosen["selected_total_kopecks"],10000)
        self.assertEqual(self.call("/shared-inbox/"+sid+"/selection","POST",
            {"included_optional":[1],"revision":0},recipient)[0],409)
        code,approved=self.call("/shared-inbox/"+sid+"/approve","POST",{
            "revision":1,"action":"approve"
        },recipient)
        self.assertEqual(code,200,approved)
        self.assertEqual(approved["status"],"changes_requested")
        notified=self.call("/shares/"+sid,token=owner)
        self.assertEqual(notified[0],200,notified)
        self.assertEqual(notified[1]["response"]["status"],"changes_requested")
        self.assertEqual(self.call("/shares/"+sid,token=outsider)[0],404)
        quote_data=self.call("/quotes/"+qid,token=owner)[1]["quote"]
        self.assertEqual(quote_data["amount_kopecks"],15000)
        self.assertNotEqual(quote_data["approval_state"],"approved")
        self.assertEqual(self.call("/shared-inbox/"+sid+"/approve","POST",{
            "revision":2,"action":"approve"
        },recipient)[0],409)

    def test_unknown_recipient_receives_an_invite_without_access_token(self):
        owner,_=self.account("five-mailer")
        _,created=self.call("/quotes","POST",{
            "title":"Монтаж","client":"Новый заказчик","amount":6000
        },owner)
        quote=created["quote"]
        self.assertEqual(self.call("/quotes/"+quote["id"]+"/publish","POST",{
            "review_confirmed":True,"revision":quote["revision"]
        },owner)[0],200)
        with patch("backend.app.mail") as smtp:
            status,result=self.call("/shares","POST",{
                "quote_id":quote["id"],"email":"new-client-external@example.org"
            },owner)
        self.assertEqual(status,201,result)
        self.assertNotIn("delivery",result)
        self.assertNotIn("token",result)
        smtp.assert_called_once()
        to,subject,text=smtp.call_args.args
        self.assertEqual(to,"new-client-external@example.org")
        self.assertTrue(text.startswith("http://localhost:0/app?share="))
        self.assertNotIn("&invite=",text)
        self.assertIn("rustore.ru",text)
        self.assertEqual(self.call("/shared-inbox",token=owner)[1]["inbox"],[])

    def test_invalid_selection_never_updates_published_sum(self):
        owner,_=self.account("five-unsafe-quote")
        recipient,_=self.account("five-unsafe-recipient")
        _,created=self.call("/quotes","POST",{
            "title":"Отделка балкона","client":"Клиент",
            "items":[
                {"name":"Основа","quantity":"2","unit_price":2400,"unit":"м²"},
                {"name":"Дополнительная отделка","quantity":"1","unit_price":900,"unit":"м²","optional":True},
            ]
        },owner)
        quote=created["quote"]
        self.assertEqual(self.call("/quotes/"+quote["id"]+"/publish","POST",{
            "review_confirmed":True,"revision":quote["revision"]
        },owner)[0],200)
        sid=self.call("/shares","POST",{
            "quote_id":quote["id"],"email":"five-unsafe-recipient@test.invalid"
        },owner)[1]["id"]
        for selected in ([0],[99],[1,1],["1"],[1.0]):
            code,_=self.call("/shared-inbox/"+sid+"/selection","POST",{
                "included_optional":selected,"revision":0,"total_kopecks":1
            },recipient)
            self.assertEqual(code,400,selected)
        code,response=self.call("/shared-inbox/"+sid,token=recipient)
        self.assertEqual(code,200,response)
        self.assertEqual(response["selected_total_kopecks"],5700)
        self.assertEqual(self.call("/quotes/"+quote["id"],token=owner)[1]["quote"]["amount_kopecks"],5700)

    def test_equally_priced_optional_lines_cannot_change_scope_on_approval(self):
        owner,_=self.account("same-price-owner")
        recipient,_=self.account("same-price-client")
        rows=[
            {"name":"Основная работа","quantity":"1","unit":"шт.","unit_price":1000},
            {"name":"Вариант A","quantity":"1","unit":"шт.","unit_price":2000,"optional":True,"included":True},
            {"name":"Вариант B","quantity":"1","unit":"шт.","unit_price":2000,"optional":True,"included":False},
        ]
        _,created=self.call("/quotes","POST",{"title":"Варианты","client":"Заказчик","items":rows},owner)
        q=created["quote"]
        self.assertEqual(self.call("/quotes/"+q["id"]+"/publish","POST",{
            "review_confirmed":True,"revision":q["revision"]
        },owner)[0],200)
        share=self.call("/shares","POST",{
            "quote_id":q["id"],"email":"same-price-client@test.invalid"
        },owner)[1]["id"]
        changed=self.call("/shared-inbox/"+share+"/selection","POST",{
            "revision":0,"included_optional":[2]
        },recipient)
        self.assertEqual(changed[0],200,changed)
        self.assertEqual(changed[1]["selected_total_kopecks"],3000)
        approved=self.call("/shared-inbox/"+share+"/approve","POST",{
            "revision":1,"action":"approve"
        },recipient)
        self.assertEqual(approved[0],200,approved)
        self.assertEqual(approved[1]["status"],"changes_requested")
        self.assertNotEqual(self.call("/quotes/"+q["id"],token=owner)[1]["quote"]["approval_state"],"approved")

    def test_unedited_selection_can_approve_original_quote(self):
        owner,_=self.account("five-second-sender")
        recipient,_=self.account("five-second-recipient")
        _,res=self.call("/quotes","POST",{"title":"Отделка","client":"Заказчик",
            "items":[{"name":"Плитка","quantity":"1","unit":"шт.","unit_price":1100}]},owner)
        q=res["quote"];qid=q["id"]
        self.assertEqual(self.call("/quotes/"+qid+"/publish","POST",{
            "review_confirmed":True,"revision":q["revision"]
        },owner)[0],200)
        sid=self.call("/shares","POST",{
            "quote_id":qid,"email":"five-second-recipient@test.invalid",
        },owner)[1]["id"]
        code,data=self.call("/shared-inbox/"+sid+"/approve","POST",
            {"revision":0,"action":"approve"},recipient)
        self.assertEqual(code,200,data)
        self.assertEqual(data["status"],"approved")
        self.assertEqual(self.call("/quotes/"+qid,token=owner)[1]["quote"]["approval_state"],"approved")
