"""Isolated real API fixture for the Android design smoke test (no production data)."""

import importlib.util
import json
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import urllib.request
import uuid
import base64
import hashlib
import hmac
import time
from unittest.mock import patch
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix="android-ui-", dir=ROOT / "data") as folder:
        os.environ.update(
            DB_PATH=str(Path(folder) / "test.sqlite3"),
            UPLOAD_DIR=str(Path(folder) / "uploads"),
            PUBLIC_ORIGIN="http://localhost:8084",
            PORT="8084",
            OPENROUTER_API_KEY="fixture-not-a-real-key",
            ASSISTANT_WORKER_SECRET="isolated-fixture-worker-secret-0123456789",
        )
        os.environ.pop("SMTP_HOST", None)
        spec = importlib.util.spec_from_file_location(
            "android_ui_app", ROOT / "backend/app.py"
        )
        app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app)
        app.migrate()
        class UiHandler(app.Handler):
            lost_quote_response = False
            lost_attachment_responses = set()

            def send_json(self, status, value, cookie=None):
                if status == 201 and isinstance(value, dict):
                    marker = None
                    if self.path == "/api/files" and value.get("file", {}).get("name") in ("brief.md", "retry-web.md"):
                        marker = "file:" + value["file"]["name"]
                    elif self.path == "/api/assistant/conversations" and value.get("conversation", {}).get("title") == "brief.md":
                        marker = "conversation:brief.md"
                    if marker and marker not in UiHandler.lost_attachment_responses:
                        UiHandler.lost_attachment_responses.add(marker)
                        return super().send_json(503, {"error": "Тестовая потеря ответа вложения"}, cookie)
                # Commit a quote, then lose its first success response. The APK must
                # restore the draft and retry without spending another quote slot.
                if (
                    self.path == "/api/quotes"
                    and status == 201
                    and isinstance(value, dict)
                    and value.get("quote", {}).get("title") == "Ремонт квартиры"
                    and not UiHandler.lost_quote_response
                ):
                    UiHandler.lost_quote_response = True
                    return super().send_json(503, {"error": "Тестовая потеря ответа"}, cookie)
                return super().send_json(status, value, cookie)

        server = ThreadingHTTPServer(("127.0.0.1", 8084), UiHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()

        def call(path, body=None, token=None):
            headers = {"Content-Type": "application/json"}
            if body is not None:
                headers["Idempotency-Key"] = str(uuid.uuid4())
            if token:
                headers["Authorization"] = "Bearer " + token
            request = urllib.request.Request(
                "http://127.0.0.1:8084/api" + path,
                json.dumps(body).encode() if body is not None else None,
                headers,
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.load(response)

        account = call(
            "/auth/register",
            {
                "email": "android-design@test.invalid",
                "password": "android design test only",
                "name": "Александр",
            },
        )
        token = account["token"]
        from PIL import Image
        receipt_object = call('/construction/objects', {'name': 'Проверка чека'}, token)['object']['id']
        receipt_zone = call('/construction/objects/' + receipt_object + '/zones', {'name': 'Комната', 'length': '2', 'width': '1'}, token)['zone']['id']
        receipt_material = call('/construction/objects/' + receipt_object + '/quantities', {'zone_id': receipt_zone, 'kind': 'material', 'title': 'Тестовый материал', 'formula': 'area', 'unit_price': 10000}, token)['quantity']['id']
        receipt_image = io.BytesIO()
        Image.new('RGB', (30, 30), 'white').save(receipt_image, format='PNG')
        receipt_file = call('/files', {'construction_id': receipt_object, 'name': 'receipt.png', 'content': base64.b64encode(receipt_image.getvalue()).decode()}, token)['file']['id']
        call('/construction/objects/' + receipt_object + '/purchases', {'material_id': receipt_material, 'receipt_file_id': receipt_file, 'quantity': '2', 'unit_price_kopecks': 10000, 'status': 'received', 'purchased_on': '2026-10-01', 'notes': 'Сохранённое примечание'}, token)
        first_price = call(
            "/catalog",
            {
                "name": "Покраска стен",
                "price": 125000,
                "cost_price": 70000,
                "unit": "м²",
                "category": "Отделка",
                "article": "FIN-001",
                "item_type": "work",
                "description": "Подготовка и окраска в два слоя",
            },
            token,
        )["item"]
        call("/catalog/" + first_price["id"] + "/use", {}, token)
        call(
            "/catalog",
            {
                "name": "Краска интерьерная",
                "price": 25000,
                "cost_price": 18000,
                "unit": "л",
                "category": "Материалы",
                "item_type": "material",
            },
            token,
        )
        clients = []
        for name, email in [
            ("Студия Север", "hello@sever.example"),
            ("Анна Смирнова", "anna@example.org"),
        ]:
            clients.append(
                call(
                    "/clients",
                    {"name": name, "email": email, "phone": "+7 900 000-00-00"},
                    token,
                )["item"]
            )
        for index, (title, amount) in enumerate(
            [
                ("Интерьер студии", 18500000),
                ("Сайт для студии Север", 12800000),
                ("Айдентика и упаковка", 6400000),
            ]
        ):
            quote = call(
                "/quotes",
                {
                    "title": title,
                    "client": clients[index % 2]["name"],
                    "client_id": clients[index % 2]["id"],
                    "amount": amount,
                    **({"items": [{"name": "Концепция и дизайн", "quantity": "1", "unit_price": amount}]} if index in (0, 2) else {}),
                    "description": "Концепция, дизайн и подготовка финальных материалов. Два этапа согласования.",
                },
                token,
            )["quote"]
            if index < 2:
                quote = call(
                    "/quotes/" + quote["id"] + "/publish",
                    {"revision": quote["revision"]},
                    token,
                )["quote"]
            if index == 0:
                public_token = quote["public_url"].split("quote=")[1]
                call(
                    "/public/accept",
                    {"token": public_token, "version": 1, "name": "Тестовый клиент"},
                )
                project = call("/quotes/" + quote["id"] + "/project", {}, token)[
                    "project"
                ]
                call(
                    "/receipts",
                    {
                        "project_id": project["id"],
                        "amount_kopecks": 6500000,
                        "method": "bank_transfer",
                    },
                    token,
                )
                for name, status in [
                    ("Концепция и планировка", "completed"),
                    ("Дизайн и визуализация", "in_progress"),
                    ("Передача материалов", "planned"),
                ]:
                    call(
                        "/stages",
                        {"project_id": project["id"], "name": name, "status": status},
                        token,
                    )
                call(
                    "/tasks",
                    {
                        "project_id": project["id"],
                        "name": "Согласовать материалы",
                        "description": "Уточнить палитру и фактуры перед визуализацией.",
                    },
                    token,
                )
        structure_qa = os.getenv('SMETRA_STRUCTURE_QA') == '1'
        if os.getenv('SMETRA_OFFICE_QA') == '1':
            from tests import office_fixtures

            for name, raw in [('brief.docx', office_fixtures.docx('Техническое задание', [['Работа', 'Цена'], ['Покраска', '15000']])),
                              ('prices.xlsx', office_fixtures.xlsx()),
                              ('prices.csv', 'Работа;Цена\nПокраска;15000\nДоставка;2000'.encode())]:
                call('/files', {'client_id': clients[0]['id'], 'name': name,
                               'content': base64.b64encode(raw).decode()}, token)
        resource_qa = os.getenv('SMETRA_RESOURCE_QA') == '1'
        seed_tool = 'restructure_quote_items' if structure_qa else 'bulk_quote_items'
        seed_args = {'id': quote['id'], 'operation': 'insert', 'items': [{'name': 'Подготовка стен', 'unit': 'м²', 'quantity': '1.25', 'unit_price': 10005}]} if structure_qa else {'id': quote['id'], 'rows': [1], 'field': 'unit_price', 'operation': 'multiply', 'value': '1.1'}
        resource_file = None
        if resource_qa:
            resource_file = call('/files', {'client_id': clients[0]['id'], 'name': 'resources.md',
                                          'content': base64.b64encode('# Рабочий документ\nСрок 30 дней.\n'.encode()).decode()}, token)['file']
            seed_tool, seed_args = 'create_document', {'quote_id': quote['id'], 'kind': 'invoice', 'template': 'Modern'}
        if structure_qa or resource_qa:
            with app.db() as con:
                con.execute("UPDATE users SET plan='pro',entitlement_until=? WHERE email=?", (int(time.time()) + 3600, 'android-design@test.invalid'))
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-not-a-real-key"), patch(
            "backend.assistant.query_model",
            return_value={"content": None, "tool_calls": [{"id": "fixture-bulk", "type": "function",
                "function": {"name": seed_tool, "arguments": json.dumps(seed_args)}}]},
        ):
            call("/assistant/chat", {"text": "Увеличь цену на 10%"}, token)
        # Deterministic streaming exercises the real quota/history/context routes;
        # this isolated fixture never contacts a model provider.
        def stream_fixture(messages, on_delta):
            prompt = next((message['content'] for message in reversed(messages) if message['role'] == 'user'), '')
            if resource_qa:
                command = {
                    'Переименуй тестовый файл': ('rename_file', {'id': resource_file['id'], 'name': 'Сроки проекта.md'}),
                    'Перенеси тестовый файл': ('move_file', {'id': resource_file['id'], 'target': 'projects', 'target_id': project['id']}),
                }.get(prompt)
                if command:
                    return {'content': None, 'tool_calls': [{'id': 'resource-fixture', 'type': 'function',
                            'function': {'name': command[0], 'arguments': json.dumps(command[1])}}]}
            if structure_qa:
                command = {
                    'Добавь тестовую опцию': ('restructure_quote_items', {'operation': 'insert', 'items': [{'name': 'Опциональная доставка', 'unit_price': 5000, 'optional': True, 'included': False}]}),
                    'Включи тестовую опцию': ('bulk_quote_items', {'rows': [2], 'field': 'included', 'value': True}),
                    'Переставь тестовые строки': ('restructure_quote_items', {'operation': 'reorder', 'rows': [2, 1]}),
                    'Удали тестовую опцию': ('restructure_quote_items', {'operation': 'remove', 'rows': [2]}),
                }.get(prompt)
                if command:
                    name, arguments = command
                    return {'content': None, 'tool_calls': [{'id': 'fixture-structure', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps({'id': quote['id'], **arguments})}}]}
            selected = "Пользователь явно выбрал контекст: смета" in messages[0]["content"]
            file_selected = "Пользователь явно выбрал контекст: файл" in messages[0]["content"]
            answer = "Контекст сметы получен." if selected else "Контекст файла получен." if file_selected else "Контекст не выбран."
            for chunk in answer.split(" "):
                on_delta(chunk + " ")
            return {"content": answer}

        from backend import assistant

        assistant.query_model_stream = stream_fixture
        assistant.query_model = lambda messages: {"content": "Фоновая задача завершена."}
        from backend import receipt_ocr

        def receipt_fixture(*_):
            time.sleep(3)
            return {'merchant': 'Тестовый магазин', 'amount_kopecks': 123450, 'date': '2026-10-03'}

        receipt_ocr._request = receipt_fixture
        from backend import file_ocr

        def scan_fixture(_image):
            time.sleep(2)
            return 'SMETRA SCAN TEST. PAINT WALLS 12 m2. TOTAL 1234.50 RUB.'

        file_ocr.request_page = scan_fixture

        def background_fixture():
            # A separate HTTP invocation models the production scheduler.
            while True:
                threading.Event().wait(2)
                try:
                    moment, nonce = str(int(time.time())), uuid.uuid4().hex
                    signature = hmac.new(os.environ['ASSISTANT_WORKER_SECRET'].encode(),
                        ('smetra-assistant-worker:v1:' + moment + ':' + nonce).encode(),hashlib.sha256).hexdigest()
                    request = urllib.request.Request('http://127.0.0.1:8084/api/cron/assistant',
                        headers={'Authorization': f'Bearer v1.{moment}.{nonce}.{signature}'})
                    with urllib.request.urlopen(request, timeout=10) as response:
                        response.read()
                except OSError:
                    pass

        threading.Thread(target=background_fixture, daemon=True).start()
        file = call('/files', {'assistant_upload': True, 'name': 'brief.txt',
                    'content': base64.b64encode(b'file context').decode()}, token)['file']
        call('/assistant/conversations', {'title': 'Бриф проекта', 'context_entity': 'files', 'context_id': file['id']}, token)
        print("ANDROID_UI_FIXTURE_READY http://127.0.0.1:8084", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
