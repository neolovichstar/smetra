"""Disposable, loopback-only real API server for protected-estimate browser tests."""
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT))
    from scripts.fixture_network import restrict_to_loopback
    restrict_to_loopback()
    if any(os.getenv(name) for name in ("DATABASE_URL", "RUNTIME_DATABASE_URL", "VERCEL")):
        raise RuntimeError("This fixture requires a disposable local SQLite database")
    os.environ["ALLOW_UNVERIFIED_SIGNUP"] = "1"
    os.environ['OPENROUTER_API_KEY'] = 'local-browser-fixture-with-network-blocked'
    os.environ['ASSISTANT_WORKER_SECRET'] = 'local-browser-fixture-worker-secret-only-2026'
    from tests.test_protected_estimates import ProtectedEstimateTests
    ProtectedEstimateTests.setUpClass()
    fixture = ProtectedEstimateTests()
    fixture.mod.ORIGIN = fixture.base
    fixture.mod.BROWSER_ORIGINS = frozenset((fixture.base,))
    fixture.setUp()
    with fixture.mod.db() as con:
        con.execute("UPDATE users SET entitlement_until=? WHERE id=?", (fixture.mod.now()+86400, fixture.owner_id))
    link, token = fixture.link()
    data = {
        "base": fixture.base, "quote": fixture.quote, "pid": os.getpid(),
        "owner": {"token": fixture.owner, "id": fixture.owner_id,
                  "email": fixture.recipient_email.replace("-client@", "@")},
        "recipient": {"token": fixture.recipient, "id": fixture.recipient_id, "email": fixture.recipient_email},
        "link": link, "url": fixture.base + "/protected-estimate#" + token,
    }
    code, project = fixture.call("/projects", "POST", {"name": "Завершённый заказ для проверки расценок", "amount_kopecks": 5000000}, fixture.owner)
    if code != 201:
        raise RuntimeError(project)
    code, obj = fixture.call("/construction/objects", "POST", {"name": "Фактические расценки — тестовый объект"}, fixture.owner)
    if code != 201:
        raise RuntimeError(obj)
    object_id = obj["object"]["id"]
    path = "/construction/objects/" + object_id
    quantities = {}
    for kind, title, unit in (("work", "Укладка плитки", "м²"), ("material", "Плиточный клей", "кг")):
        code, result = fixture.call(path+"/quantities", "POST", {"kind": kind, "title": title, "unit": unit, "formula": "10", "unit_price": 10000}, fixture.owner)
        if code != 201:
            raise RuntimeError(result)
        quantities[kind] = result["quantity"]["id"]
    fixture.call(path+"/facts", "POST", {"quantity_id": quantities["work"], "quantity": "10"}, fixture.owner)
    for quantity, price in (("2", 10000), ("3", 20000)):
        fixture.call(path+"/purchases", "POST", {"material_id": quantities["material"], "quantity": quantity, "unit_price_kopecks": price, "status": "received", "purchased_on": "2026-11-01"}, fixture.owner)
    with fixture.mod.db() as con:
        con.execute("UPDATE construction_objects SET project_id=? WHERE id=?", (project["item"]["id"], object_id))
        con.execute("UPDATE projects SET status='completed' WHERE id=?", (project["item"]["id"],))
    data["workflow"] = {"object_id": object_id, **quantities}
    code, open_project = fixture.call("/projects", "POST", {"name": "Открытый заказ для допработ", "amount_kopecks": 1000000, "internal_cost": 500000, "due_date": "2026-12-01"}, fixture.owner)
    if code != 201:
        raise RuntimeError(open_project)
    code, open_obj = fixture.call("/construction/objects", "POST", {"name": "Объект для защищённых допработ"}, fixture.owner)
    if code != 201:
        raise RuntimeError(open_obj)
    with fixture.mod.db() as con:
        con.execute("UPDATE construction_objects SET project_id=? WHERE id=?", (open_project["item"]["id"], open_obj["object"]["id"]))
    data["workflow"].update(open_object_id=open_obj["object"]["id"], open_project_id=open_project["item"]["id"])
    from backend.business import identity, stamp
    thread_id = identity()
    with fixture.mod.db() as con:
        workspace = con.execute('SELECT workspace_id FROM workspace_members WHERE user_id=? AND role=\'owner\'',
                                (fixture.owner_id,)).fetchone()[0]
        con.execute('INSERT INTO assistant_conversations(id,workspace_id,user_id,title,context_entity,context_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                    (thread_id, workspace, fixture.owner_id, 'Проверка чистого поля ввода', 'quotes', fixture.quote['id'], stamp(), stamp()))
        con.execute('INSERT INTO assistant_messages(id,workspace_id,user_id,conversation_id,role,content,created_at) VALUES(?,?,?,?,?,?,?)',
                    (identity(), workspace, fixture.owner_id, thread_id, 'user', 'Проверь смету по дизайн-проекту', stamp()))
    data['assistant_thread_id'] = thread_id
    (ROOT / "data/protected-estimates-fixture.json").write_text(json.dumps(data), encoding="utf-8")
    print("PROTECTED_ESTIMATES_FIXTURE_READY " + fixture.base, flush=True)
    try:
        threading.Event().wait()
    finally:
        fixture.tearDownClass()


if __name__ == "__main__":
    main()
