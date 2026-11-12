"""Safe, deterministic decimal calculation rules for workspace estimates.

No eval/exec, Python function calls, attributes, subscripts, or exponentiation.
Saved rules reuse workspace_knowledge with explicit versioned JSON; therefore no
new database table or RLS policy is required.
"""
import ast
import json
import re
from decimal import Decimal, InvalidOperation, DivisionByZero, localcontext

from backend.business import DomainError, identity, stamp, string

PREFIX = "SMETRA_FORMULA_V1:"
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,39}\Z")
MAX_VALUE = Decimal("1000000000000")
MAX_NODES = 64


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise DomainError(400, "Подставьте числовое значение")
    raw = str(value).strip().replace(",", ".")
    if not re.fullmatch(r"[+-]?(?:\d{1,12})(?:\.\d{1,8})?", raw):
        raise DomainError(400, "Некорректное значение переменной")
    try:
        parsed = Decimal(raw)
    except InvalidOperation:
        raise DomainError(400, "Некорректное значение переменной") from None
    if not parsed.is_finite() or abs(parsed) > MAX_VALUE:
        raise DomainError(400, "Число вне допустимого диапазона")
    return parsed


def _tree(expression):
    if not isinstance(expression, str) or not 1 <= len(expression) <= 260:
        raise DomainError(400, "Формула должна содержать от 1 до 260 символов")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        raise DomainError(400, "Некорректный синтаксис формулы") from None
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_NODES:
        raise DomainError(400, "Слишком сложная формула")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Load,
               ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.UAdd,
               ast.USub, ast.IfExp, ast.Compare, ast.Gt, ast.GtE, ast.Lt,
               ast.LtE, ast.Eq, ast.NotEq, ast.BoolOp, ast.And, ast.Or)
    if any(not isinstance(n, allowed) or
           (isinstance(n, ast.Constant) and (isinstance(n.value, bool) or
            not isinstance(n.value, (int, float)))) for n in nodes):
        raise DomainError(400, "Формула содержит запрещённую операцию")
    names = sorted({n.id for n in nodes if isinstance(n, ast.Name)})
    if len(names) > 12 or any(not IDENTIFIER.fullmatch(name) for name in names):
        raise DomainError(400, "Некорректные переменные формулы")
    return tree, names


def _evaluate(node, values, depth=0):
    if depth > 16:
        raise DomainError(400, "Слишком глубокая формула")
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, values, depth + 1)
    if isinstance(node, ast.Constant):
        return _decimal(node.value)
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise DomainError(400, "Укажите значение переменной " + node.id)
        return values[node.id]
    if isinstance(node, ast.UnaryOp):
        value = _evaluate(node.operand, values, depth + 1)
        if isinstance(node.op, ast.UAdd):
            return value
        if isinstance(node.op, ast.USub):
            return -value
    if isinstance(node, ast.BinOp):
        left = _evaluate(node.left, values, depth + 1)
        right = _evaluate(node.right, values, depth + 1)
        if isinstance(node.op, ast.Add):
            result = left + right
        elif isinstance(node.op, ast.Sub):
            result = left - right
        elif isinstance(node.op, ast.Mult):
            result = left * right
        elif isinstance(node.op, ast.Div):
            if right == 0:
                raise DomainError(400, "Деление на ноль")
            result = left / right
        else:
            raise DomainError(400, "Недопустимая операция")
        if not result.is_finite() or abs(result) > MAX_VALUE:
            raise DomainError(400, "Результат вне допустимого диапазона")
        return result
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, values, depth + 1)
        for operation, comp in zip(node.ops, node.comparators):
            right = _evaluate(comp, values, depth + 1)
            if isinstance(operation, ast.Gt):
                ok = left > right
            elif isinstance(operation, ast.GtE):
                ok = left >= right
            elif isinstance(operation, ast.Lt):
                ok = left < right
            elif isinstance(operation, ast.LtE):
                ok = left <= right
            elif isinstance(operation, ast.Eq):
                ok = left == right
            elif isinstance(operation, ast.NotEq):
                ok = left != right
            else:
                raise DomainError(400, "Недопустимое сравнение")
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        # A guarded expression must not evaluate a dangerous right-hand side
        # after the left-hand side already determines the boolean result.
        # Preserve the existing boolean return contract for conditional rules.
        if isinstance(node.op, ast.And):
            for part in node.values:
                if not _evaluate(part, values, depth + 1):
                    return False
            return True
        for part in node.values:
            if _evaluate(part, values, depth + 1):
                return True
        return False
    if isinstance(node, ast.IfExp):
        condition = _evaluate(node.test, values, depth + 1)
        return _evaluate(node.body if condition else node.orelse, values, depth + 1)
    raise DomainError(400, "Недопустимое выражение")


def calculate(expression, values=None, defaults=None):
    tree, names = _tree(expression)
    if values is None:
        values = {}
    if defaults is None:
        defaults = {}
    if not isinstance(values, dict) or not isinstance(defaults, dict):
        raise DomainError(400, "Переменные должны быть объектом")
    if len(values) > 12 or len(defaults) > 12:
        raise DomainError(400, "Допускается не более 12 переменных")
    for name in (*values, *defaults):
        if not isinstance(name, str) or not IDENTIFIER.fullmatch(name) or name not in names:
            raise DomainError(400, "Неизвестная переменная")
    merged = {k: _decimal(v) for k, v in {**defaults, **values}.items()}
    missing = [name for name in names if name not in merged]
    if missing:
        raise DomainError(400, "Укажите значение переменной " + missing[0])
    with localcontext() as ctx:
        ctx.prec = 28
        try:
            result = _evaluate(tree, merged)
        except (InvalidOperation, DivisionByZero, OverflowError, ZeroDivisionError):
            raise DomainError(400, "Не удалось вычислить выражение") from None
    if isinstance(result, bool) or not result.is_finite() or abs(result) > MAX_VALUE:
        raise DomainError(400, "Результат должен быть конечным числом")
    return {
        "result": format(result.normalize(), "f"),
        "expression": expression,
        "variables": {name: format(merged[name], "f") for name in names},
    }


def normalize_rule(data):
    if not isinstance(data, dict):
        raise DomainError(400, "Некорректное правило")
    title = string(data.get("title", ""), "Название правила", 120, True)
    expression = string(data.get("expression", ""), "Формула", 260, True)
    unit = string(data.get("unit", ""), "Единица", 40)
    defaults = data.get("defaults", {})
    _, names = _tree(expression)
    if not isinstance(defaults, dict) or len(defaults) > 12:
        raise DomainError(400, "Некорректные значения по умолчанию")
    if any(k not in names for k in defaults):
        raise DomainError(400, "Лишняя переменная в значениях по умолчанию")
    return {"title": title, "expression": expression, "unit": unit,
            "defaults": {k: format(_decimal(v), "f") for k, v in defaults.items()},
            "variables": names}


def _require_paid(service):
    from backend.entitlements import workspace_feature_access
    if not workspace_feature_access(service.con, service.wid, "smart_formulas", stamp())["allowed"]:
        raise DomainError(402, "Умные формулы доступны с PRO Solo. Подключите подписку в разделе «Тарифы».")


def list_rules(service):
    _require_paid(service)
    rows = service.con.execute(
        "SELECT id,title,content FROM workspace_knowledge WHERE workspace_id=? "
        "AND kind='rule' AND enabled=1 ORDER BY updated_at DESC LIMIT 50", (service.wid,),
    ).fetchall()
    result = []
    for row in rows:
        if not row["content"].startswith(PREFIX):
            continue
        try:
            rule = normalize_rule(json.loads(row["content"][len(PREFIX):]))
        except (ValueError, TypeError, DomainError):
            continue
        result.append({"id": row["id"], **rule})
    return {"rules": result}


def evaluate(service, args):
    _require_paid(service)
    if not isinstance(args, dict):
        raise DomainError(400, "Некорректный запрос")
    rule_id = args.get("rule_id")
    if rule_id:
        rule_id = string(rule_id, "Правило", 80, True)
        row = service.con.execute(
            "SELECT content FROM workspace_knowledge WHERE id=? AND workspace_id=? AND kind='rule' AND enabled=1",
            (rule_id, service.wid),
        ).fetchone()
        if not row or not row["content"].startswith(PREFIX):
            raise DomainError(404, "Правило не найдено")
        rule = normalize_rule(json.loads(row["content"][len(PREFIX):]))
    else:
        rule = normalize_rule({
            "title": args.get("title") or "Разовый расчёт",
            "expression": args.get("expression"), "unit": args.get("unit", ""), "defaults": {},
        })
    calculated = calculate(rule["expression"], args.get("values", {}), rule["defaults"])
    return {"rule_id": rule_id, "title": rule["title"], "unit": rule["unit"],
            **calculated, "note": "Расчёт по формуле; исходные размеры и нормы проверьте по проекту или производителю."}


def save_rule(service, data):
    # The action confirmation checks the current user's rights and paid status,
    # not just the earlier proposal.
    service.write_access(True)
    _require_paid(service)
    rule = normalize_rule(data)
    content = PREFIX + json.dumps({key: rule[key] for key in ("title", "expression", "unit", "defaults")},
                                  ensure_ascii=False, separators=(",", ":"))
    # The enclosing assistant-action transaction owns atomicity and idempotency.
    rows = service.con.execute(
        "SELECT id,title,content FROM workspace_knowledge WHERE workspace_id=? AND kind='rule' "
        "AND title=? LIMIT 1", (service.wid, rule["title"]),
    ).fetchall()
    if rows:
        if not rows[0]["content"].startswith(PREFIX):
            raise DomainError(409, "Название занято другим правилом команды")
        rid = rows[0]["id"]
        service.con.execute(
            "UPDATE workspace_knowledge SET content=?,enabled=1,updated_at=? WHERE id=? AND workspace_id=?",
            (content, stamp(), rid, service.wid),
        )
    else:
        count = service.con.execute(
            "SELECT count(*) FROM workspace_knowledge WHERE workspace_id=?", (service.wid,),
        ).fetchone()[0]
        if count >= 50:
            raise DomainError(409, "Достигнут лимит правил рабочего пространства")
        rid = identity()
        service.con.execute(
            "INSERT INTO workspace_knowledge(id,workspace_id,title,content,kind,enabled,created_by,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (rid, service.wid, rule["title"], content, "rule", 1, service.user["id"], stamp(), stamp()),
        )
    return {"id": rid, **rule, "saved": True}
