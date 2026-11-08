import io
import json
from decimal import Decimal
import unittest

from openpyxl import load_workbook

from backend.business import DomainError, Service, without_finance
from backend.procurement_plan import amount
from tests import test_business, test_assistant_finance


class ProcurementPlanTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account
    team = test_assistant_finance.AssistantFinanceTests.team
    grant = test_assistant_finance.AssistantFinanceTests.grant
    tool_chat = test_assistant_finance.AssistantFinanceTests.tool_chat

    def object(self, token, name='Ремонт'):
        status, result = self.call('/construction/objects', 'POST', {'name': name}, token)
        self.assertEqual(status, 201, result)
        return result['object']['id']

    def material(self, token, obj, title='Краска', quantity='10', cost=1000, **extra):
        status, result = self.call('/construction/objects/' + obj + '/quantities', 'POST', {
            'title': title, 'formula': quantity, 'kind': 'material', 'unit': 'л',
            'unit_price': 2000, 'cost_price': cost, **extra,
        }, token)
        self.assertEqual(status, 201, result)
        return result['quantity']['id']

    def purchase(self, token, obj, material, quantity, price, status='received', day='2026-11-08'):
        code, result = self.call('/construction/objects/' + obj + '/purchases', 'POST', {
            'material_id': material, 'quantity': quantity, 'unit_price_kopecks': price,
            'purchased_on': day, 'status': status,
        }, token)
        self.assertEqual(code, 201, result)

    def report(self, token, obj, percent='0', workspace=None):
        code, result = self.call('/construction/objects/' + obj + '/procurement-plan?price_change=' + percent,
                                 token=token, workspace=workspace)
        self.assertEqual(code, 200, result)
        return result

    def test_pooling_prevents_buying_again_for_a_second_room(self):
        owner, _ = self.account('plan-pool')
        obj = self.object(owner)
        first = self.material(owner, obj, quantity='5')
        second = self.material(owner, obj, title='  КРАСКА  ', quantity='15', cost=1200)
        self.purchase(owner, obj, first, '12', 1100, day='2026-11-07')
        self.purchase(owner, obj, second, '2', 1300, status='ordered')
        result = self.report(owner, obj)
        row = result['materials'][0]
        self.assertEqual(result['summary'], dict(groups=1, source_rows=2, to_buy_groups=1, surplus_groups=0, shortage_groups=0))
        self.assertEqual(Decimal(row['to_buy_quantity']), 6)
        self.assertEqual(result['procurement_budget']['forecast_kopecks'], 23600)
        self.assertEqual(result['procurement_budget']['planned_kopecks'], 23000)
        self.assertEqual(result['procurement_budget']['delta_kopecks'], 600)
        scenario = self.report(owner, obj, '10')
        self.assertEqual(scenario['procurement_budget']['forecast_kopecks'], 24380)
        self.assertEqual(scenario['procurement_budget']['recorded_kopecks'], 15800)
        self.assertEqual(self.report(owner, obj)['procurement_budget'], result['procurement_budget'])
        self.assertEqual(self.call('/expenses', token=owner)[1]['items'], [])

    def test_specifications_units_and_catalog_ids_are_not_guessed_equivalent(self):
        owner, _ = self.account('plan-distinct')
        obj = self.object(owner)
        self.material(owner, obj, notes='Белая')
        self.material(owner, obj, notes='Чёрная')
        self.material(owner, obj, notes='Белая', unit='кг')
        catalog = self.call('/catalog', 'POST', {'name': 'Другой артикул', 'price': 1000}, owner)[1]['item']
        self.material(owner, obj, notes='Белая', catalog_id=catalog['id'])
        self.assertEqual(self.report(owner, obj)['summary']['groups'], 4)

    def test_missing_prices_are_unknown_and_fully_received_needs_no_future_price(self):
        owner, _ = self.account('plan-unknown')
        obj = self.object(owner)
        material = self.material(owner, obj, cost=0)
        result = self.report(owner, obj)
        self.assertIsNone(result['procurement_budget']['planned_kopecks'])
        self.assertIsNone(result['procurement_budget']['forecast_kopecks'])
        self.assertEqual(result['procurement_budget']['unpriced_groups'], 1)
        self.purchase(owner, obj, material, '10', 1234)
        result = self.report(owner, obj, '1000')
        self.assertEqual(result['procurement_budget']['forecast_kopecks'], 12340)
        self.assertEqual(result['procurement_budget']['remaining_kopecks'], 0)
        self.assertIsNone(result['procurement_budget']['delta_kopecks'])

    def test_unknown_recorded_price_is_not_hidden_by_a_later_known_price(self):
        owner, _ = self.account('plan-unknown-purchase')
        obj = self.object(owner)
        material = self.material(owner, obj)
        self.purchase(owner, obj, material, '2', 0)
        self.purchase(owner, obj, material, '2', 1200)
        result = self.report(owner, obj)
        self.assertIsNone(result['procurement_budget']['recorded_kopecks'])
        self.assertIsNone(result['procurement_budget']['forecast_kopecks'])
        self.assertTrue(result['materials'][0]['procurement_budget']['unknown_purchase_prices'])

    def test_latest_price_uses_purchase_date_and_surplus_is_not_negative_demand(self):
        owner, _ = self.account('plan-latest')
        obj = self.object(owner)
        material = self.material(owner, obj)
        self.purchase(owner, obj, material, '8', 1400, day='2026-11-08')
        self.purchase(owner, obj, material, '4', 900, day='2026-11-07')
        result = self.report(owner, obj, '-100')
        row = result['materials'][0]
        self.assertEqual(Decimal(row['to_buy_quantity']), 0)
        self.assertEqual(Decimal(row['surplus_quantity']), 2)
        self.assertEqual(row['procurement_budget']['reference_unit_price_kopecks'], 1400)
        self.assertEqual(result['procurement_budget']['forecast_kopecks'], 14800)

    def test_rounding_is_per_purchase_and_future_unit_price(self):
        owner, _ = self.account('plan-rounding')
        obj = self.object(owner)
        material = self.material(owner, obj, quantity='1', cost=101)
        self.purchase(owner, obj, material, '0.3333', 101)
        result = self.report(owner, obj, '10')
        self.assertEqual(result['procurement_budget']['recorded_kopecks'], 34)
        self.assertEqual(result['materials'][0]['procurement_budget']['future_unit_price_kopecks'], 111)
        self.assertEqual(result['procurement_budget']['remaining_kopecks'], 74)
        self.assertEqual(result['procurement_budget']['forecast_kopecks'], 108)

    def test_unit_price_is_not_lost_when_a_tiny_planned_line_rounds_to_zero(self):
        owner, _ = self.account('plan-tiny')
        obj = self.object(owner)
        self.material(owner, obj, quantity='0.0001', cost=1)
        result = self.report(owner, obj)
        self.assertEqual(result['materials'][0]['procurement_budget']['reference_unit_price_kopecks'], 1)

    def test_weighted_plan_does_not_invent_an_overrun_from_rounding(self):
        owner, _ = self.account('plan-weighted')
        obj = self.object(owner)
        self.material(owner, obj, quantity='1', cost=1)
        self.material(owner, obj, quantity='1', cost=2)
        result = self.report(owner, obj)
        self.assertEqual(result['procurement_budget']['forecast_kopecks'], 3)
        self.assertEqual(result['procurement_budget']['delta_kopecks'], 0)

    def test_private_budget_cannot_leak_to_a_member_or_assistant_after_revocation(self):
        owner, member, member_id, wid = self.team('plan-permission', granted=True)
        obj = self.object(owner)
        self.material(owner, obj, cost=19763)
        self.assertIn('procurement_budget', self.report(member, obj, workspace=wid))
        self.grant(owner, member_id, False)
        result = self.report(member, obj, workspace=wid)
        self.assertEqual(len(result['materials']), 1)
        self.assertNotIn('procurement_budget', json.dumps(result))
        self.assertNotIn('19763', json.dumps(result))
        from backend.assistant import execute_read
        with self.mod.db() as con:
            service = Service(None, con, 'http://localhost')
            service.wid, service.role = wid, 'member'
            service.user = con.execute('SELECT * FROM users WHERE id=?', (member_id,)).fetchone()
            result = execute_read(service, 'get_procurement_plan', {'id': obj, 'price_change_percent': '20'})
        self.assertNotIn('procurement_budget', json.dumps(result))
        self.assertEqual(without_finance({'procurement_budget': {'anything': 'private'}}), {})

    def test_cross_workspace_json_export_and_assistant_are_denied(self):
        owner, _ = self.account('plan-owner')
        outsider, outsider_id = self.account('plan-outsider')
        obj = self.object(owner)
        self.material(owner, obj)
        for suffix in ('procurement-plan', 'procurement-plan.xlsx'):
            self.assertEqual(self.call('/construction/objects/' + obj + '/' + suffix, token=outsider)[0], 404)
        from backend.assistant import execute_read
        wid = self.call('/workspace', token=outsider)[1]['workspace']['id']
        with self.mod.db() as con:
            service = Service(None, con, 'http://localhost')
            service.wid, service.role = wid, 'owner'
            service.user = con.execute('SELECT * FROM users WHERE id=?', (outsider_id,)).fetchone()
            with self.assertRaises(DomainError) as error:
                execute_read(service, 'get_procurement_plan', {'id': obj})
        self.assertEqual(error.exception.status, 404)

    def test_model_can_read_a_scenario_without_proposing_or_applying_a_write(self):
        owner, _ = self.account('plan-model')
        obj = self.object(owner)
        self.material(owner, obj)
        wid = self.call('/workspace', token=owner)[1]['workspace']['id']
        result, turns = self.tool_chat(owner, wid, 'get_procurement_plan',
                                      {'id': obj, 'price_change_percent': '10'})
        self.assertEqual(result['actions'], [])
        reports = [json.loads(message['content']) for turn in turns[1:] for message in turn
                   if message['role'] == 'tool']
        self.assertTrue(reports)
        self.assertEqual(reports[0]['procurement_budget']['forecast_kopecks'], 11000)
        self.assertFalse(reports[0]['materials_truncated'])

    def test_assistant_context_is_bounded_but_totals_cover_all_materials(self):
        owner, uid = self.account('plan-context-limit')
        obj = self.object(owner)
        for index in range(22):
            self.material(owner, obj, title='Материал ' + str(index), notes='x' * 1000)
        wid = self.call('/workspace', token=owner)[1]['workspace']['id']
        from backend.assistant import execute_read
        with self.mod.db() as con:
            service = Service(None, con, 'http://localhost')
            service.wid, service.role = wid, 'owner'
            service.user = con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
            result = execute_read(service, 'get_procurement_plan', {'id': obj})
        self.assertEqual(len(result['materials']), 20)
        self.assertTrue(result['materials_truncated'])
        self.assertEqual(result['summary']['groups'], 22)
        self.assertEqual(result['procurement_budget']['forecast_kopecks'], 220000)
        self.assertTrue(all(len(item['notes']) == 500 and 'material_ids' not in item for item in result['materials']))

    def test_supplier_export_contains_only_remaining_quantities_and_literal_text(self):
        owner, _ = self.account('plan-export')
        obj = self.object(owner, '=1+1')
        self.material(owner, obj, title='=HYPERLINK("https://example.invalid")', notes='@formula', cost=19763)
        closed = self.material(owner, obj, title='Уже получено')
        self.purchase(owner, obj, closed, '10', 12345)
        status, content = self.call('/construction/objects/' + obj + '/procurement-plan.xlsx', token=owner, raw=True)
        self.assertEqual(status, 200)
        book = load_workbook(io.BytesIO(content), data_only=False)
        sheet = book.active
        self.assertEqual(sheet.max_row, 3)
        self.assertEqual(sheet['B1'].value, '=1+1')
        self.assertEqual(sheet['B1'].data_type, 's')
        self.assertEqual(sheet['A3'].data_type, 's')
        self.assertEqual(sheet['B3'].value, '@formula')
        self.assertEqual(sheet['G3'].value, 10)
        values = json.dumps(list(sheet.values), ensure_ascii=False)
        self.assertNotIn('19763', values)
        self.assertNotIn('12345', values)
        self.assertEqual(len(book.worksheets), 1)

    def test_invalid_scenarios_and_mutations_are_rejected(self):
        owner, _ = self.account('plan-invalid')
        obj = self.object(owner)
        path = '/construction/objects/' + obj + '/procurement-plan'
        for percent in ('NaN', 'Infinity', '-100.01', '1000.01', '0.001', '1e999999'):
            self.assertEqual(self.call(path + '?price_change=' + percent, token=owner)[0], 400, percent)
        self.assertEqual(self.call(path, 'POST', {}, owner)[0], 405)
        with self.assertRaises(DomainError):
            amount(Decimal('1000000'), 100_000_000_000)

    def test_empty_plan_has_no_invented_missing_prices(self):
        owner, _ = self.account('plan-empty')
        result = self.report(owner, self.object(owner))
        self.assertEqual(result['materials'], [])
        self.assertEqual(result['procurement_budget']['forecast_kopecks'], 0)
        self.assertEqual(result['procurement_budget']['unpriced_groups'], 0)


    def quote(self, token, obj, material, name, price, stock='10', shipping=0, **other):
        payload = {
            'material_id': material, 'supplier_name': name, 'unit_price_kopecks': price,
            'stock_quantity': stock, 'min_order_quantity': '0',
            'delivery_kopecks': shipping, 'delivery_days': 2,
            'delivery_city': 'Москва', **other,
        }
        code, data = self.call('/construction/objects/' + obj + '/supplier-quotes',
                               'POST', payload, token)
        self.assertEqual(code, 201, data)
        return data['quote']['id']

    def test_smart_supplier_total_includes_delivery_not_commission(self):
        owner, _ = self.account('smart-price')
        obj = self.object(owner)
        material = self.material(owner, obj, quantity='10')
        self.quote(owner, obj, material, 'Магазин А', 39000, shipping=30000)
        self.quote(owner, obj, material, 'Магазин Б', 35000, shipping=180000)
        compare = self.report(owner, obj)['materials'][0]['supplier_comparison']
        self.assertEqual(compare['best']['suppliers'][0]['supplier'], 'Магазин А')
        self.assertEqual(compare['best']['products_kopecks'], 390000)
        self.assertEqual(compare['best']['delivery_kopecks'], 30000)
        self.assertEqual(compare['best']['total_kopecks'], 420000)
        self.assertEqual(compare['saving_vs_next_kopecks'], 110000)

    def test_smart_supplier_split_when_no_single_offer_fills_stock(self):
        owner, _ = self.account('smart-split')
        obj = self.object(owner)
        material = self.material(owner, obj, quantity='10')
        self.quote(owner, obj, material, 'Первый', 30000, stock='6', shipping=10000)
        self.quote(owner, obj, material, 'Второй', 32000, stock='4', shipping=10000)
        result = self.report(owner, obj)['materials'][0]['supplier_comparison']['best']
        self.assertEqual(result['kind'], 'split')
        self.assertEqual(result['total_kopecks'], 328000)
        self.assertEqual(sum(Decimal(x['quantity']) for x in result['suppliers']), Decimal('10'))

    def test_smart_supplier_missing_data_is_never_a_free_delivery(self):
        owner, _ = self.account('smart-unknown')
        obj = self.object(owner)
        material = self.material(owner, obj)
        self.quote(owner, obj, material, 'Цена без доставки', 100, shipping=None)
        self.quote(owner, obj, material, 'Неизвестный остаток', 100, stock=None)
        result = self.report(owner, obj)['materials'][0]['supplier_comparison']
        self.assertIsNone(result['best'])
        self.assertEqual(len(result['excluded']), 2)
        self.assertEqual(result['uncovered_quantity'], '10.0000')

    def test_smart_supplier_destination_expiry_and_deadline(self):
        import datetime as dt
        from backend.business import business_date
        owner, _ = self.account('smart-due')
        obj = self.object(owner)
        material = self.material(owner, obj)
        self.quote(owner, obj, material, 'Из другого города', 100, delivery_city='Тула')
        self.quote(owner, obj, material, 'Приедет поздно', 100, delivery_days=9)
        self.quote(owner, obj, material, 'Вовремя', 200, delivery_days=1)
        target = (business_date() + dt.timedelta(days=2)).isoformat()
        code, data = self.call('/construction/objects/' + obj +
            '/procurement-plan?site_city=%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&needed_by=' + target, token=owner)
        self.assertEqual(code, 200, data)
        comp = data['materials'][0]['supplier_comparison']
        self.assertEqual(comp['best']['suppliers'][0]['supplier'], 'Вовремя')
        self.assertEqual(len(comp['excluded']), 2)

    def test_smart_supplier_minimum_order_increases_real_cost(self):
        owner, _ = self.account('smart-minimum')
        obj = self.object(owner)
        material = self.material(owner, obj, quantity='3')
        self.quote(owner, obj, material, 'Опт', 500, stock='100', shipping=0, min_order_quantity='10')
        result = self.report(owner, obj)['materials'][0]['supplier_comparison']['best']
        self.assertEqual(result['purchased_quantity'], '10')
        self.assertEqual(result['total_kopecks'], 5000)

    def test_smart_supplier_crud_does_not_cross_workspace_or_leak_cost(self):
        owner, _ = self.account('smart-owner')
        outsider, _ = self.account('smart-outsider')
        obj = self.object(owner)
        material = self.material(owner, obj)
        quote_id = self.quote(owner, obj, material, 'Стройбаза', 4000, stock='10', shipping=1200)
        base = '/construction/objects/' + obj + '/supplier-quotes'
        self.assertEqual(self.call(base, 'POST', {
            'material_id': material, 'supplier_name': 'Атакующий',
            'unit_price_kopecks': 1, 'stock_quantity': '10', 'delivery_kopecks': 0,
        }, outsider)[0], 404)
        self.assertEqual(self.call(base + '/' + quote_id, 'DELETE', token=outsider)[0], 404)
        owner_row = self.report(owner, obj)['materials'][0]
        self.assertEqual(owner_row['supplier_quotes'][0]['id'], quote_id)
        status, modified = self.call(base + '/' + quote_id, 'PATCH', {
            'unit_price_kopecks': 3600,
        }, owner)
        self.assertEqual(status, 200, modified)
        self.assertEqual(self.report(owner, obj)['materials'][0]['supplier_comparison']['best']['total_kopecks'], 37200)
        self.assertEqual(self.call(base + '/' + quote_id, 'DELETE', token=owner)[0], 200)
        self.assertNotIn('supplier_comparison', self.report(owner, obj)['materials'][0])

    def test_smart_supplier_finance_revocation_hides_private_quotes(self):
        owner, member, member_id, wid = self.team('smart-revocation', granted=True)
        obj = self.object(owner)
        material = self.material(owner, obj)
        self.quote(owner, obj, material, 'Тайная закупочная цена', 19763)
        self.assertIn('supplier_comparison', self.report(member, obj, workspace=wid)['materials'][0])
        self.grant(owner, member_id, False)
        result = self.report(member, obj, workspace=wid)
        self.assertNotIn('supplier_quotes', json.dumps(result))
        self.assertNotIn('supplier_comparison', json.dumps(result))
        self.assertNotIn('19763', json.dumps(result))
        self.assertEqual(self.call('/construction/objects/' + obj + '/supplier-quotes',
                                   'POST', {'material_id': material}, member, workspace=wid)[0], 403)

    def test_smart_supplier_malformed_and_unverifiable_quotes(self):
        owner, _ = self.account('smart-invalid')
        obj = self.object(owner)
        material = self.material(owner, obj)
        base = '/construction/objects/' + obj + '/supplier-quotes'
        for value in ('NaN', '1e999999', '-1', '0.00001', '1000001'):
            self.assertEqual(self.call(base, 'POST', {
                'material_id': material, 'supplier_name': 'Поставщик', 'unit_price_kopecks': 100,
                'stock_quantity': value, 'delivery_kopecks': 0,
            }, owner)[0], 400, value)
        self.assertEqual(self.call(base, 'POST', {
            'material_id': material, 'supplier_name': '<script>alert(1)</script>',
            'unit_price_kopecks': -1, 'stock_quantity': '10', 'delivery_kopecks': 0,
        }, owner)[0], 400)


if __name__ == '__main__':
    unittest.main()
