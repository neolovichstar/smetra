"""Deterministic money control for one order (project).

Every figure is an integer number of kopecks computed here from stored rows:
the contract amount, the planned internal cost, recorded payments and expenses.
Nothing is estimated by a model; the assistant may only read these results.
"""

CLOSED = ("completed", "cancelled")


def percent(part, whole):
    """Whole percent, rounded half up; None when there is no base to compare to."""
    if whole <= 0:
        return None
    return (part * 200 + whole) // (whole * 2)


def summarize(amount, planned_cost, paid, actual_cost):
    amount, planned_cost, paid, actual_cost = (int(value or 0) for value in (amount, planned_cost, paid, actual_cost))
    overrun = max(0, actual_cost - planned_cost) if planned_cost > 0 else 0
    return dict(
        revenue=amount,
        planned_cost=planned_cost,
        actual_cost=actual_cost,
        paid=paid,
        receivable=max(0, amount - paid),
        overpaid=max(0, paid - amount),
        # Without any cost figure the margin is unknown, not 100%.
        planned_profit=amount - planned_cost if planned_cost > 0 else None,
        # Spending above plan comes straight out of the margin.
        forecast_profit=amount - max(planned_cost, actual_cost) if planned_cost > 0 or actual_cost > 0 else None,
        cash_result=paid - actual_cost,
        budget_used_pct=percent(actual_cost, planned_cost),
        overrun=overrun,
        paid_pct=percent(paid, amount),
    )


def project_rows(con, workspace_id):
    """Active orders with their payment and expense totals, one query."""
    return con.execute(
        "SELECT p.id,p.name,p.currency,p.status,p.due_date,p.amount_kopecks,p.internal_cost,"
        "coalesce((SELECT sum(x.amount_kopecks) FROM project_payments x WHERE x.project_id=p.id AND x.workspace_id=p.workspace_id),0) AS paid,"
        "coalesce((SELECT sum(x.amount_kopecks) FROM expenses x WHERE x.project_id=p.id AND x.workspace_id=p.workspace_id),0) AS actual_cost "
        "FROM projects p WHERE p.workspace_id=? AND p.status NOT IN (?,?)",
        (workspace_id, *CLOSED),
    ).fetchall()


def workspace_money(con, workspace_id, currency):
    """What the owner earns across active orders in one currency."""
    receivable = forecast = known = unknown = 0
    overruns = []
    for row in project_rows(con, workspace_id):
        if row["currency"] != currency:
            continue
        result = summarize(row["amount_kopecks"], row["internal_cost"], row["paid"], row["actual_cost"])
        receivable += result["receivable"]
        if result["forecast_profit"] is None:
            unknown += 1
        else:
            forecast += result["forecast_profit"]
            known += 1
        if result["overrun"]:
            overruns.append(dict(id=row["id"], name=row["name"], currency=row["currency"], overrun=result["overrun"], budget_used_pct=result["budget_used_pct"]))
    overruns.sort(key=lambda item: -item["overrun"])
    return dict(
        currency=currency,
        receivable=receivable,
        forecast_profit=forecast if known else None,
        orders_with_costs=known,
        orders_without_costs=unknown,
        overruns=overruns,
    )


def order_report(con, workspace_id):
    """Every order except cancelled ones, newest first, with its money figures."""
    rows = con.execute(
        "SELECT p.id,p.name,p.currency,p.status,p.due_date,p.amount_kopecks,p.internal_cost,"
        "coalesce((SELECT sum(x.amount_kopecks) FROM project_payments x WHERE x.project_id=p.id AND x.workspace_id=p.workspace_id),0) AS paid,"
        "coalesce((SELECT sum(x.amount_kopecks) FROM expenses x WHERE x.project_id=p.id AND x.workspace_id=p.workspace_id),0) AS actual_cost "
        "FROM projects p WHERE p.workspace_id=? AND p.status!='cancelled' ORDER BY p.updated_at DESC,p.id LIMIT 500",
        (workspace_id,),
    ).fetchall()
    return [
        dict(id=row["id"], name=row["name"], currency=row["currency"], status=row["status"], due_date=row["due_date"],
             **summarize(row["amount_kopecks"], row["internal_cost"], row["paid"], row["actual_cost"]))
        for row in rows
    ]


REPORT_COLUMNS = (
    ("name", "Заказ"), ("status", "Статус"), ("currency", "Валюта"), ("revenue", "Стоимость"),
    ("paid", "Получено"), ("receivable", "К получению"), ("planned_cost", "Себестоимость план"),
    ("actual_cost", "Расходы"), ("overrun", "Перерасход"), ("forecast_profit", "Ожидаемая прибыль"),
    ("cash_result", "Денежный результат"),
)
MONEY_COLUMNS = {"revenue", "paid", "receivable", "planned_cost", "actual_cost", "overrun", "forecast_profit", "cash_result"}


def kopecks_text(value):
    """Exact rubles with two decimals; no float rounding."""
    if value is None:
        return ""
    sign = "-" if value < 0 else ""
    value = abs(int(value))
    return f"{sign}{value // 100}.{value % 100:02d}"


STATUS_LABELS = {"planned": "Запланирован", "in_progress": "В работе", "waiting": "Ожидание", "completed": "Завершён", "cancelled": "Отменён"}


def report_rows(orders, numeric=False):
    """Header plus one row per order. Spreadsheets get exact Decimal rubles, CSV gets text."""
    from decimal import Decimal

    def cell(key, value):
        if key in MONEY_COLUMNS:
            if value is None:
                return None if numeric else ""
            return Decimal(int(value)) / 100 if numeric else kopecks_text(value)
        if key == "status":
            return STATUS_LABELS.get(value, value)
        return value

    return [[title for _, title in REPORT_COLUMNS]] + [[cell(key, order[key]) for key, _ in REPORT_COLUMNS] for order in orders]
