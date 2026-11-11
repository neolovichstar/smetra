"""Price sourcing and high-resolution cloud PDF regression coverage."""
import base64
import io
import json
import os
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.business import DomainError
from backend.estimate_drafts import enrich_catalog_prices, normalize
from backend.assistant_cloud import _validated_region, analyze_page


class PriceEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute("CREATE TABLE catalog_items (workspace_id TEXT, name TEXT, unit TEXT, "
                         "item_type TEXT, price INTEGER)")
        self.service = SimpleNamespace(con=self.con, wid="mine")

    def tearDown(self):
        self.con.close()

    def _row(self, name="Укладка плитки", kind="work", price=175000, wid="mine"):
        self.con.execute(
            "INSERT INTO catalog_items(workspace_id,name,unit,item_type,price) VALUES(?,?,?,?,?)",
            (wid, name, "м²", kind, price),
        )

    def _item(self, **kwargs):
        return {"name": "Укладка плитки", "quantity": "12", "unit": "м²",
                "kind": "work", "category": "Отделка", "unit_price": 0,
                "price_status": "unknown", **kwargs}

    def test_unknown_gets_exact_workspace_price_and_real_server_total(self):
        self._row(name="  УКЛАДКА   ПЛИТКИ ")
        self._row(name="Укладка плитки", price=999999, wid="other")
        args = enrich_catalog_prices(self.service, {"title": "Пол", "items": [self._item()]})
        self.assertEqual(args["items"][0]["unit_price"], 175000)
        self.assertEqual(args["items"][0]["price_status"], "confirmed")
        arguments, preview = normalize(args)
        self.assertEqual(preview["total"], 12 * 175000)
        self.assertIn("каталога", arguments["items"][0]["description"])

    def test_preserves_explicit_estimate_and_refuses_ambiguous_rates(self):
        self._row(price=150000)
        self._row(price=180000)
        given = self._item(unit_price=199000, price_status="estimate")
        rows = enrich_catalog_prices(self.service, {"items": [self._item(), given]})["items"]
        self.assertEqual(rows[0]["unit_price"], 0)
        self.assertEqual(rows[0]["price_status"], "unknown")
        self.assertEqual(rows[1]["unit_price"], 199000)
        self.assertEqual(rows[1]["price_status"], "estimate")

    def test_does_not_mix_work_material_unit_or_currency(self):
        self._row(kind="material")
        self._row(name="Укладка плитки", kind="work", price=0)
        self.assertEqual(enrich_catalog_prices(self.service, {"items": [self._item()]})
                         ["items"][0]["unit_price"], 0)
        self.assertEqual(enrich_catalog_prices(self.service, {
            "currency": "EUR", "items": [self._item()],
        })["items"][0]["unit_price"], 0)
        self._row(name="Укладка плитки", kind="work")
        item = self._item(unit="шт.")
        self.assertEqual(enrich_catalog_prices(self.service, {"items": [item]})
                         ["items"][0]["unit_price"], 0)


class CloudPDFVisualTests(unittest.TestCase):
    def test_region_geometry_rejected_before_any_provider_call(self):
        for crop in ({"x": .9, "y": 0, "width": .3, "height": 1},
                     {"x": 0, "y": 0, "width": .1, "height": .5},
                     {"x": 0, "y": 0, "width": float("nan"), "height": 1},
                     {"x": 0, "y": 0, "width": True, "height": 1}):
            with self.subTest(crop=crop), self.assertRaises(DomainError):
                _validated_region(crop)
        self.assertEqual(_validated_region(
            {"x": .25, "y": .25, "width": .5, "height": .5}), [.25, .25, .5, .5])

    def test_cloud_crop_is_rendered_and_only_selected_page_is_claimed(self):
        crop = {"x": .2, "y": .3, "width": .4, "height": .5}
        encoded = base64.b64encode(bytes((0xFF, 0xD8, 0xFF)) + b"x" * 20).decode()
        rendered = {"pages": [[7, encoded]], "total_pages": 49,
                    "region": [.2, .3, .4, .5], "truncated": True}
        report = {"choices": [{"message": {"content": "Размеры: часть цифр не читается."},
                               "finish_reason": "stop"}], "usage": {"total_tokens": 42}}
        fake_service = SimpleNamespace(
            user={"id": "member"}, h=SimpleNamespace(throttle=lambda *a: None),
        )
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-token"), patch(
            "backend.assistant_cloud._access",
        ), patch("backend.assistant_cloud._source", return_value=(
            {"provider": "google_drive"},
            {"name": "План.pdf", "mime": "application/pdf", "size": 100},
        )), patch("backend.file_processing.isolated_extract", return_value=rendered) as extractor, patch(
            "urllib.request.urlopen", return_value=io.BytesIO(json.dumps(report).encode())
        ):
            result = analyze_page(fake_service, "file", 7, region=crop,
                                  focus="размеры кухни", _raw=b"%PDF-stub")
        self.assertIn('"page":7', extractor.call_args.args[1])
        self.assertIn('"region":[0.2,0.3,0.4,0.5]', extractor.call_args.args[1])
        self.assertEqual(result["page"], 7)
        self.assertEqual(result["total_pages"], 49)
        self.assertEqual(result["region"], crop)
        self.assertFalse(result["report_partial"])
        self.assertIn("не читается", result["analysis"])


if __name__ == "__main__":
    unittest.main()
