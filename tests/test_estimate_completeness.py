"""Regression tests for non-billable, scope-based estimate suggestions."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from backend.estimate_completeness import recommend
from backend.business import DomainError, Service


class EstimateCompletenessTests(unittest.TestCase):
    def test_demolition_with_materials_suggests_three_distinct_costs(self):
        result = recommend([{"name": "Демонтаж старой плитки"}, {"name": "Плитка керамическая", "category": "material"}])
        self.assertEqual({s["kind"] for s in result}, {"consumables", "delivery", "waste"})
        self.assertTrue(all("unit_price" not in s and "quantity" not in s for s in result))

    def test_painting_does_not_invent_transport_or_rubbish_removal(self):
        result = recommend([{"name": "Покраска стен"}])
        self.assertEqual([s["kind"] for s in result], ["consumables"])

    def test_existing_lines_are_not_suggested_again(self):
        result = recommend([{"name": "Демонтаж плитки"}, {"name": "Мешки и расходники для демонтажа"},
                            {"name": "Вывоз строительного мусора"}, {"name": "Доставка материалов"}])
        self.assertEqual(result, [])

    def test_explicit_exclusions_are_respected(self):
        result = recommend([{"name": "Демонтаж плитки"}, {"name": "Керамическая плитка"}],
                           "Без доставки и без вывоза мусора и без расходников")
        self.assertEqual(result, [])

    def test_self_delivery_suppresses_logistics(self):
        result = recommend([{"name": "Укладка ламината"}], "Материалы самовывозом")
        self.assertEqual({s["kind"] for s in result}, {"consumables"})

    def test_unrelated_services_have_no_suggestions(self):
        self.assertEqual(recommend([{"name": "Консультация дизайнера"}]), [])
        self.assertEqual(recommend([]), [])
        self.assertEqual(recommend(None), [])
        self.assertEqual(recommend([{"name": ""}]), [])

    def test_recommendations_are_idempotent_after_user_adds_them(self):
        original = [{"name": "Покраска стен"}]
        suggestions = recommend(original)
        original.extend({"name": s["name"], "optional": True, "included": False} for s in suggestions)
        self.assertEqual(recommend(original), [])

    def test_scoped_preview_does_not_save_or_call_ai(self):
        service = object.__new__(Service)
        service.h = SimpleNamespace(throttle=Mock())
        service.user = {"id": "user"}
        code, result = service.quotes("POST", ["recommendations"], {},
                                      {"items": [{"name": "Демонтаж стен"}], "description": ""})
        self.assertEqual(code, 200)
        self.assertEqual({s["kind"] for s in result["recommendations"]}, {"consumables", "waste"})
        service.h.throttle.assert_called_once()

    def test_preview_rejects_invalid_input(self):
        service = object.__new__(Service)
        service.h = SimpleNamespace(throttle=Mock())
        service.user = {"id": "user"}
        for bad in [{"items": [{}] * 201}, {"items": [None]}, {"items": [{"name": 123}]}]:
            with self.subTest(bad=bad), self.assertRaises(DomainError):
                service.quotes("POST", ["recommendations"], {}, bad)


if __name__ == "__main__":
    unittest.main()
