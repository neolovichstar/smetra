"""Isolated real API fixture for the Android design smoke test (no production data)."""

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import urllib.request
import uuid
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
        )
        os.environ.pop("SMTP_HOST", None)
        spec = importlib.util.spec_from_file_location(
            "android_ui_app", ROOT / "backend/app.py"
        )
        app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app)
        app.migrate()
        server = ThreadingHTTPServer(("127.0.0.1", 8084), app.Handler)
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
                    **({"items": [{"name": "Концепция и дизайн", "quantity": "1", "unit_price": amount}]} if index == 0 else {}),
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
