"""Private work statistics for the currently selected workspace."""
from backend.business import business_date


def summary(service):
    con, wid = service.con, service.wid
    workspace = dict(con.execute(
        "SELECT id,name,currency FROM workspaces WHERE id=?", (wid,)
    ).fetchone())
    counts = dict(con.execute(
        "SELECT (SELECT count(*) FROM quotes WHERE workspace_id=?) AS quotes,"
        "(SELECT count(*) FROM construction_objects WHERE workspace_id=?) AS objects,"
        "(SELECT count(*) FROM clients WHERE workspace_id=?) AS clients,"
        "(SELECT count(*) FROM projects WHERE workspace_id=? AND status NOT IN ('completed','cancelled')) AS active_projects,"
        "(SELECT count(*) FROM projects WHERE workspace_id=? AND status='completed') AS completed_projects,"
        "(SELECT count(*) FROM assistant_conversations WHERE workspace_id=? AND user_id=?) AS conversations",
        (wid, wid, wid, wid, wid, wid, service.user['id']),
    ).fetchone())
    states = {row['state']: row['total'] for row in con.execute(
        "SELECT CASE WHEN status='completed' THEN 'completed' ELSE approval_state END AS state,"
        "count(*) AS total FROM quotes WHERE workspace_id=? GROUP BY 1", (wid,)
    )}
    recent = [dict(row) for row in con.execute(
        "SELECT id,title,client,currency,amount_kopecks,approval_state,updated_at FROM quotes "
        "WHERE workspace_id=? ORDER BY updated_at DESC,id LIMIT 5", (wid,)
    )]
    return {'workspace': workspace, 'counts': counts, 'quote_states': states,
            'recent_quotes': recent, 'money': money_summary(service) if service.finance_visible() else None}


def money_summary(service):
    con, wid = service.con, service.wid
    today = business_date()
    month = today.replace(day=1)
    months = []
    for offset in range(5, -1, -1):
        index = month.year * 12 + month.month - 1 - offset
        months.append(f'{index // 12:04d}-{index % 12 + 1:02d}')
    first = months[0] + '-01'
    current = months[-1] + '-01'
    until = today.isoformat()
    currencies = {}

    def currency(code):
        if code not in currencies:
            currencies[code] = {'currency': code, 'received': 0, 'spent': 0,
                                'received_month': 0, 'spent_month': 0,
                                'months': [{'month': value, 'received': 0, 'spent': 0} for value in months]}
        return currencies[code]

    # Each stream is aggregated separately: joining payments and expenses would
    # multiply amounts when a project has several records of both kinds.
    for table, date_field, key in (
        ('project_payments', 'payment_date', 'received'), ('expenses', 'expense_date', 'spent')
    ):
        for row in con.execute(
            f"SELECT p.currency,coalesce(sum(x.amount_kopecks),0) AS total,"
            f"coalesce(sum(CASE WHEN x.{date_field}>=? THEN x.amount_kopecks ELSE 0 END),0) AS this_month "
            f"FROM {table} x JOIN projects p ON p.id=x.project_id AND p.workspace_id=x.workspace_id "
            f"WHERE x.workspace_id=? AND x.{date_field}<=? GROUP BY p.currency", (current, wid, until)
        ):
            item = currency(row['currency'])
            item[key] = row['total']
            item[key + '_month'] = row['this_month']
        for row in con.execute(
            f"SELECT p.currency,substr(x.{date_field},1,7) AS month,sum(x.amount_kopecks) AS total "
            f"FROM {table} x JOIN projects p ON p.id=x.project_id AND p.workspace_id=x.workspace_id "
            f"WHERE x.workspace_id=? AND x.{date_field}>=? AND x.{date_field}<=? "
            f"GROUP BY p.currency,substr(x.{date_field},1,7)", (wid, first, until)
        ):
            item = currency(row['currency'])
            item['months'][months.index(row['month'])][key] = row['total']
    default = con.execute('SELECT currency FROM workspaces WHERE id=?', (wid,)).fetchone()[0] or 'RUB'
    currency(default)
    for item in currencies.values():
        item['balance'] = item['received'] - item['spent']
        item['balance_month'] = item['received_month'] - item['spent_month']
    return {'as_of': until, 'currencies': sorted(currencies.values(), key=lambda item: (item['currency'] != default, item['currency']))}
