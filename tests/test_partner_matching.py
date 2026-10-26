"""Assistant partner offers: only needed materials, only verified partners, spread across partners."""
import json
import sqlite3
import time
import unittest
from pathlib import Path

from backend import business, partner_platform as partner
from backend.partner_matching import is_work, offers_for, offers_for_quote


class PartnerMatchingTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:", isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript((Path(__file__).parents[1] / "backend/schema.sql").read_text())
        business.migrate(self.con)
        self.a = self._partner("store-a", "Магазин А", "a-store.ru", [
            ("TILE-1", "Плитка керамическая 30×60 серая", 189000),
            ("LAM-1", "Ламинат дуб 33 класс", 99000),
            ("DRY-1", "Гипсокартон влагостойкий 12,5 мм", 55000),
        ])
        self.b = self._partner("store-b", "Магазин Б", "b-store.ru", [
            ("T-9", "Плитка керамическая 30×60 светлая", 175000),
            ("L-9", "Ламинат 33 класс ясень", 101000),
            ("G-9", "Гипсокартон влагостойкий 12,5 мм Кнауф", 57000),
        ])

    def tearDown(self):
        self.con.close()

    def _partner(self, code, name, host, products, verified=True, active=True):
        created = partner.create_partner(self.con, {"code": code, "name": name, "allowed_host": host})
        account = self.con.execute("SELECT * FROM partner_accounts WHERE id=?", (created["id"],)).fetchone()
        partner.ingest_products(self.con, account, {"products": [
            {"sku": sku, "name": title, "price_kopecks": price, "url": f"https://{host}/p/{sku}"} for sku, title, price in products]})
        if verified:
            now = int(time.time())
            self.con.execute(
                "INSERT INTO partner_domain_verifications(partner_id,domain,token,status,method,verified_at,last_checked_at,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)", (created["id"], host, "smetra-verify-x", "verified", "dns", now, now, now))
        if not active:
            self.con.execute("UPDATE partner_accounts SET active=0 WHERE id=?", (created["id"],))
        return created["id"]

    def test_work_lines_are_not_products(self):
        self.assertTrue(is_work("Укладка плитки на пол"))
        self.assertTrue(is_work("Шпаклевание стен"))
        self.assertTrue(is_work("Монтаж гипсокартона"))
        self.assertFalse(is_work("Шпаклёвка финишная"))
        self.assertFalse(is_work("Плитка керамическая 30x60"))
        result = offers_for(self.con, "user-1", [{"name": "Укладка плитки", "quantity": "8", "unit": "м²"}])
        self.assertEqual(result["offers"], [])
        self.assertEqual(result["not_found"], [])

    def test_offers_only_needed_materials_spread_across_partners(self):
        result = offers_for(self.con, "user-1", [
            {"name": "Плитка керамическая 30x60", "quantity": "8", "unit": "м²"},
            {"name": "Ламинат 33 класс", "quantity": "24", "unit": "м²"},
            {"name": "Гипсокартон влагостойкий 12,5 мм", "quantity": "6", "unit": "лист"},
            {"name": "Укладка ламината", "quantity": "24", "unit": "м²"},
        ], origin="https://smetra.online")
        self.assertEqual([item["material"] for item in result["offers"]],
                         ["Плитка керамическая 30x60", "Ламинат 33 класс", "Гипсокартон влагостойкий 12,5 мм"])
        partners = {item["offer"]["partner"] for item in result["offers"]}
        self.assertEqual(partners, {"Магазин А", "Магазин Б"}, "offers must not all go to one partner")
        for item in result["offers"]:
            self.assertRegex(item["offer"]["buy_url"], r"^https://smetra\.online/api/partners/out/[0-9a-f-]{36}$")
        self.assertEqual(result["label"], "Партнёрское предложение")

    def test_unknown_material_is_reported_not_replaced(self):
        result = offers_for(self.con, "user-1", [{"name": "Кирпич облицовочный", "quantity": "500", "unit": "шт"}])
        self.assertEqual(result["offers"], [])
        self.assertEqual(result["not_found"], ["Кирпич облицовочный"])

    def test_unverified_inactive_and_unavailable_are_never_offered(self):
        self.con.execute("DELETE FROM partner_domain_verifications")
        self._partner("store-c", "Магазин В", "c-store.ru", [("K-1", "Кирпич облицовочный красный", 3000)], verified=False)
        self._partner("store-d", "Магазин Г", "d-store.ru", [("K-2", "Кирпич облицовочный жёлтый", 3200)], active=False)
        self.assertEqual(offers_for(self.con, "u", [{"name": "Кирпич облицовочный"}, {"name": "Плитка керамическая 30x60"}])["offers"], [])
        e = self._partner("store-e", "Магазин Д", "e-store.ru", [("K-3", "Кирпич облицовочный белый", 3500)])
        self.con.execute("UPDATE partner_products SET available=0 WHERE partner_id=?", (e,))
        self.assertEqual(offers_for(self.con, "u", [{"name": "Кирпич облицовочный"}])["offers"], [])

    def test_equal_offers_rotate_between_partners(self):
        seen = {offers_for(self.con, f"user-{i}", [{"name": "Гипсокартон влагостойкий 12,5 мм"}])["offers"][0]["offer"]["partner"]
                for i in range(40)}
        self.assertEqual(seen, {"Магазин А", "Магазин Б"})

    def test_quote_lines_respect_workspace_access(self):
        rows = [{"name": "Плитка керамическая 30x60", "quantity": "8", "unit": "м²", "included": True},
                {"name": "Укладка плитки", "quantity": "8", "unit": "м²", "included": True},
                {"name": "Ламинат 33 класс", "quantity": "24", "unit": "м²", "included": False}]

        class Service:
            con = self.con
            user = {"id": "user-1"}

            def get(self, table, record_id):
                if record_id != "q-mine":
                    raise business.DomainError(404, "Запись не найдена")

        self.con.execute("PRAGMA foreign_keys=OFF")
        for position, row in enumerate(rows):
            self.con.execute("INSERT INTO quote_items(id,quote_id,position,data) VALUES(?,?,?,?)",
                             (f"i{position}", "q-mine", position, json.dumps(row, ensure_ascii=False)))
        result = offers_for_quote(Service(), "q-mine")
        self.assertEqual([item["material"] for item in result["offers"]], ["Плитка керамическая 30x60"])
        with self.assertRaises(business.DomainError):
            offers_for_quote(Service(), "q-other")


if __name__ == "__main__":
    unittest.main()
