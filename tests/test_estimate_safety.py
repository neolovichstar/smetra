"""Server-side regression tests for safe AI estimate drafting and consent."""
import base64
import urllib.request
import io
import json
import os
import unittest
from unittest.mock import patch

from PIL import Image

from backend.documents import pdf
from backend.estimate_safety import AI_ESTIMATE_DISCLAIMER
from tests.test_business import BusinessFlows


class _Lease:
    def release(self):
        pass


def _provider_reply(payload):
    original_urlopen = urllib.request.urlopen

    def reply(request, *args, **kwargs):
        if request.full_url.startswith("https://openrouter.ai/"):
            return _Response(payload)
        return original_urlopen(request, *args, **kwargs)

    return reply


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload, ensure_ascii=False).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.payload[:size]


class EstimateSafetyTests(unittest.TestCase):
    setUpClass = classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(BusinessFlows.tearDownClass.__func__)
    setUp = BusinessFlows.setUp
    call = BusinessFlows.call
    account = BusinessFlows.account

    def test_email_registration_requires_explicit_versioned_consent(self):
        status, result = self.call(
            "/auth/register",
            "POST",
            {
                "email": "no-consent@test.invalid",
                "name": "No consent",
                "password": "secure twelve password",
            },
        )
        self.assertEqual(status, 400, result)
        self.assertIn("соглашение", result["error"].lower())

    def test_registration_consent_is_separate_from_first_ai_use_consent(self):
        status, registered = self.call(
            "/auth/register",
            "POST",
            {
                "email": "consent-separation@test.invalid",
                "name": "consent-separation",
                "password": "secure twelve password",
                "legal_acceptance": True,
                "legal_version": "2026-10-19-registration-v1",
            },
        )
        self.assertEqual(status, 200, registered)
        token, user_id = registered["token"], registered["user"]["id"]
        status, result = self.call("/me/legal-consent", token=token)
        self.assertEqual(status, 200, result)
        self.assertFalse(result["accepted"], "Registration consent must not skip the first-use AI prompt")
        with self.mod.db() as con:
            rows = con.execute(
                "SELECT document_version,source FROM legal_acceptances WHERE user_id=?",
                (user_id,),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["document_version"], "2026-10-19-registration-v1")
        self.assertEqual(rows[0]["source"], "registration")

    def test_ai_endpoints_cannot_bypass_server_side_consent(self):
        token, user_id = self.account("consent-gate")
        with self.mod.db() as con:
            con.execute("DELETE FROM legal_acceptances WHERE user_id=?", (user_id,))

        status, result = self.call("/me/legal-consent", token=token)
        self.assertEqual(status, 200, result)
        self.assertFalse(result["accepted"])

        status, result = self.call(
            "/ai/draft", "POST", {"text": "Ремонт ванной"}, token
        )
        self.assertEqual(status, 428, result)

        status, result = self.call(
            "/me/legal-consent",
            "POST",
            {"accepted": True, "version": "older-version"},
            token,
        )
        self.assertEqual(status, 400, result)

        status, result = self.call(
            "/me/legal-consent",
            "POST",
            {"accepted": True, "version": "2026-10-19-ai-estimate-v1"},
            token,
        )
        self.assertEqual(status, 200, result)
        self.assertTrue(result["accepted"])

        with self.mod.db() as con:
            rows = con.execute(
                "SELECT document_version,source FROM legal_acceptances WHERE user_id=?",
                (user_id,),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["document_version"], "2026-10-19-ai-estimate-v1")
        self.assertEqual(rows[0]["source"], "first_estimate")

    def test_ai_draft_is_structured_and_hidden_work_is_marked_for_measurement(self):
        token, _ = self.account("structured-draft")
        model_result = {
            "title": "Ремонт ванной",
            "client": "",
            "description": "Предварительный перечень, требует проверки",
            "terms": "Проверить объёмы и технологию на объекте",
            "items": [
                {
                    "name": "Демонтаж плитки",
                    "description": "Снять существующую облицовку",
                    "quantity": "12",
                    "unit": "м²",
                    "unit_price": 0,
                    "requires_measurement": False,
                },
                {
                    "name": "Грунтовка стен",
                    "description": "Подготовка основания перед отделкой",
                    "quantity": "12",
                    "unit": "м²",
                    "unit_price": 3500,
                    "requires_measurement": True,
                },
            ],
        }
        wire = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(model_result, ensure_ascii=False)},
            }],
            "usage": {"prompt_tokens": 50, "completion_tokens": 80},
        }
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-only", OPENROUTER_MODEL="openrouter/free"),
            patch("backend.redis_infra.acquire_lock", return_value=_Lease()),
            patch("backend.ai.urllib.request.urlopen", side_effect=_provider_reply(wire)) as opener,
        ):
            status, result = self.call(
                "/ai/draft", "POST", {"text": "Подготовить ванную комнату"}, token
            )

        self.assertEqual(status, 200, result)
        self.assertTrue(result["requires_review"])
        draft = result["draft"]
        self.assertNotIn("total", draft)
        self.assertNotIn("amount_kopecks", draft)
        self.assertEqual(
            set(draft["items"][0]),
            {"name", "description", "quantity", "unit", "unit_price", "requires_measurement"},
        )
        self.assertTrue(draft["items"][0]["requires_measurement"])
        self.assertIn("Требует замера по месту", draft["items"][0]["description"])
        self.assertTrue(draft["items"][1]["requires_measurement"])
        self.assertIn("Требует замера по месту", draft["items"][1]["description"])

        payload = json.loads(opener.call_args.args[0].data)
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        schema = payload["response_format"]["json_schema"]["schema"]
        self.assertTrue(schema["additionalProperties"] is False)
        self.assertNotIn("total", schema["properties"])
        self.assertIn("requires_measurement", schema["properties"]["items"]["items"]["properties"])
        self.assertIn("черновой ассистент-структуризатор", payload["messages"][0]["content"])
        self.assertIn("итоговую сумму", payload["messages"][0]["content"])

    def test_model_cannot_smuggle_a_total_into_the_structured_schema(self):
        token, _ = self.account("draft-total-rejected")
        model_result = {
            "title": "Ремонт",
            "client": "",
            "description": "Черновик",
            "terms": "",
            "total": 15000000,
            "items": [{
                "name": "Работа",
                "description": "",
                "quantity": "1",
                "unit": "шт.",
                "unit_price": 15000000,
                "requires_measurement": False,
            }],
        }
        wire = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(model_result, ensure_ascii=False)},
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 20},
        }
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-only", OPENROUTER_MODEL="openrouter/free"),
            patch("backend.redis_infra.acquire_lock", return_value=_Lease()),
            patch("backend.ai.urllib.request.urlopen", side_effect=_provider_reply(wire)),
        ):
            status, result = self.call(
                "/ai/draft", "POST", {"text": "Составь смету"}, token
            )
        self.assertEqual(status, 502, result)
        self.assertIn("черновик", result["error"].lower())


    def test_uploaded_photo_is_normalized_and_sent_to_the_vision_model(self):
        token, _ = self.account("photo-estimate")
        image_bytes = io.BytesIO()
        Image.new("RGB", (12, 8), (240, 240, 240)).save(image_bytes, format="PNG")
        image_content = base64.b64encode(image_bytes.getvalue()).decode("ascii")
        model_result = {
            "title": "Предварительный расчёт ванной",
            "client": "",
            "description": "Состав работ определён только по видимой части фотографии",
            "terms": "Проверить размеры и скрытые коммуникации на объекте",
            "items": [{
                "name": "Подготовка основания",
                "description": "Объём уточнить после осмотра",
                "quantity": "1",
                "unit": "компл.",
                "unit_price": 0,
                "requires_measurement": True,
            }],
        }
        wire = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(model_result, ensure_ascii=False)},
            }],
            "usage": {"prompt_tokens": 60, "completion_tokens": 40},
        }
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-only", OPENROUTER_MODEL="openrouter/free"),
            patch("backend.redis_infra.acquire_lock", return_value=_Lease()),
            patch("backend.ai.urllib.request.urlopen", side_effect=_provider_reply(wire)) as opener,
        ):
            status, result = self.call(
                "/ai/draft",
                "POST",
                {
                    "text": "Оцени видимые работы, не угадывай размеры",
                    "file": {
                        "name": "bathroom.png",
                        "mime": "image/png",
                        "content": image_content,
                    },
                },
                token,
            )

        self.assertEqual(status, 200, result)
        self.assertTrue(result["requires_review"])
        payload = json.loads(opener.call_args.args[0].data)
        user_message = payload["messages"][1]["content"]
        self.assertIsInstance(user_message, list)
        self.assertEqual(user_message[0]["type"], "text")
        self.assertIn("не угадывай размеры", user_message[0]["text"])
        self.assertEqual(user_message[1]["type"], "image_url")
        image_url = user_message[1]["image_url"]["url"]
        self.assertTrue(image_url.startswith("data:image/jpeg;base64,"))
        self.assertIn("Требует замера по месту", result["draft"]["items"][0]["description"])

    def test_general_assistant_chat_accepts_and_forwards_a_photo(self):
        token, _ = self.account("assistant-photo")
        image_bytes = io.BytesIO()
        Image.new("RGB", (16, 10), (180, 190, 200)).save(image_bytes, format="PNG")
        encoded = base64.b64encode(image_bytes.getvalue()).decode("ascii")
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-only", OPENROUTER_MODEL="openrouter/free"),
            patch("backend.assistant.query_model", return_value={"content": "На фото видны поверхности. Размеры нужно измерить отдельно."}) as model,
        ):
            status, result = self.call(
                "/assistant/chat",
                "POST",
                {
                    "text": "Что ты видишь на фото?",
                    "image": {
                        "name": "room.png",
                        "mime": "image/png",
                        "content": encoded,
                    },
                },
                token,
            )
        self.assertEqual(status, 200, result)
        self.assertIn("Размеры нужно измерить", result["answer"])
        messages = model.call_args.args[0]
        user_message = messages[-1]
        self.assertEqual(user_message["role"], "user")
        self.assertIsInstance(user_message["content"], list)
        self.assertEqual(user_message["content"][0]["text"], "Что ты видишь на фото?")
        self.assertEqual(user_message["content"][1]["type"], "image_url")
        self.assertTrue(user_message["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_model_cannot_hide_a_final_sum_inside_narrative_text(self):
        token, _ = self.account("draft-narrative-total")
        model_result = {
            "title": "Ремонт ванной",
            "client": "",
            "description": "Итого ремонт ванной обойдётся в 150 000 рублей.",
            "terms": "",
            "items": [{
                "name": "Укладка плитки",
                "description": "Укладка напольной плитки",
                "quantity": "12",
                "unit": "м²",
                "unit_price": 350000,
                "requires_measurement": False,
            }],
        }
        wire = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(model_result, ensure_ascii=False)},
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 20},
        }
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-only", OPENROUTER_MODEL="openrouter/free"),
            patch("backend.redis_infra.acquire_lock", return_value=_Lease()),
            patch("backend.ai.urllib.request.urlopen", side_effect=_provider_reply(wire)),
        ):
            status, result = self.call(
                "/ai/draft", "POST", {"text": "Ремонт ванной"}, token
            )
        self.assertEqual(status, 502, result)
        self.assertIn("черновик", result["error"].lower())


    def test_ai_generated_estimate_pdf_contains_fixed_disclaimer(self):
        snapshot = {
            "company": "Сметра QA",
            "title": "Предварительная смета",
            "client": "Клиент",
            "company_details": "",
            "description": "Черновик по описанию",
            "items": [{
                "name": "Грунтовка стен",
                "description": "Требует замера по месту",
                "quantity": "12",
                "unit": "м²",
                "unit_price": 3500,
                "subtotal": 42000,
                "included": True,
            }],
            "amount_kopecks": 42000,
            "currency": "RUB",
            "due_date": "",
            "terms": "Предварительный состав",
            "ai_generated": 1,
        }
        document = {
            "kind": "estimate",
            "number": 1,
            "name": "Смета",
            "template": "Minimal",
            "snapshot": json.dumps(snapshot, ensure_ascii=False),
        }
        from pypdf import PdfReader

        rendered = pdf(document)
        extracted = " ".join(
            " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(rendered)).pages).split()
        )
        for fragment in (
            'Расчет сгенерирован ИИ-ассистентом "сметра."',
            "предварительным черновиком",
            "Обязательно проверьте объемы, технологию и цены перед подписанием",
            "Сервис не несет ответственности за финансовые риски сторон",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, extracted)
        self.assertIn("Требует замера по месту", extracted)
        self.assertIn(AI_ESTIMATE_DISCLAIMER.split(".")[0], extracted)

    def test_ai_estimate_provenance_is_preserved_when_editor_saves(self):
        token, uid = self.account("ai-provenance")
        self.call("/workspace", token=token)
        import uuid
        draft_id = str(uuid.uuid4())
        with self.mod.db() as con:
            wid = con.execute("SELECT id FROM workspaces WHERE owner_id=?", (uid,)).fetchone()["id"]
            con.execute("INSERT INTO ai_usage(id,workspace_id,user_id,action,model,status,created_at) VALUES(?,?,?,'estimate_draft','test','succeeded',?)",
                        (draft_id, wid, uid, int(__import__("time").time())))
        status, created = self.call(
            "/quotes",
            "POST",
            {
                "title": "AI-черновик",
                "ai_draft_usage_id": draft_id,
                "client": "Клиент",
                "ai_generated": True,
                "items": [{
                    "name": "Грунтовка",
                    "description": "Требует замера по месту",
                    "quantity": "12",
                    "unit": "м²",
                    "unit_price": 3500,
                }],
            },
            token,
        )
        self.assertEqual(status, 201, created)
        quote = created["quote"]
        self.assertEqual(quote["ai_generated"], 1)
        status, updated = self.call(
            "/quotes/" + quote["id"],
            "PATCH",
            {
                "revision": quote["revision"],
                "title": "AI-черновик — уточнён",
                "items": quote["items"],
            },
            token,
        )
        self.assertEqual(status, 200, updated)
        self.assertEqual(updated["quote"]["ai_generated"], 1)

    def test_ai_estimate_pdf_download_requires_review_confirmation(self):
        token, _ = self.account("ai-pdf-gate")
        status, created = self.call(
            "/quotes",
            "POST",
            {
                "title": "AI-черновик для PDF",
                "client": "Клиент",
                "ai_generated": True,
                "items": [{
                    "name": "Грунтовка",
                    "description": "Требует замера по месту",
                    "quantity": "12",
                    "unit": "м²",
                    "unit_price": 1000,
                }],
            },
            token,
        )
        self.assertEqual(status, 201, created)
        status, doc = self.call(
            "/documents",
            "POST",
            {
                "quote_id": created["quote"]["id"],
                "kind": "estimate",
                "review_confirmed": True,
            },
            token,
        )
        self.assertEqual(status, 201, doc)
        status, rejected = self.call(
            "/documents/" + doc["document"]["id"] + "/pdf",
            token=token,
            raw=True,
        )
        self.assertEqual(status, 400, rejected)
        status, rendered = self.call(
            "/documents/" + doc["document"]["id"] + "/pdf?review_confirmed=1",
            token=token,
            raw=True,
        )
        self.assertEqual(status, 200)
        self.assertTrue(rendered.startswith(b"%PDF-"))

    def test_server_rejects_quote_publication_without_review_confirmation(self):
        token, _ = self.account("quote-review-required")
        status, created = self.call(
            "/quotes",
            "POST",
            {
                "title": "Смета на ремонт ванной",
                "client": "Клиент",
                "items": [{
                    "name": "Грунтовка",
                    "quantity": "12",
                    "unit": "м²",
                    "unit_price": 3500,
                }],
            },
            token,
        )
        self.assertEqual(status, 201, created)
        quote = created["quote"]
        status, rejected = self.call(
            "/quotes/" + quote["id"] + "/publish",
            "POST",
            {"revision": quote["revision"]},
            token,
        )
        self.assertEqual(status, 400, rejected)
        self.assertIn("провер", rejected["error"].lower())
        status, published = self.call(
            "/quotes/" + quote["id"] + "/publish",
            "POST",
            {"revision": quote["revision"], "review_confirmed": True},
            token,
        )
        self.assertEqual(status, 200, published)


if __name__ == "__main__":
    unittest.main()
