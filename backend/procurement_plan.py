"""Read-only material planning from recorded quantities and purchases, never AI prices."""

import hashlib
import io
import unicodedata
from decimal import Decimal, ROUND_HALF_UP

from backend.business import DomainError, decimal, packed, stamp
from backend.documents import Download


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).casefold().split())


def amount(quantity, price):
    result = int((quantity * price).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if abs(result) > 9_007_199_254_740_991:
        raise DomainError(400, 'Сумма закупок слишком велика для расчёта')
    return result


def plan(service, obj, change='0'):
    change = decimal(change, 'Изменение будущих цен, %', '-100', '1000', places=2)
    materials = service.con.execute(
        'SELECT q.*,z.name AS zone_name FROM construction_quantities q '
        'LEFT JOIN construction_zones z ON z.id=q.zone_id AND z.workspace_id=q.workspace_id '
        "WHERE q.workspace_id=? AND q.object_id=? AND q.kind='material' ORDER BY q.created_at,q.id",
        (service.wid, obj['id']),
    ).fetchall()
    purchases = service.con.execute(
        'SELECT material_id,quantity,unit_price_kopecks,status,purchased_on FROM construction_purchases '
        'WHERE workspace_id=? AND object_id=? ORDER BY purchased_on,updated_at,created_at,id',
        (service.wid, obj['id']),
    ).fetchall()
    facts = service.con.execute(
        'SELECT quantity_id,quantity FROM construction_facts WHERE workspace_id=? AND object_id=?',
        (service.wid, obj['id']),
    ).fetchall()
    groups, by_id = {}, {}
    for row in materials:
        # Different SKUs, specifications and units must never be pooled by guesswork.
        key = (row['catalog_id'] or '', normalized(row['title']), row['unit'], normalized(row['notes']))
        group = groups.setdefault(key, dict(
            id=hashlib.sha256(packed(key).encode()).hexdigest()[:24],
            title=row['title'], unit=row['unit'], notes=row['notes'], material_ids=[], zones=[],
            required=Decimal(0), received=Decimal(0), ordered=Decimal(0), consumed=Decimal(0),
            planned=0, weighted=Decimal(0), planned_known=True, recorded=0, recorded_known=True, latest_price=None,
            latest_price_date=None,
        ))
        group['material_ids'].append(row['id'])
        if row['zone_name'] and row['zone_name'] not in group['zones']:
            group['zones'].append(row['zone_name'])
        quantity = Decimal(row['quantity'])
        group['required'] += quantity
        group['planned'] += amount(quantity, row['cost_price'])
        group['weighted'] += quantity * row['cost_price']
        group['planned_known'] &= row['cost_price'] > 0
        by_id[row['id']] = group
    for row in purchases:
        group = by_id.get(row['material_id'])
        if group is None:
            continue
        quantity, price = Decimal(row['quantity']), row['unit_price_kopecks']
        group['received' if row['status'] == 'received' else 'ordered'] += quantity
        group['recorded'] += amount(quantity, price)
        group['recorded_known'] &= price > 0
        if price > 0:
            group['latest_price'], group['latest_price_date'] = price, row['purchased_on']
    for row in facts:
        if row['quantity_id'] in by_id:
            by_id[row['quantity_id']]['consumed'] += Decimal(row['quantity'])

    items, budgets = [], []
    finance = service.finance_visible()
    for group in groups.values():
        remaining = max(Decimal(0), group['required'] - group['received'] - group['ordered'])
        item = {key: group[key] for key in ('id', 'title', 'unit', 'notes', 'material_ids', 'zones')}
        item.update(
            required_quantity=str(group['required']), received_quantity=str(group['received']),
            ordered_quantity=str(group['ordered']), to_buy_quantity=str(remaining),
            surplus_quantity=str(max(Decimal(0), group['received'] + group['ordered'] - group['required'])),
            shortage_quantity=str(max(Decimal(0), group['consumed'] - group['received'])),
        )
        if finance:
            reference = group['latest_price']
            source = 'purchase' if reference is not None else 'planned' if group['planned_known'] else 'unknown'
            if reference is None and group['planned_known'] and group['required'] > 0:
                reference = amount(group['weighted'] / group['required'], 1)
            future_price = amount(Decimal(reference), 1 + Decimal(change) / 100) if reference is not None else None
            # A weighted average can contain fractions of a kopeck. Round the
            # final amount, not that average, to avoid inventing an overrun.
            basis = (group['weighted'] / group['required'] * (1 + Decimal(change) / 100)
                     if source == 'planned' and group['required'] > 0 else future_price)
            future_cost = amount(remaining, basis) if basis is not None else 0 if remaining == 0 else None
            forecast = (group['recorded'] + future_cost
                        if group['recorded_known'] and future_cost is not None else None)
            if forecast is not None:
                amount(Decimal(forecast), 1)
            budget = dict(
                planned_kopecks=group['planned'] if group['planned_known'] else None,
                recorded_kopecks=group['recorded'] if group['recorded_known'] else None,
                reference_unit_price_kopecks=reference, reference_source=source,
                reference_date=group['latest_price_date'], future_unit_price_kopecks=future_price,
                remaining_kopecks=future_cost, forecast_kopecks=forecast,
                delta_kopecks=forecast - group['planned'] if forecast is not None and group['planned_known'] else None,
                unknown_purchase_prices=not group['recorded_known'],
            )
            item['procurement_budget'] = budget
            budgets.append(budget)
        items.append(item)
    items.sort(key=lambda item: (Decimal(item['to_buy_quantity']) == 0, normalized(item['title']), item['id']))
    result = dict(
        object_id=obj['id'], object_name=obj['name'], generated_at=stamp(), price_change_percent=str(change),
        materials=items,
        summary=dict(groups=len(items), source_rows=len(materials),
                     to_buy_groups=sum(Decimal(item['to_buy_quantity']) > 0 for item in items),
                     surplus_groups=sum(Decimal(item['surplus_quantity']) > 0 for item in items),
                     shortage_groups=sum(Decimal(item['shortage_quantity']) > 0 for item in items)),
    )
    if finance:
        def total(key):
            return amount(Decimal(sum(item[key] for item in budgets)), 1) if all(item[key] is not None for item in budgets) else None

        planned, forecast = total('planned_kopecks'), total('forecast_kopecks')
        result['procurement_budget'] = dict(
            planned_kopecks=planned, recorded_kopecks=total('recorded_kopecks'),
            remaining_kopecks=total('remaining_kopecks'), forecast_kopecks=forecast,
            delta_kopecks=forecast - planned if forecast is not None and planned is not None else None,
            unpriced_groups=sum(item['forecast_kopecks'] is None for item in budgets),
        )
    return result


def supplier_xlsx(result):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    book = Workbook()
    sheet = book.active
    sheet.title = 'Список закупок'
    sheet.append(['Список закупок', result['object_name']])
    sheet.append(['Материал', 'Примечание', 'Единица', 'Потребность', 'Получено', 'Заказано', 'Докупить', 'Помещения'])
    for item in result['materials']:
        if Decimal(item['to_buy_quantity']) <= 0:
            continue
        sheet.append([item['title'], item['notes'], item['unit'],
                      *[Decimal(item[key]) for key in ('required_quantity', 'received_quantity', 'ordered_quantity', 'to_buy_quantity')],
                      ', '.join(item['zones'])])
    # Untrusted names and notes stay literal strings, including =, +, -, @.
    for row in sheet:
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = 's'
            cell.alignment = Alignment(vertical='top', wrap_text=True)
    for cell in sheet[2]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='202020')
    for key, width in zip('ABCDEFGH', (34, 40, 12, 16, 16, 16, 16, 34)):
        sheet.column_dimensions[key].width = width
    for row in sheet.iter_rows(min_row=3, min_col=4, max_col=7):
        for cell in row:
            cell.number_format = '0.####'
    sheet.freeze_panes = 'A3'
    sheet.auto_filter.ref = f'A2:H{max(2, sheet.max_row)}'
    output = io.BytesIO()
    book.save(output)
    return Download(output.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'smetra-procurement.xlsx')
