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
    from scripts.fixture_network import restrict_to_loopback
    restrict_to_loopback()
    port = int(os.getenv('SMETRA_FIXTURE_PORT', '8084'))
    # The emulator reaches the host as 10.0.2.2, so the Android screenshot run overrides the origin.
    origin = os.getenv('SMETRA_FIXTURE_ORIGIN', f'http://localhost:{port}')
    base_url = f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory(prefix="android-ui-", dir=ROOT / "data") as folder:
        # Fixtures must never inherit a production DB, cache, payment or mail service.
        for key in tuple(os.environ):
            if key in ('DATABASE_URL', 'RUNTIME_DATABASE_URL', 'VERCEL') or key.startswith(('REDIS_', 'KV_', 'UPSTASH_', 'YOOKASSA_', 'SMTP_', 'YANDEX_', 'VK_', 'GOOGLE_', 'CLOUD_')):
                os.environ.pop(key, None)
        os.environ.update(
            DB_PATH=str(Path(folder) / "test.sqlite3"),
            UPLOAD_DIR=str(Path(folder) / "uploads"),
            PUBLIC_ORIGIN=origin,
            PORT=str(port),
            OPENROUTER_API_KEY="fixture-not-a-real-key",
            ASSISTANT_WORKER_SECRET="isolated-fixture-worker-secret-0123456789",
        )
        os.environ.pop("SMTP_HOST", None)
        if not origin.startswith('http://localhost:'):
            os.environ['ALLOW_UNVERIFIED_SIGNUP'] = '1'
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

        server = ThreadingHTTPServer(("127.0.0.1", port), UiHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()

        def call(path, body=None, token=None):
            headers = {"Content-Type": "application/json"}
            if body is not None:
                headers["Idempotency-Key"] = str(uuid.uuid4())
            if token:
                headers["Authorization"] = "Bearer " + token
            request = urllib.request.Request(
                base_url + "/api" + path,
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
                "legal_acceptance": True,
                "legal_version": "2026-10-19-registration-v1",
            },
        )
        token = account["token"]
        call("/me/legal-consent", {"accepted": True, "version": "2026-10-19-ai-estimate-v1"}, token)
        if os.getenv('SMETRA_ACTION_QA') == '1':
            with app.db() as con:
                con.execute("UPDATE users SET role='admin',plan='pro',entitlement_until=?,email_verified_at=? WHERE id=?", (int(time.time())+3600,int(time.time()),account['user']['id']))
            with app.db() as con:
                wid = app.business.ensure_workspace(con, account['user'])
                con.execute("UPDATE workspaces SET plan='team_month',subscription_status='active',entitlement_until=?,seat_limit=5 WHERE id=?", (int(time.time())+3600,wid))
            call('/auth/register', {'email': 'ui-member@test.invalid', 'password': 'isolated member test password', 'name': 'UI member', 'legal_acceptance': True, 'legal_version': '2026-10-19-registration-v1'})
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
                    {"revision": quote["revision"], "review_confirmed": True},
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
            if os.getenv('SMETRA_DURABLE_QA') == '1' and prompt in ('UI durable question', 'UI cancel durable question'):
                on_delta('Поток начат. ')
                time.sleep(3)
                on_delta('Ответ сохранён.')
                return {'content': 'Поток начат. Ответ сохранён.'}
            if os.getenv('SMETRA_ACTION_QA') == '1' and prompt == 'UI slow question':
                on_delta('Тестовый поток начат. ')
                time.sleep(1)
                on_delta('Поток завершён.')
                return {'content': 'Тестовый поток начат. Поток завершён.'}
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
        from backend import community
        community._support_completion = lambda payload, timeout: {
            "reply": "Тестовое обращение передано сотруднику поддержки.",
            "escalate": True, "reason": "isolated_ui_fixture",
        }
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
                    request = urllib.request.Request(base_url + '/api/cron/assistant',
                        headers={'Authorization': f'Bearer v1.{moment}.{nonce}.{signature}'})
                    with urllib.request.urlopen(request, timeout=10) as response:
                        response.read()
                except OSError:
                    pass

        if os.getenv('SMETRA_DURABLE_QA') != '1':
            threading.Thread(target=background_fixture, daemon=True).start()
        file = call('/files', {'assistant_upload': True, 'name': 'brief.txt',
                    'content': base64.b64encode(b'file context').decode()}, token)['file']
        call('/assistant/conversations', {'title': 'Бриф проекта', 'context_entity': 'files', 'context_id': file['id']}, token)
        if os.getenv('SMETRA_QUOTE_REVIEW_QA') == '1':
            quote_review = call('/quotes', {'title': 'Сравнение условий', 'client': 'Тестовый клиент', 'terms': 'Срок 10 дней',
                                           'items': [{'name': 'Подготовка', 'unit_price': 10000}, {'name': 'Покраска', 'unit_price': 20000}, {'name': 'Доставка', 'unit_price': 3000}]}, token)['quote']
            quote_review = call('/quotes/' + quote_review['id'] + '/publish', {'revision': quote_review['revision'], 'review_confirmed': True}, token)['quote']

            def revise_review(quote, terms, items):
                payload = json.dumps({'revision': quote['revision'], 'terms': terms, 'items': items}).encode()
                request = urllib.request.Request(base_url + '/api/quotes/' + quote['id'], data=payload,
                                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}, method='PATCH')
                with urllib.request.urlopen(request) as response:
                    return json.load(response)['quote']

            quote_review = revise_review(quote_review, 'Срок 7 дней', [{**quote_review['items'][0], 'name': 'Подготовка поверхности', 'unit_price': 12000},
                                                                     quote_review['items'][1], {'name': 'Защита мебели', 'unit_price': 4000}])
            quote_review = call('/quotes/' + quote_review['id'] + '/publish', {'revision': quote_review['revision'], 'review_confirmed': True}, token)['quote']
            revise_review(quote_review, 'Срок 5 дней', quote_review['items'])
        if os.getenv('SMETRA_PROMO_QA') == '1':
            seed_promo(app, call)
        print("ANDROID_UI_FIXTURE_READY " + base_url, flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()


def seed_promo(app, call):
    """Believable construction data for real RuStore screenshots (isolated database only)."""
    # A separate account keeps the other fixtures' test records out of the pictures.
    account = call('/auth/register', {'email': 'promo@test.invalid', 'password': 'promo screenshots only', 'name': 'Александр Петров',
                                      'legal_acceptance': True, 'legal_version': '2026-10-19-registration-v1'})
    token = account['token']
    call('/me/legal-consent', {'accepted': True, 'version': '2026-10-19-ai-estimate-v1'}, token)
    with app.db() as con:
        con.execute("UPDATE users SET plan='pro',entitlement_until=?,email_verified_at=? WHERE id=?",
                    (int(time.time()) + 30 * 86400, int(time.time()), account['user']['id']))
    client = call('/clients', {'name': 'Ирина Ковалёва', 'email': 'irina@example.org', 'phone': '+7 900 123-45-67'}, token)['item']
    obj = call('/construction/objects', {'name': 'Квартира на Лесной, 54 м²'}, token)['object']['id']
    rooms = [('Гостиная', '5.2', '3.8'), ('Спальня', '4.1', '3.4'), ('Кухня', '3.6', '3.2'), ('Санузел', '2.1', '1.7')]
    for name, length, width in rooms:
        zone = call('/construction/objects/' + obj + '/zones', {'name': name, 'length': length, 'width': width, 'height': '2.7'}, token)['zone']['id']
        for title, formula, unit, price in [('Шпаклёвка стен', 'perimeter * height', 'м²', 45000), ('Покраска стен в 2 слоя', 'perimeter * height', 'м²', 38000),
                                            ('Ламинат с подложкой', 'area', 'м²', 65000)]:
            if name == 'Санузел' and title.startswith('Ламинат'):
                title, price = 'Укладка плитки', 180000
            call('/construction/objects/' + obj + '/quantities', {'zone_id': zone, 'kind': 'work', 'title': title, 'formula': formula, 'unit': unit, 'unit_price': price}, token)
    items = [('Демонтаж старых покрытий', 'м²', '54', 25000), ('Выравнивание стен', 'м²', '142', 52000), ('Покраска стен в 2 слоя', 'м²', '142', 38000),
             ('Укладка ламината', 'м²', '48', 65000), ('Укладка плитки в санузле', 'м²', '18', 180000), ('Электромонтаж, точка', 'шт', '36', 120000),
             ('Натяжной потолок', 'м²', '54', 90000), ('Вывоз мусора', 'рейс', '3', 450000)]
    quote = call('/quotes', {'title': 'Ремонт квартиры 54 м²', 'client': client['name'], 'client_id': client['id'],
                             'description': 'Комплексный ремонт: черновые и чистовые работы, материалы по согласованию.',
                             'terms': 'Срок 45 рабочих дней. Аванс 30%, оплата по этапам.',
                             'items': [{'name': n, 'unit': u, 'quantity': q, 'unit_price': p} for n, u, q, p in items]}, token)['quote']
    quote = call('/quotes/' + quote['id'] + '/publish', {'revision': quote['revision'], 'review_confirmed': True}, token)['quote']
    call('/public/accept', {'token': quote['public_url'].split('quote=')[1], 'version': 1, 'name': client['name']})
    project = call('/quotes/' + quote['id'] + '/project', {}, token)['project']
    call('/receipts', {'project_id': project['id'], 'amount_kopecks': 18000000, 'method': 'bank_transfer'}, token)
    for name, status in [('Демонтаж', 'completed'), ('Черновые работы', 'in_progress'), ('Чистовая отделка', 'planned')]:
        call('/stages', {'project_id': project['id'], 'name': name, 'status': status}, token)
    for name in ('Закупить шпаклёвку и грунт', 'Согласовать раскладку плитки', 'Вызвать электрика на прозвонку'):
        call('/tasks', {'project_id': project['id'], 'name': name}, token)
    call('/quotes', {'title': 'Ванная под ключ', 'client': 'Сергей Орлов', 'description': 'Плитка, сантехника, вентиляция.',
                     'items': [{'name': 'Укладка плитки', 'unit': 'м²', 'quantity': '24', 'unit_price': 180000},
                               {'name': 'Монтаж инсталляции', 'unit': 'шт', 'quantity': '1', 'unit_price': 850000}]}, token)
    answer = ('Посчитал покраску гостиной 5,2 × 3,8 м при высоте 2,7 м:\n\n'
              '- **Стены:** 48,6 м², за вычетом окна и двери ≈ 44 м²\n'
              '- **Краска:** 2 слоя × 0,12 л/м² ≈ 10,6 л — 3 банки по 4,5 л\n'
              '- **Работа:** 44 м² × 380 ₽ = **16 720 ₽**\n\n'
              'Добавить эти строки в смету «Ремонт квартиры 54 м²»?')
    with patch("backend.assistant.query_model", return_value={"content": answer}):
        call('/assistant/chat', {'text': 'Сколько краски и работы на гостиную 5,2 на 3,8, потолки 2,7?'}, token)
    session_file = os.getenv('SMETRA_FIXTURE_SESSION_FILE')
    if session_file:
        Path(session_file).write_text(token, encoding='utf-8')


if __name__ == "__main__":
    main()
