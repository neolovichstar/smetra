"""Interior design specification contract and workspace isolation regression tests."""
import sqlite3
import unittest
from pathlib import Path

from backend import business
from backend.designer import route

MIGRATION = Path(__file__).resolve().parents[1] / "backend/migrations/026_designer_studio.sql"


class FakeService:
    def __init__(self, connection, workspace_id):
        self.con, self.wid = connection, workspace_id
        self.events = []

    def get(self, table, record_id):
        if table not in ("designer_projects", "designer_rooms", "designer_items", "clients"):
            raise AssertionError("Invalid test table")
        row = self.con.execute(
            f"SELECT * FROM {table} WHERE id=? AND workspace_id=?",
            (record_id, self.wid),
        ).fetchone()
        if not row:
            raise business.DomainError(404, "Запись не найдена")
        return row

    def page(self, query):
        return 0

    def check_revision(self, row, data):
        if type(data.get("revision")) is not int or data["revision"] != row["revision"]:
            raise business.DomainError(409, "Запись изменена")

    def emit(self, *args):
        self.events.append(args)


class DesignerContractTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:", isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.execute("CREATE TABLE workspaces(id TEXT PRIMARY KEY)")
        self.con.execute("CREATE TABLE clients(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL)")
        self.con.executemany("INSERT INTO workspaces VALUES(?)", [("team-a",), ("team-b",)])
        self.con.executemany("INSERT INTO clients VALUES(?,?)", [("client-a", "team-a"), ("client-b", "team-b")])
        self.con.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at INTEGER NOT NULL)")
        self.con.executescript(MIGRATION.read_text(encoding="utf-8"))
        self.a = FakeService(self.con, "team-a")
        self.b = FakeService(self.con, "team-b")

    def tearDown(self):
        self.con.close()

    def use(self, service, method, path, data=None):
        return route(service, method, path.strip("/").split("/"), {}, data or {})

    def create(self):
        status, result = self.use(self.a, "POST", "projects", {
            "name": "Квартира 120 м²", "budget_kopecks": 1_000_000,
            "client_id": "client-a",
        })
        self.assertEqual(status, 201)
        return result["project"]["id"]

    def test_create_room_item_and_decimal_total(self):
        project = self.create()
        _, room = self.use(self.a, "POST", f"projects/{project}/rooms", {"name": "Гостиная"})
        room_id = room["room"]["id"]
        code, item = self.use(self.a, "POST", f"projects/{project}/items", {
            "name": "Диван", "room_id": room_id, "kind": "furniture",
            "quantity": "2.5", "unit_price": 19999, "article": "SOFA-A1",
            "supplier": "Магазин мебели", "status": "selected",
        })
        self.assertEqual(code, 201)
        self.assertEqual(item["item"]["total_kopecks"], 49998)
        _, result = self.use(self.a, "GET", f"projects/{project}")
        self.assertEqual(result["summary"]["total_kopecks"], 49998)
        self.assertEqual(result["summary"]["remainder_kopecks"], 950002)
        self.assertEqual(result["summary"]["missing_prices"], 0)
        self.assertEqual(result["items"][0]["room_id"], room_id)

    def test_workspace_and_project_isolation(self):
        project = self.create()
        with self.assertRaises(business.DomainError) as err:
            self.use(self.b, "GET", f"projects/{project}")
        self.assertEqual(err.exception.status, 404)
        with self.assertRaises(business.DomainError) as err:
            self.use(self.a, "POST", "projects", {
                "name": "Недоступный клиент", "client_id": "client-b",
            })
        self.assertEqual(err.exception.status, 404)
        _, foreign = self.use(self.b, "POST", "projects", {"name": "Чужой проект"})
        other_project = foreign["project"]["id"]
        _, room = self.use(self.b, "POST", f"projects/{other_project}/rooms", {"name": "Чужая комната"})
        with self.assertRaises(business.DomainError) as err:
            self.use(self.a, "POST", f"projects/{project}/items", {
                "name": "Несанкционированное прикрепление",
                "room_id": room["room"]["id"],
            })
        self.assertEqual(err.exception.status, 404)

    def test_rejects_invalid_numbers_and_untrusted_fields(self):
        project = self.create()
        for value in (-1, True, 10**12, "100"):
            with self.subTest(value=value), self.assertRaises(business.DomainError):
                self.use(self.a, "POST", f"projects/{project}/items", {
                    "name": "Мебель", "unit_price": value,
                })
        for quantity in ("NaN", "Infinity", "-1", "0", "0.00001", "1000001"):
            with self.subTest(quantity=quantity), self.assertRaises(business.DomainError):
                self.use(self.a, "POST", f"projects/{project}/items", {
                    "name": "Мебель", "quantity": quantity, "unit_price": 1,
                })
        _, result = self.use(self.a, "POST", f"projects/{project}/items", {
            "name": "Кресло", "unit_price": 0, "workspace_id": "team-b",
        })
        self.assertEqual(result["item"]["workspace_id"], "team-a")
        _, details = self.use(self.a, "GET", f"projects/{project}")
        self.assertEqual(details["summary"]["missing_prices"], 1)

    def test_revision_conflict_and_update(self):
        project = self.create()
        _, record = self.use(self.a, "POST", f"projects/{project}/items", {
            "name": "Плитка", "unit_price": 10000,
        })
        item = record["item"]
        _, changed = self.use(self.a, "PATCH", f"projects/{project}/items/{item['id']}", {
            "revision": 1, "quantity": "3", "unit_price": 17000,
        })
        self.assertEqual(changed["item"]["total_kopecks"], 51000)
        self.assertEqual(changed["item"]["revision"], 2)
        with self.assertRaises(business.DomainError) as err:
            self.use(self.a, "PATCH", f"projects/{project}/items/{item['id']}", {
                "revision": 1, "quantity": "999",
            })
        self.assertEqual(err.exception.status, 409)

    def test_deleted_room_reassigns_items_to_general_scope(self):
        project = self.create()
        _, room = self.use(self.a, "POST", f"projects/{project}/rooms", {"name": "Кухня"})
        room_id = room["room"]["id"]
        self.use(self.a, "POST", f"projects/{project}/items", {
            "name": "Светильник", "room_id": room_id, "unit_price": 20000,
        })
        self.use(self.a, "DELETE", f"projects/{project}/rooms/{room_id}")
        _, details = self.use(self.a, "GET", f"projects/{project}")
        self.assertEqual(len(details["items"]), 1)
        self.assertIsNone(details["items"][0]["room_id"])


if __name__ == "__main__":
    unittest.main()
